"""Nakładka na podgląd: ramka wokół osoby z napisem SCROLLUJE / NIE SCROLLUJE."""
from __future__ import annotations

import cv2
import numpy as np

from detektor import Wynik

CZERWONY = (40, 40, 230)
ZIELONY = (90, 200, 60)
ZOLTY = (0, 220, 255)
SZARY = (150, 150, 150)
FONT = cv2.FONT_HERSHEY_DUPLEX   # bez polskich znaków — napisy ASCII


def _grubosc(klatka: np.ndarray) -> int:
    return max(2, klatka.shape[1] // 640)


def _napis(obraz, tekst: str, x: int, y: int, kolor, skala: float, grub: int) -> None:
    (w, h), base = cv2.getTextSize(tekst, FONT, skala, grub)
    y = max(y, h + base + 4)
    cv2.rectangle(obraz, (x, y - h - base - 6), (x + w + 10, y + 2), kolor, -1)
    cv2.putText(obraz, tekst, (x + 5, y - base - 2), FONT, skala, (255, 255, 255), grub, cv2.LINE_AA)


def rysuj_wynik(klatka: np.ndarray, wynik: Wynik | None, etykiety: list[tuple[bool, str]] | None = None,
                napis_dodatkowy: str = "", scrolluje: bool = False) -> np.ndarray:
    """etykiety: dla każdej osoby (czy scrolluje, jej licznik) z jej własnego śladu.

    Bez etykiet (np. w testach na zdjęciach) scrolluje ten, kto trzyma telefon.
    """
    obraz = klatka.copy()
    g = _grubosc(obraz)
    skala_tekstu = g * 0.45
    if wynik is not None and wynik.rozmiar == (obraz.shape[1], obraz.shape[0]):
        for i, osoba in enumerate(wynik.osoby):
            if etykiety is not None and i < len(etykiety):
                tak, licznik = etykiety[i]
            else:
                tak, licznik = scrolluje and osoba.z_telefonem, ""
            kolor = CZERWONY if tak else ZIELONY
            x1, y1, x2, y2 = osoba.ramka
            cv2.rectangle(obraz, (x1, y1), (x2, y2), kolor, g + 1)
            tekst = "SCROLLUJE" if tak else "NIE SCROLLUJE"
            if tak and licznik:
                tekst += f"  {licznik}"
            _napis(obraz, tekst, x1, y1 - 4, kolor, skala_tekstu, max(1, g // 2 + 1))
        for tel in wynik.telefony_obok:
            cv2.rectangle(obraz, tel.ramka[:2], tel.ramka[2:], SZARY, max(1, g // 2))
        for osoba in wynik.osoby:
            if osoba.telefon:
                cv2.rectangle(obraz, osoba.telefon.ramka[:2], osoba.telefon.ramka[2:], ZOLTY, g)
    if napis_dodatkowy:
        _napis(obraz, napis_dodatkowy, 10, obraz.shape[0] - 10, (60, 60, 60), skala_tekstu, 1)
    return obraz
