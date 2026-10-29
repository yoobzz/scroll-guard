"""Sprawdza detektor na zdjęciach, także udając kamerę w rogu pokoju.

Użycie: python tests/sprawdz_obrazy.py <katalog_ze_zdjeciami> [katalog_wyjscia] [czulosc]
Pliki poz_*.jpg powinny dać TELEFON, neg_*.jpg nie. Każde zdjęcie jest
sprawdzane w oryginale i „z daleka”: pomniejszone tak, że kadr ma WYS_DALEKO px
wysokości i wklejone w klatkę 2560x1440 (jak główny strumień kamery IP).
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from detektor import Detektor  # noqa: E402
from rysuj import rysuj_wynik  # noqa: E402
from ustawienia import CZULOSC  # noqa: E402

KLATKA = (2560, 1440)
WYSOKOSCI_DALEKO = (600, 420, 300)


def z_daleka(obraz: np.ndarray, wys: int) -> np.ndarray:
    s = wys / obraz.shape[0]
    maly = cv2.resize(obraz, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    rng = np.random.default_rng(0)
    tlo = rng.integers(60, 90, size=(KLATKA[1], KLATKA[0], 3), dtype=np.uint8)
    y, x = (KLATKA[1] - maly.shape[0]) // 2 + 200, (KLATKA[0] - maly.shape[1]) // 3
    tlo[y:y + maly.shape[0], x:x + maly.shape[1]] = maly
    # kamera IP kompresuje: JPEG q=60 rozmywa drobne krawędzie jak H.264
    _, bufor = cv2.imencode(".jpg", tlo, [cv2.IMWRITE_JPEG_QUALITY, 60])
    return cv2.imdecode(bufor, cv2.IMREAD_COLOR)


def main() -> int:
    katalog = Path(sys.argv[1])
    wyjscie = Path(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] != "-" else None
    progi = CZULOSC[sys.argv[3] if len(sys.argv) > 3 else "normalna"]
    if wyjscie:
        wyjscie.mkdir(parents=True, exist_ok=True)
    det = Detektor(Path(__file__).resolve().parents[1] / "modele")
    trafione = bledne = 0
    for plik in sorted(katalog.glob("*.jpg")):
        obraz = cv2.imread(str(plik))
        warianty = [("oryginal", obraz)] + [(f"daleko{w}", z_daleka(obraz, w)) for w in WYSOKOSCI_DALEKO]
        for nazwa, klatka in warianty:
            w = det.analizuj(klatka, progi["pewnosc_tel"], progi["twarz"])
            oczekiwane = plik.name.startswith("poz_")
            ok = w.telefon_w_uzyciu == oczekiwane
            trafione += ok
            bledne += not ok
            tel = [f"{o.telefon.pewnosc:.2f}@{o.telefon.ramka[2]-o.telefon.ramka[0]}px"
                   for o in w.osoby if o.telefon]
            powody = "; ".join(o.powod for o in w.osoby) or "brak osob"
            print(f"{'OK ' if ok else 'ZLE'} {plik.stem:16} {nazwa:9} osoby={len(w.osoby)} "
                  f"tel={tel or '-'} obok={len(w.telefony_obok)} rece={w.rece_twarz} "
                  f"{w.czas_ms:5.0f}ms  [{powody}]")
            if wyjscie:
                cv2.imwrite(str(wyjscie / f"{plik.stem}_{nazwa}.jpg"),
                            rysuj_wynik(klatka, w, scrolluje=w.telefon_w_uzyciu, napis_dodatkowy=nazwa))
    print(f"\nzgodne {trafione}, niezgodne {bledne}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
