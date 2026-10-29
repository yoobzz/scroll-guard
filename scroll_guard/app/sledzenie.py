"""Śledzenie osób między klatkami: każda osoba ma własny licznik scrollowania.

Telefon w rękach jednej osoby nie nabija czasu drugiej, a postawa „ręce przy
twarzy” (np. głowa pochylona nad laptopem) liczy się tylko wtedy, gdy TA SAMA
osoba miała przed chwilą telefon. Osoby łączymy między klatkami po pokryciu ramek
(ludzie w pokoju ruszają się wolno, analiza idzie kilka razy na sekundę).
Kara jest wspólna: gdy dowolna osoba przekroczy limit, internet znika dla domu.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from ocena import Ocena, krok
from ustawienia import Ustawienia

PROG_IOU = 0.3          # minimalne pokrycie ramek, żeby uznać, że to ta sama osoba
ZAPOMNIJ_PO_S = 15.0    # osoba niewidziana dłużej znika z pamięci


@dataclass(frozen=True)
class Slad:
    id: int
    ramka: tuple[int, int, int, int]
    ocena: Ocena
    widziany_t: float


@dataclass(frozen=True)
class OsobaWKlatce:
    ramka: tuple[int, int, int, int]
    telefon: bool
    rece_przy_twarzy: bool


@dataclass(frozen=True)
class Sledzenie:
    slady: tuple[Slad, ...] = ()
    kara_do: float = 0.0
    nastepny_id: int = 1
    odpal: bool = False
    przypisanie: tuple[int, ...] = ()   # id śladu dla każdej osoby z ostatniej klatki

    def kara_zostalo(self, t: float) -> float:
        return max(0.0, self.kara_do - t)

    def slad(self, id_: int) -> Slad | None:
        return next((s for s in self.slady if s.id == id_), None)

    def prowadzacy(self) -> Slad | None:
        """Osoba najbliżej limitu (to jej licznik pokazuje strona)."""
        return max(self.slady, key=lambda s: (s.ocena.scrolluje, s.ocena.seria_s), default=None)


def iou(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    czesc = max(0, x2 - x1) * max(0, y2 - y1)
    suma = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - czesc
    return czesc / suma if suma > 0 else 0.0


def dopasuj(ramki, slady) -> list[int | None]:
    """Zachłannie: najpierw pary o największym pokryciu. Zwraca indeks śladu albo None."""
    pary = sorted(((iou(r, s.ramka), i, j) for i, r in enumerate(ramki) for j, s in enumerate(slady)),
                  reverse=True)
    wynik: list[int | None] = [None] * len(ramki)
    zajete: set[int] = set()
    for pokrycie, i, j in pary:
        if pokrycie < PROG_IOU:
            break
        if wynik[i] is None and j not in zajete:
            wynik[i], zajete = j, zajete | {j}
    return wynik


def krok_sledzenia(st: Sledzenie, osoby: list[OsobaWKlatce], t: float, ust: Ustawienia) -> Sledzenie:
    if t < st.kara_do:
        return replace(st, slady=(), odpal=False, przypisanie=())

    przypisanie = dopasuj([o.ramka for o in osoby], st.slady)
    nowe: list[Slad] = []
    ids: list[int] = []
    nid = st.nastepny_id
    odpal = False
    for osoba, j in zip(osoby, przypisanie):
        if j is None:
            stary = Slad(nid, osoba.ramka, Ocena(), t)
            nid += 1
        else:
            stary = st.slady[j]
        ocena = krok(stary.ocena, t, osoba.telefon, osoba.rece_przy_twarzy, ust)
        odpal = odpal or ocena.odpal
        nowe.append(Slad(stary.id, osoba.ramka, ocena, t))
        ids.append(stary.id)

    uzyte = {j for j in przypisanie if j is not None}
    nowe += [s for j, s in enumerate(st.slady) if j not in uzyte and t - s.widziany_t < ZAPOMNIJ_PO_S]

    if odpal:
        return Sledzenie((), t + ust.kara_s, nid, True, ())
    return Sledzenie(tuple(nowe), st.kara_do, nid, False, tuple(ids))
