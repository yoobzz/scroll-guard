"""Źródło obrazu: RTSP z kamery (albo plik wideo / zdjęcie / kamera Maca do testów).

„mac” = kamera MacBooka przez ffmpeg, wybierana po nazwie (indeks 0 bywa
wirtualną kamerą OBS); „mac:<nazwa urządzenia>” = inna kamera AVFoundation.

Wątek czyta strumień bez przerwy i trzyma tylko najnowszą klatkę — analiza
nigdy nie dostaje starego obrazu z bufora. Gdy strumień padnie (np. router
odcięty karą), łączy się ponownie co kilka sekund.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
import cv2  # noqa: E402  (zmienna środowiskowa musi być ustawiona przed importem)
import numpy as np  # noqa: E402

ROZSZERZENIA_OBRAZOW = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
KAMERA_MACA = "MacBook Pro Camera"
ROZMIAR_MACA = (1280, 720)
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
LIMIT_POLACZENIA_MS = 8000
PONOW_PO_S = 3.0


class Kamera:
    def __init__(self) -> None:
        self._zrodlo = ""
        self._klatka: np.ndarray | None = None
        self._t = 0.0
        self._stan = "brak źródła"
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
                self._ustaw_stan("brak źródła — wpisz adres RTSP w WIĘCEJ")
                self._zmiana.wait(1.0)
                continue
            try:
                self._czytaj(zrodlo)
            except Exception as blad:  # noqa: BLE001 — wątek kamery nie może umrzeć
                self._ustaw_stan(f"błąd odczytu: {type(blad).__name__}")
            if not self._zmiana.is_set():
                self._zmiana.wait(PONOW_PO_S)

    def _czytaj(self, zrodlo: str) -> None:
        if zrodlo == "mac" or zrodlo.startswith("mac:"):
            self._czytaj_maca(zrodlo.partition(":")[2] or KAMERA_MACA)
            return
        plik = Path(zrodlo).expanduser()
        if plik.suffix.lower() in ROZSZERZENIA_OBRAZOW:
            self._czytaj_obraz(plik)
            return
        self._ustaw_stan("łączę z kamerą…")
        if zrodlo.isdigit():
            cap = cv2.VideoCapture(int(zrodlo))
        else:
            cap = cv2.VideoCapture(str(plik) if plik.exists() else zrodlo, cv2.CAP_FFMPEG,
                                   [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, LIMIT_POLACZENIA_MS,
                                    cv2.CAP_PROP_READ_TIMEOUT_MSEC, LIMIT_POLACZENIA_MS])
        try:
            if not cap.isOpened():
                self._ustaw_stan("nie mogę połączyć się z kamerą (adres, hasło, sieć?)")
                return
            z_pliku = plik.exists()
            odstep = 1.0 / (cap.get(cv2.CAP_PROP_FPS) or 15.0) if z_pliku else 0.0
            while not self._zmiana.is_set():
                ok, klatka = cap.read()
                if not ok:
                    if z_pliku:                     # wideo testowe kręci się w kółko
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                    self._ustaw_stan("strumień przerwany — łączę ponownie")
                    return
                self._publikuj(klatka)
                if odstep:
                    time.sleep(odstep)
        finally:
            cap.release()

    def _czytaj_obraz(self, plik: Path) -> None:
        obraz = cv2.imread(str(plik))
        if obraz is None:
            self._ustaw_stan("nie da się otworzyć pliku z obrazem")
            return
        while not self._zmiana.is_set():
            self._publikuj(obraz)
            time.sleep(0.1)

    def _czytaj_maca(self, nazwa: str) -> None:
        szer, wys = ROZMIAR_MACA
        polecenie = [FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "avfoundation",
                     "-framerate", "30", "-i", nazwa, "-vf", f"scale={szer}:{wys}",
                     "-r", "10", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
        self._ustaw_stan(f"otwieram kamerę „{nazwa}” (macOS może pytać o zgodę)…")
        proc = subprocess.Popen(polecenie, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        rozmiar = szer * wys * 3
        try:
            while not self._zmiana.is_set():
                bufor = proc.stdout.read(rozmiar)
                if len(bufor) < rozmiar:
                    blad = proc.stderr.read(400).decode("utf-8", "replace").strip().splitlines()
                    self._ustaw_stan(f"kamera Maca: {blad[-1] if blad else 'brak obrazu'}")
                    return
                self._publikuj(np.frombuffer(bufor, np.uint8).reshape(wys, szer, 3).copy())
        finally:
            proc.kill()
            proc.wait()
