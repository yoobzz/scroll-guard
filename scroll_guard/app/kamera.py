"""Źródło obrazu: kamera IP (RTSP), ESP32 z kamerą (MJPEG po HTTP), kamera laptopa albo plik.

„laptop” = wbudowana kamera komputera: na Macu przez ffmpeg (AVFoundation), wybierana
po nazwie, bo indeks 0 bywa wirtualną kamerą OBS albo iPhone'em; na Linuksie /dev/video0.
„mac:<nazwa urządzenia>” = konkretna kamera AVFoundation.

Wątek czyta strumień bez przerwy i trzyma tylko najnowszą klatkę — analiza
nigdy nie dostaje starego obrazu z bufora. Gdy strumień padnie (np. router
odcięty karą), łączy się ponownie co kilka sekund.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from zrodla import kamera_wbudowana, rodzaj_zrodla, urzadzenia_wideo

os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
import cv2  # noqa: E402  (zmienna środowiskowa musi być ustawiona przed importem)
import numpy as np  # noqa: E402

ROZSZERZENIA_OBRAZOW = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
ROZMIAR_LAPTOPA = (1280, 720)
FFMPEG = shutil.which("ffmpeg") or next((p for p in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg")
                                          if Path(p).exists()), "")
LIMIT_POLACZENIA_MS = 8000
PONOW_PO_S = 3.0


class Kamera:
    def __init__(self) -> None:
        self._zrodlo = ""
        self._klatka: np.ndarray | None = None
        self._t = 0.0
        self._stan = "no source"
        self._lock = threading.Lock()
        self._zmiana = threading.Event()
        self._watek = threading.Thread(target=self._petla, daemon=True, name="kamera")

    def start(self) -> None:
        self._watek.start()

    def ustaw(self, zrodlo: str) -> None:
        with self._lock:
            if zrodlo == self._zrodlo:
                return
            self._zrodlo = zrodlo
            self._klatka = None
        self._zmiana.set()

    def klatka(self) -> tuple[np.ndarray | None, float]:
        with self._lock:
            return self._klatka, self._t

    @property
    def stan(self) -> str:
        with self._lock:
            return self._stan

    def _ustaw_stan(self, stan: str) -> None:
        with self._lock:
            self._stan = stan

    def _publikuj(self, klatka: np.ndarray) -> None:
        with self._lock:
            self._klatka, self._t, self._stan = klatka, time.time(), "ok"

    def _petla(self) -> None:
        while True:
            with self._lock:
                zrodlo = self._zrodlo
            self._zmiana.clear()
            if not zrodlo:
                self._ustaw_stan("no camera set: pick one under More")
                self._zmiana.wait(1.0)
                continue
            try:
                self._czytaj(zrodlo)
            except Exception as blad:  # noqa: BLE001 — wątek kamery nie może umrzeć
                self._ustaw_stan(f"read error: {type(blad).__name__}")
            if not self._zmiana.is_set():
                self._zmiana.wait(PONOW_PO_S)

    def _czytaj(self, zrodlo: str) -> None:
        rodzaj = rodzaj_zrodla(zrodlo)
        if rodzaj == "laptop":
            self._czytaj_laptop(zrodlo.partition(":")[2].strip())
            return
        plik = Path(zrodlo).expanduser()
        if rodzaj == "plik" and plik.suffix.lower() in ROZSZERZENIA_OBRAZOW:
            self._czytaj_obraz(plik)
            return
        self._ustaw_stan("connecting to the camera…")
        if rodzaj == "indeks":
            cap = cv2.VideoCapture(int(zrodlo))
        else:
            cap = cv2.VideoCapture(str(plik) if plik.exists() else zrodlo, cv2.CAP_FFMPEG,
                                   [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, LIMIT_POLACZENIA_MS,
                                    cv2.CAP_PROP_READ_TIMEOUT_MSEC, LIMIT_POLACZENIA_MS])
        self._czytaj_strumien(cap, z_pliku=plik.exists())

    def _czytaj_strumien(self, cap, z_pliku: bool = False) -> None:
        try:
            if not cap.isOpened():
                self._ustaw_stan("can't connect to the camera (address, password, network?)")
                return
            odstep = 1.0 / (cap.get(cv2.CAP_PROP_FPS) or 15.0) if z_pliku else 0.0
            while not self._zmiana.is_set():
                ok, klatka = cap.read()
                if not ok:
                    if z_pliku:                     # wideo testowe kręci się w kółko
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                    self._ustaw_stan("stream dropped, reconnecting")
                    return
                self._publikuj(klatka)
                if odstep:
                    time.sleep(odstep)
        finally:
            cap.release()

    def _czytaj_obraz(self, plik: Path) -> None:
        obraz = cv2.imread(str(plik))
        if obraz is None:
            self._ustaw_stan("can't open the image file")
            return
        while not self._zmiana.is_set():
            self._publikuj(obraz)
            time.sleep(0.1)

    def _czytaj_laptop(self, nazwa: str) -> None:
        if sys.platform != "darwin" or not FFMPEG:
            # Linux (V4L2) albo Mac bez ffmpeg: pierwsza kamera przez OpenCV
            self._ustaw_stan("opening the laptop camera…")
            self._czytaj_strumien(cv2.VideoCapture(0))
            return
        nazwa = nazwa or self._kamera_maca()
        if not nazwa:
            self._ustaw_stan("no laptop camera found")
            return
        szer, wys = ROZMIAR_LAPTOPA
        polecenie = [FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "avfoundation",
                     "-framerate", "30", "-i", nazwa, "-vf", f"scale={szer}:{wys}",
                     "-r", "10", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
        self._ustaw_stan(f"opening the laptop camera “{nazwa}” (macOS may ask for permission)…")
        proc = subprocess.Popen(polecenie, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        rozmiar = szer * wys * 3
        try:
            while not self._zmiana.is_set():
                bufor = proc.stdout.read(rozmiar)
                if len(bufor) < rozmiar:
                    blad = proc.stderr.read(400).decode("utf-8", "replace").strip().splitlines()
                    self._ustaw_stan(f"laptop camera: {blad[-1] if blad else 'no picture'}")
                    return
                self._publikuj(np.frombuffer(bufor, np.uint8).reshape(wys, szer, 3).copy())
        finally:
            proc.kill()
            proc.wait()

    @staticmethod
    def _kamera_maca() -> str | None:
        """Wbudowana kamera z listy urządzeń AVFoundation (ffmpeg wypisuje ją na stderr)."""
        try:
            lista = subprocess.run([FFMPEG, "-hide_banner", "-f", "avfoundation", "-list_devices", "true",
                                    "-i", ""], capture_output=True, text=True, timeout=10).stderr
        except (OSError, subprocess.TimeoutExpired):
            return None
        return kamera_wbudowana(urzadzenia_wideo(lista))
