"""Spina całość: kamera -> detektor -> śledzenie osób (licznik każdej) -> ESP, plus podgląd."""
from __future__ import annotations

import threading
import time
import traceback

import cv2
import numpy as np

import ustawienia as U
from detektor import Detektor, Wynik
from ha import HomeAssistant
from kamera import Kamera
from ocena import Ocena
from odciecie import Odcinacz
from rysuj import FONT, rysuj_wynik
from sledzenie import OsobaWKlatce, Sledzenie, krok_sledzenia

ANALIZ_NA_S = 3           # wystarczy: limit liczy się w minutach
PODGLAD_FPS = 10
PODGLAD_SZER = 1280
KLATKA_STARA_S = 5.0


def mmss(sekundy: float) -> str:
    s = int(max(0, sekundy))
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def _plansza(napis: str, podpis: str = "") -> np.ndarray:
    obraz = np.zeros((720, PODGLAD_SZER, 3), np.uint8)
    cv2.putText(obraz, napis, (60, 360), FONT, 2.0, (255, 255, 255), 3, cv2.LINE_AA)
    if podpis:
        cv2.putText(obraz, podpis, (60, 430), FONT, 1.0, (160, 160, 160), 2, cv2.LINE_AA)
    return obraz


class Straznik:
    def __init__(self, ust: U.Ustawienia, detektor: Detektor) -> None:
        self._lock = threading.Lock()
        self._ust = ust
        self._sledz = Sledzenie()
        self._wynik: Wynik | None = None
        self._blad = ""
        self._detektor = detektor
        self.kamera = Kamera()
        self.odcinacz = Odcinacz()
        self.ha = HomeAssistant()
        self._jpeg = b""
        self._jpeg_nr = 0
        self._nowy_jpeg = threading.Condition()

    # --- ustawienia ---
    @property
    def ust(self) -> U.Ustawienia:
        with self._lock:
            return self._ust

    def zmien_ustawienia(self, dane: dict) -> U.Ustawienia:
        with self._lock:
            nowe = U.zastosuj(self._ust, dane)
            self._ust = nowe
        U.zapisz(nowe)
        self.kamera.ustaw(nowe.zrodlo)
        return nowe

    def testuj_odciecie(self, sekundy: int = 20) -> None:
        ust = self.ust
        self.odcinacz.odetnij(ust.esp, sekundy, ust.esp_token)

    # --- pętle ---
    def start(self) -> None:
        self.kamera.ustaw(self.ust.zrodlo)
        self.kamera.start()
        threading.Thread(target=self._petla_analizy, daemon=True, name="analiza").start()
        threading.Thread(target=self._petla_podgladu, daemon=True, name="podglad").start()
        self.odcinacz.pilnuj_statusu(lambda: self.ust.esp)
        self.ha.publikuj(self.stan)

    def _petla_analizy(self) -> None:
        ostatnia = 0.0
        while True:
            start = time.time()
            klatka, t_klatki = self.kamera.klatka()
            if klatka is None or start - t_klatki > KLATKA_STARA_S or t_klatki == ostatnia:
                time.sleep(0.1)
                continue
            ostatnia = t_klatki
            ust = self.ust
            try:
                progi = U.CZULOSC[ust.czulosc]
                wynik = self._detektor.analizuj(klatka, progi["pewnosc_tel"], progi["twarz"])
            except Exception as blad:  # noqa: BLE001 — pętla musi żyć dalej
                traceback.print_exc()
                with self._lock:
                    self._blad = f"analiza: {type(blad).__name__}: {blad}"
                time.sleep(1.0)
                continue
            osoby = [OsobaWKlatce(o.ramka, o.z_telefonem, o.rece_twarz) for o in wynik.osoby]
            with self._lock:
                self._wynik, self._blad = wynik, ""
                self._sledz = krok_sledzenia(self._sledz, osoby, time.time(), ust)
                odpal = self._sledz.odpal
            if odpal:
                print(f"[straznik] limit {mmss(ust.limit_s)} przekroczony — kara {mmss(ust.kara_s)}", flush=True)
                self.odcinacz.odetnij(ust.esp, ust.kara_s, ust.esp_token)
                self.ha.zdarzenie_odciecia(ust.kara_s)
            time.sleep(max(0.0, 1.0 / ANALIZ_NA_S - (time.time() - start)))

    def _klatka_podgladu(self) -> np.ndarray:
        teraz = time.time()
        klatka, t_klatki = self.kamera.klatka()
        with self._lock:
            sledz, wynik, ust = self._sledz, self._wynik, self._ust
        if sledz.kara_zostalo(teraz) > 0:
            return _plansza("INTERNET ODCIETY", f"wraca za {mmss(sledz.kara_zostalo(teraz))}")
        if klatka is None or teraz - t_klatki > KLATKA_STARA_S:
            return _plansza("BRAK OBRAZU", "szczegoly na stronie")
        etykiety = []
        for id_ in sledz.przypisanie:
            slad = sledz.slad(id_)
            o = slad.ocena if slad else Ocena()
            etykiety.append((o.scrolluje, f"{mmss(o.seria_s)} / {mmss(ust.limit_s)}"))
        obraz = rysuj_wynik(klatka, wynik, etykiety)
        s = PODGLAD_SZER / obraz.shape[1]
        return cv2.resize(obraz, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else obraz

    def _petla_podgladu(self) -> None:
        while True:
            start = time.time()
            try:
                ok, bufor = cv2.imencode(".jpg", self._klatka_podgladu(), [cv2.IMWRITE_JPEG_QUALITY, 75])
                if ok:
                    with self._nowy_jpeg:
                        self._jpeg, self._jpeg_nr = bufor.tobytes(), self._jpeg_nr + 1
                        self._nowy_jpeg.notify_all()
            except Exception:  # noqa: BLE001
                traceback.print_exc()
            time.sleep(max(0.0, 1.0 / PODGLAD_FPS - (time.time() - start)))

    def czekaj_na_jpeg(self, poprzedni_nr: int, limit_s: float = 2.0) -> tuple[bytes, int]:
        with self._nowy_jpeg:
            self._nowy_jpeg.wait_for(lambda: self._jpeg_nr != poprzedni_nr, timeout=limit_s)
            return self._jpeg, self._jpeg_nr

    # --- stan dla strony ---
    def stan(self) -> dict:
        teraz = time.time()
        _, t_klatki = self.kamera.klatka()
        with self._lock:
            sledz, w, ust, blad = self._sledz, self._wynik, self._ust, self._blad
        prowadzacy = sledz.prowadzacy()
        o = prowadzacy.ocena if prowadzacy else Ocena()   # strona pokazuje osobę najbliżej limitu
        swiezy = w is not None and teraz - w.t < KLATKA_STARA_S
        telefon = max((x.telefon.pewnosc for x in w.osoby if x.telefon), default=None) if swiezy else None
        return {
            "scrolluje": any(s.ocena.scrolluje for s in sledz.slady),
            "scrollujacych": sum(s.ocena.scrolluje for s in sledz.slady),
            "seria_s": round(o.seria_s, 1),
            "przerwa_s": round(o.przerwa_s, 1),
            "udzial": round(o.udzial, 2),
            "kara_zostalo_s": round(sledz.kara_zostalo(teraz)),
            "obraz_ok": t_klatki > 0 and teraz - t_klatki < KLATKA_STARA_S,
            "kamera": self.kamera.stan,
            "osoby": len(w.osoby) if swiezy else 0,
            "telefon": round(telefon, 2) if telefon is not None else None,
            "powody": [x.powod for x in w.osoby] if swiezy else [],
            "analiza_ms": round(w.czas_ms) if swiezy else None,
            "blad": blad,
            "odciecie": self.odcinacz.stan(),
            "ustawienia": U.do_strony(ust),
        }
