"""Rodzaje źródeł obrazu i wybór wbudowanej kamery laptopa (bez OpenCV — do testów w CI).

Źródła:
- „laptop” (albo starsze „mac”) — wbudowana kamera komputera, na którym działa serwer;
  „mac:<nazwa>” — konkretna kamera AVFoundation na Macu,
- rtsp://…  — kamera IP (np. TP-Link Tapo),
- http://…  — strumień MJPEG, np. ESP32-CAM / XIAO ESP32S3 Sense z przykładu CameraWebServer,
- liczba    — indeks kamery w OpenCV,
- ścieżka   — plik wideo albo zdjęcie (do testów).
"""
from __future__ import annotations

import re

LAPTOP = ("laptop", "mac")
# kamery, które nie są kamerą laptopa: wirtualne, ekran, „Desk View”, iPhone przez Continuity
NIE_LAPTOP = re.compile(r"virtual|capture screen|desk view|iphone|obs|snap camera|ndi", re.IGNORECASE)
WBUDOWANA = re.compile(r"macbook|facetime|built-?in|integrated", re.IGNORECASE)
LINIA_URZADZENIA = re.compile(r"\]\s*\[(\d+)\]\s*(.+?)\s*$")


def rodzaj_zrodla(zrodlo: str) -> str:
    """'' | 'laptop' | 'rtsp' | 'http' | 'indeks' | 'plik'."""
    z = zrodlo.strip()
    if not z:
        return ""
    if z.lower() in LAPTOP or z.lower().startswith("mac:"):
        return "laptop"
    if z.lower().startswith(("rtsp://", "rtsps://")):
        return "rtsp"
    if z.lower().startswith(("http://", "https://")):
        return "http"
    if z.isdigit():
        return "indeks"
    return "plik"


def urzadzenia_wideo(lista_ffmpeg: str) -> list[str]:
    """Nazwy kamer z `ffmpeg -f avfoundation -list_devices true -i ""` (bez urządzeń audio)."""
    nazwy, w_wideo = [], False
    for linia in lista_ffmpeg.splitlines():
        if "video devices" in linia:
            w_wideo = True
        elif "audio devices" in linia:
            w_wideo = False
        elif w_wideo and (m := LINIA_URZADZENIA.search(linia)):
            nazwy.append(m.group(2))
    return nazwy


def kamera_wbudowana(nazwy: list[str]) -> str | None:
    """Wbudowana kamera laptopa; bez niej pierwsza prawdziwa kamera; same wirtualne = None."""
    prawdziwe = [n for n in nazwy if not NIE_LAPTOP.search(n)]
    wbudowane = [n for n in prawdziwe if WBUDOWANA.search(n)]
    return (wbudowane or prawdziwe or [None])[0]
