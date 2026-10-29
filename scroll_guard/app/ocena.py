"""Ocena w czasie: kiedy „scrollujesz”, jak długo, kiedy odciąć internet.

Pojedyncza klatka kłamie (telefon mignie, zasłoni go ręka), więc decyzja idzie
z okna ostatnich sekund: ile klatek pokazywało telefon w użyciu. Licznik serii
rośnie, gdy scrollujesz; krótka przerwa go nie zeruje, dopiero dłuższa
(ustawienie przerwa_s). Po przekroczeniu limitu: jeden sygnał `odpal` i kara.
Wszystko to czyste funkcje na niezmiennym stanie — łatwo przetestować.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

from ustawienia import CZULOSC, Ustawienia

OKNO_S = 10.0               # z ilu ostatnich sekund liczymy udział klatek z telefonem
MIN_PROBEK = 3
PAMIEC_TELEFONU_S = 8.0     # „ręce przed twarzą” mostkują tylko krótkie zniknięcia telefonu
MAKS_KROK_S = 5.0           # dłuższa dziura w obrazie nie dolicza scrollowania (5 s: wolny procesor w add-onie)
WYGASANIE_S = 4.0           # tyle po wygaśnięciu pamięci telefonu stan gaśnie na pewno
DOWOD_S = 3.0               # kara tylko, gdy telefon był widziany w ostatnich sekundach


@dataclass(frozen=True)
class Ocena:
    okno: tuple[tuple[float, bool], ...] = ()
    scrolluje: bool = False
    seria_s: float = 0.0          # ile trwa bieżąca seria scrollowania
    przerwa_s: float = 0.0        # ile trwa przerwa w tej serii
    udzial: float = 0.0           # udział klatek z telefonem w oknie (0..1)
    ostatni_t: float | None = None
    telefon_t: float = -math.inf  # kiedy ostatnio widziany telefon w użyciu
    kara_do: float = 0.0
    odpal: bool = False           # True tylko w kroku, w którym trzeba odciąć internet

    def kara_zostalo(self, t: float) -> float:
        return max(0.0, self.kara_do - t)


def _po_karze(o: Ocena, t: float) -> Ocena:
    return replace(o, okno=(), scrolluje=False, seria_s=0.0, przerwa_s=0.0, udzial=0.0,
                   ostatni_t=t, odpal=False)


def krok(o: Ocena, t: float, telefon: bool, rece_przy_twarzy: bool, ust: Ustawienia) -> Ocena:
    """Nowy stan po jednej przeanalizowanej klatce z chwili t (sekundy)."""
    if t < o.kara_do:
        return _po_karze(o, t)

    telefon_t = t if telefon else o.telefon_t
    pozytyw = telefon or (rece_przy_twarzy and t - telefon_t <= PAMIEC_TELEFONU_S)
    okno = tuple(p for p in o.okno if p[0] > t - OKNO_S) + ((t, pozytyw),)
    udzial = sum(p for _, p in okno) / len(okno)

    luka = 0.0 if o.ostatni_t is None else max(0.0, t - o.ostatni_t)
    dt = min(luka, MAKS_KROK_S)
    seria, przerwa = o.seria_s, o.przerwa_s
    if luka > MAKS_KROK_S and seria > 0:      # brak obrazu liczy się jak przerwa
        przerwa += luka
        if przerwa >= ust.przerwa_s:
            seria, przerwa = 0.0, 0.0

    progi = CZULOSC[ust.czulosc]
    scrolluje = o.scrolluje and luka <= OKNO_S   # po długiej dziurze stan od nowa
    if len(okno) >= MIN_PROBEK:
        if not scrolluje and udzial >= progi["wejscie"]:
            scrolluje = True
        elif scrolluje and udzial < progi["wyjscie"]:
            scrolluje = False
    if scrolluje and t - telefon_t > PAMIEC_TELEFONU_S + WYGASANIE_S:
        scrolluje = False                          # telefonu dawno nie widać — koniec

    bez_telefonu = max(0.0, t - telefon_t)
    if scrolluje:
        seria, przerwa = seria + dt, 0.0
    elif o.scrolluje:
        # stan gaśnie z opóźnieniem okna — czas od ostatniego telefonu to już przerwa
        seria, przerwa = max(0.0, seria - bez_telefonu), bez_telefonu
    elif seria > 0:
        przerwa += dt
    if przerwa >= ust.przerwa_s:
        seria, przerwa = 0.0, 0.0

    nowa = Ocena(okno, scrolluje, seria, przerwa, udzial, t, telefon_t, o.kara_do, False)
    # odcinamy tylko „na gorącym uczynku”: telefon widziany przed chwilą
    if ust.czuwanie and seria >= ust.limit_s and bez_telefonu <= DOWOD_S:
        return replace(_po_karze(nowa, t), kara_do=t + ust.kara_s, odpal=True)
    return nowa

