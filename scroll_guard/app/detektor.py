"""Wykrywanie „siedzi w telefonie” z kamery w rogu pokoju.

Nie opiera się na dłoniach ani palcach (z daleka ich nie widać). Dwa etapy:
1. YOLO26m na całej klatce znajduje osoby (pewnie także z bliska i przy uciętym kadrze).
2. Każda osoba jest wycinana z PEŁNEJ rozdzielczości i powiększana; na wycinku
   YOLO26m szuka telefonu (klasa COCO „cell phone”), a YOLO26m-pose wyznacza
   17 punktów ciała (twarz, barki, nadgarstki, biodra). Z daleka telefon ma
   kilkadziesiąt pikseli — na pomniejszonej całej klatce by zniknął.

Telefon liczy się tylko wtedy, gdy jest przy twarzy albo w ręce tej osoby
(odległości mierzone w szerokościach barków, więc działa tak samo na siedząco,
na leżąco i z różnej odległości). Telefon leżący na stole obok — nie.
Kciuka i samego przewijania z tej odległości nie widać: wykrywamy „telefon trzymany
przed sobą”, a czas liczy ocena.py.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Zestawy modeli (SCROLL_GUARD_MODELE): „pelne” na Maca z GPU, „lekkie” na słabszy procesor
# (np. Home Assistant na mini-PC). Brakujące pliki ultralytics pobiera sam do katalogu modeli.
ZESTAWY_MODELI = {
    "pelne": ("yolo26m-pose.pt", "yolo26m.pt"),
    "lekkie": ("yolo26n-pose.pt", "yolo26s.pt"),
}
MODEL_POZY, MODEL_OBIEKTOW = ZESTAWY_MODELI.get(os.environ.get("SCROLL_GUARD_MODELE", "pelne"),
                                                ZESTAWY_MODELI["pelne"])
KLASA_TELEFON = 67
KLASA_OSOBA = 0

ROZMIAR_OSOB = 960          # na tym rozmiarze szukamy ludzi na całej klatce
PEWNOSC_OSOBY = 0.35
ROZMIAR_WYCINKA = 640       # wycinek osoby skalujemy do tego (dłuższy bok)
MARGINES_WYCINKA = 0.30     # zapas wokół osoby (ręce wyciągnięte na leżąco)
MAKS_OSOB = 4
PEWNOSC_PUNKTU = 0.35       # punkty ciała poniżej tej pewności ignorujemy

# progi w szerokościach barków (ok. 40 cm)
TELEFON_PRZY_TWARZY_SAM = 1.3   # gdy nadgarstków nie widać, wymagamy bliżej
TELEFON_PRZY_UCHU = 0.5     # telefon na twarzy/przy uchu — ręka nie musi być widoczna
TELEFON_W_RECE = 0.7        # nadgarstek w ramce telefonu albo tuż obok
ZAPAS_RAMKI_OSOBY = 0.20    # telefon musi leżeć w ramce osoby (z tym zapasem), żeby był „jej”
REKA_PRZY_TWARZY = 1.4     # poza „ręce przed twarzą” (podtrzymuje stan, gdy telefon mignie)
GLOWA_NAD_BARKAMI = 0.6     # barki bliżej górnej krawędzi kadru = twarz musi być nad kadrem
TA_SAMA_RAMKA = 0.7         # mniejsza ramka telefonu leżąca w tej części w większej = ten sam telefon

TWARZ = (0, 1, 2, 3, 4)         # nos, oczy, uszy
OCZY = (1, 2)
USZY = (3, 4)
BARKI = (5, 6)
NADGARSTKI = (9, 10)
BIODRA = (11, 12)


@dataclass(frozen=True)
class Telefon:
    ramka: tuple[int, int, int, int]
    pewnosc: float


@dataclass(frozen=True)
class Osoba:
    ramka: tuple[int, int, int, int]
    punkty: np.ndarray              # (17, 3): x, y, pewność — w pikselach klatki
    skala: float                    # szerokość barków w pikselach (szacowana)
    telefon: Telefon | None         # telefon trzymany przez tę osobę
    rece_twarz: bool
    powod: str                      # krótko, czemu tak (do podglądu)

    @property
    def z_telefonem(self) -> bool:
        return self.telefon is not None


@dataclass(frozen=True)
class Wynik:
    t: float
    rozmiar: tuple[int, int]        # (szer, wys) klatki
    osoby: tuple[Osoba, ...]
    telefony_obok: tuple[Telefon, ...]  # wykryte, ale nie w ręce/przy twarzy
    czas_ms: float

    @property
    def telefon_w_uzyciu(self) -> bool:
        return any(o.z_telefonem for o in self.osoby)

    @property
    def rece_twarz(self) -> bool:
        return any(o.rece_twarz for o in self.osoby)


# ---------- geometria (czyste funkcje) ----------

def _punkt(punkty: np.ndarray, indeksy) -> np.ndarray | None:
    """Średnia z widocznych punktów o podanych indeksach albo None."""
    widoczne = [punkty[i, :2] for i in indeksy if punkty[i, 2] >= PEWNOSC_PUNKTU]
    return np.mean(widoczne, axis=0) if widoczne else None


def _widoczne(punkty: np.ndarray, indeksy) -> list[np.ndarray]:
    return [punkty[i, :2] for i in indeksy if punkty[i, 2] >= PEWNOSC_PUNKTU]


def skala_osoby(punkty: np.ndarray, ramka) -> float:
    """Szerokość barków w pikselach; odporna na profil, leżenie i ucięty kadr.

    Proporcje do barków (~40 cm): uszy ~14 cm (0.35), źrenice ~6.5 cm (0.16).
    """
    x1, y1, x2, y2 = ramka
    kandydaci = [0.12 * max(x2 - x1, y2 - y1)]
    barki = _widoczne(punkty, BARKI)
    if len(barki) == 2:
        kandydaci.append(float(np.linalg.norm(barki[0] - barki[1])))
    srodek_barkow, srodek_bioder = _punkt(punkty, BARKI), _punkt(punkty, BIODRA)
    if srodek_barkow is not None and srodek_bioder is not None:
        kandydaci.append(0.8 * float(np.linalg.norm(srodek_barkow - srodek_bioder)))
    # z bliska barki wychodzą poza kadr — wtedy skalę daje twarz
    for (a, b), proporcja in ((USZY, 0.35), (OCZY, 0.16)):
        para = _widoczne(punkty, (a, b))
        if len(para) == 2:
            kandydaci.append(float(np.linalg.norm(para[0] - para[1])) / proporcja)
    return max(kandydaci)


def odleglosc_do_ramki(p: np.ndarray, ramka) -> float:
    """Odległość punktu od prostokąta (0, gdy w środku)."""
    x1, y1, x2, y2 = ramka
    dx = max(x1 - p[0], 0.0, p[0] - x2)
    dy = max(y1 - p[1], 0.0, p[1] - y2)
    return float(np.hypot(dx, dy))


def przodem_do_kamery(punkty: np.ndarray) -> bool:
    """Lewy bark/biodro osoby (COCO 5, 11) po prawej stronie obrazu = stoi przodem.

    Wszystkie widoczne pary muszą się zgadzać; bez żadnej pary nie wiadomo, więc False.
    """
    pary = [(punkty[l, 0] > punkty[p, 0]) for l, p in ((5, 6), (11, 12))
            if punkty[l, 2] >= PEWNOSC_PUNKTU and punkty[p, 2] >= PEWNOSC_PUNKTU]
    return bool(pary) and all(pary)


def glowa_ucieta(punkty: np.ndarray, skala: float) -> bool:
    """Barki tuż pod górną krawędzią kadru (y=0): twarz osoby jest nad kadrem, nie odwrócona."""
    barki = _widoczne(punkty, BARKI)
    return bool(barki) and min(b[1] for b in barki) < GLOWA_NAD_BARKAMI * skala


def _telefon_nad_biodrami(punkty: np.ndarray, skala: float, tel: Telefon) -> bool:
    """Środek telefonu nad linią bioder: trzymany przed sobą, nie na kolanach ani na biurku."""
    barki, biodra = _punkt(punkty, BARKI), _punkt(punkty, BIODRA)
    dol = biodra[1] if biodra is not None else barki[1] + 1.5 * skala
    return (tel.ramka[1] + tel.ramka[3]) / 2 <= dol


def ocen_telefon(punkty: np.ndarray, skala: float, tel: Telefon, prog_twarzy: float) -> tuple[bool, str]:
    """Czy ten telefon jest trzymany/oglądany przez tę osobę.

    Twarz musi być widoczna: telefon przy dłoni osoby odwróconej plecami
    to najczęściej telefon leżący na biurku obok klawiatury. Wyjątek: głowa
    ucięta górną krawędzią kadru (ktoś stoi blisko kamery) — wtedy wystarczy
    stać przodem i trzymać telefon w dłoni nad biodrami.
    """
    twarz = _punkt(punkty, TWARZ)
    nadgarstki = _widoczne(punkty, NADGARSTKI)
    d_twarz = odleglosc_do_ramki(twarz, tel.ramka) / skala if twarz is not None else None
    d_reka = min(odleglosc_do_ramki(n, tel.ramka) for n in nadgarstki) / skala if nadgarstki else None

    if d_twarz is not None and d_reka is not None:
        ok = d_twarz <= TELEFON_PRZY_UCHU or (d_reka <= TELEFON_W_RECE and d_twarz <= prog_twarzy)
        return ok, f"hand {d_reka:.1f} face {d_twarz:.1f}"
    if d_twarz is not None:
        return d_twarz <= TELEFON_PRZY_TWARZY_SAM, f"face {d_twarz:.1f}"
    if glowa_ucieta(punkty, skala) and d_reka is not None:
        if not przodem_do_kamery(punkty):
            return False, "head out of frame, back to camera"
        ok = d_reka <= TELEFON_W_RECE and _telefon_nad_biodrami(punkty, skala, tel)
        return ok, f"head out of frame, hand {d_reka:.1f}"
    return False, "no face visible"


def rece_przy_twarzy(punkty: np.ndarray, skala: float) -> bool:
    twarz = _punkt(punkty, TWARZ)
    if twarz is None:
        return False
    return any(np.linalg.norm(n - twarz) / skala <= REKA_PRZY_TWARZY
               for n in _widoczne(punkty, NADGARSTKI))


def _odleglosc_dloni(punkty: np.ndarray, tel: Telefon) -> float:
    """Odległość najbliższego nadgarstka od telefonu w pikselach (inf, gdy dłoni nie widać)."""
    nadgarstki = _widoczne(punkty, NADGARSTKI)
    return min((odleglosc_do_ramki(n, tel.ramka) for n in nadgarstki), default=float("inf"))


def _w_ramce(tel: Telefon, ramka, zapas: float = ZAPAS_RAMKI_OSOBY) -> bool:
    x1, y1, x2, y2 = ramka
    m = zapas * max(x2 - x1, y2 - y1)
    cx, cy = (tel.ramka[0] + tel.ramka[2]) / 2, (tel.ramka[1] + tel.ramka[3]) / 2
    return x1 - m <= cx <= x2 + m and y1 - m <= cy <= y2 + m


def _ten_sam(a, b) -> bool:
    """Ramki telefonów prawie się pokrywają albo mniejsza leży w większości w większej."""
    mniejsze = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return _iou(a, b) >= 0.5 or (mniejsze > 0 and _czesc_wspolna(a, b) / mniejsze >= TA_SAMA_RAMKA)


def bez_powtorzen_telefonow(telefony: list[Telefon]) -> list[Telefon]:
    """Ten sam telefon widziany w wycinkach dwóch osób liczy się raz (zostaje pewniejszy)."""
    zostaja: list[Telefon] = []
    for tel in sorted(telefony, key=lambda t: -t.pewnosc):
        if not any(_ten_sam(tel.ramka, z.ramka) for z in zostaja):
            zostaja.append(tel)
    return zostaja


def przypisz_telefony(osoby: list[tuple], telefony: list[Telefon], prog_twarzy: float):
    """Każdy telefon dostaje co najwyżej JEDNA osoba: ta, w której ramce leży i której dłoń jest najbliżej.

    `osoby`: lista (ramka, punkty, skala). Zwraca (lista (telefon|None, powód) dla osób, telefony obok).
    Bez tego osoba siedząca blisko kamery „zabierała” telefon komuś z tyłu — w jej dużej skali
    cudzy telefon wypadał w zasięgu ręki.
    """
    wynik: list[tuple[Telefon | None, str]] = [(None, "no phone")] * len(osoby)
    obok: list[Telefon] = []
    for tel in bez_powtorzen_telefonow(telefony):
        kandydaci, opisy = [], {}
        for i, (ramka, punkty, skala) in enumerate(osoby):
            if not _w_ramce(tel, ramka):
                continue
            ok, opis = ocen_telefon(punkty, skala, tel, prog_twarzy)
            opisy[i] = opis
            if ok:
                kandydaci.append((_odleglosc_dloni(punkty, tel), i, opis))
        wolni = [k for k in sorted(kandydaci) if wynik[k[1]][0] is None]
        if wolni:
            _, i, opis = wolni[0]
            wynik[i] = (tel, opis)
            continue
        obok.append(tel)
        for i, opis in opisy.items():
            if wynik[i][0] is None:
                wynik[i] = (None, f"phone nearby ({opis})")
    return wynik, obok


def wycinek(ramka, szer: int, wys: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = ramka
    m = MARGINES_WYCINKA * max(x2 - x1, y2 - y1)
    return (max(0, int(x1 - m)), max(0, int(y1 - m)),
            min(szer, int(x2 + m)), min(wys, int(y2 + m)))


# ---------- modele ----------

def _iou(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    czesc = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    suma = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - czesc
    return czesc / suma if suma > 0 else 0.0


def bez_duplikatow(ramki, prog: float = 0.6) -> list:
    """Od największej: pomija ramki leżące w większości wewnątrz już przyjętej (ta sama osoba)."""
    przyjete = []
    for b in sorted(ramki, key=lambda b: -(b[2] - b[0]) * (b[3] - b[1])):
        pole = max(1e-6, (b[2] - b[0]) * (b[3] - b[1]))
        if all(_czesc_wspolna(b, a) / pole < prog for a in przyjete):
            przyjete.append(b)
    return przyjete


def _czesc_wspolna(a, b) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


class Detektor:
    def __init__(self, katalog_modeli: Path):
        import torch
        from ultralytics import YOLO

        if torch.backends.mps.is_available():
            self.urzadzenie = "mps"
        elif torch.cuda.is_available():
            self.urzadzenie = "cuda"
        else:
            self.urzadzenie = "cpu"
        katalog_modeli.mkdir(parents=True, exist_ok=True)
        self._poza = YOLO(str(katalog_modeli / MODEL_POZY))
        self._obiekty = YOLO(str(katalog_modeli / MODEL_OBIEKTOW))

    def _predict(self, model, obrazy, **kw):
        return model.predict(obrazy, device=self.urzadzenie, verbose=False, **kw)

    def _ramki_osob(self, klatka: np.ndarray) -> list[tuple[int, int, int, int]]:
        r = self._predict(self._obiekty, klatka, imgsz=ROZMIAR_OSOB, conf=PEWNOSC_OSOBY,
                          classes=[KLASA_OSOBA])[0]
        ramki = bez_duplikatow(list(r.boxes.xyxy.cpu().numpy()))
        return [tuple(int(v) for v in b) for b in ramki[:MAKS_OSOB]]

    def _wycinki(self, klatka: np.ndarray, okna):
        import cv2

        obrazy, skale = [], []
        for x1, y1, x2, y2 in okna:
            fragment = klatka[y1:y2, x1:x2]
            s = ROZMIAR_WYCINKA / max(fragment.shape[:2])
            interp = cv2.INTER_CUBIC if s > 1 else cv2.INTER_AREA
            obrazy.append(cv2.resize(fragment, None, fx=s, fy=s, interpolation=interp))
            skale.append(s)
        return obrazy, skale

    def _telefony(self, obrazy, okna, skale, pewnosc: float) -> list[list[Telefon]]:
        """Telefony w powiększonych wycinkach, przeliczone na współrzędne klatki."""
        wyniki = self._predict(self._obiekty, obrazy, imgsz=ROZMIAR_WYCINKA, conf=pewnosc,
                               classes=[KLASA_TELEFON])
        telefony = []
        for (x1, y1, _, _), s, r in zip(okna, skale, wyniki):
            lista = []
            for ramka, conf in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy()):
                bx = ramka / s + np.array([x1, y1, x1, y1])
                lista.append(Telefon(tuple(int(v) for v in bx), float(conf)))
            telefony.append(lista)
        return telefony

    def _punkty(self, obrazy, okna, skale, ramki) -> list[np.ndarray]:
        """Punkty ciała z modelu pozy na wycinku — ta poza, która najlepiej pokrywa się z osobą."""
        wyniki = self._predict(self._poza, obrazy, imgsz=ROZMIAR_WYCINKA, conf=0.05,
                               classes=[KLASA_OSOBA])
        lista = []
        for (x1, y1, _, _), s, ramka, r in zip(okna, skale, ramki, wyniki):
            punkty = np.zeros((17, 3))
            if r.boxes is not None and len(r.boxes):
                w_wycinku = [(v - o) * s for v, o in zip(ramka, (x1, y1, x1, y1))]
                ious = [_iou(w_wycinku, b) for b in r.boxes.xyxy.cpu().numpy()]
                najlepsza = int(np.argmax(ious))
                if ious[najlepsza] >= 0.2:
                    punkty = r.keypoints.data[najlepsza].cpu().numpy().copy()
                    punkty[:, :2] = punkty[:, :2] / s + np.array([x1, y1])
            lista.append(punkty)
        return lista

    def analizuj(self, klatka: np.ndarray, pewnosc_tel: float, prog_twarzy: float) -> Wynik:
        start = time.perf_counter()
        wys, szer = klatka.shape[:2]
        ramki = self._ramki_osob(klatka)
        okna = [wycinek(ramka, szer, wys) for ramka in ramki]
        obrazy, skale = self._wycinki(klatka, okna)
        telefony_okien = self._telefony(obrazy, okna, skale, pewnosc_tel) if obrazy else []
        punkty_osob = self._punkty(obrazy, okna, skale, ramki) if obrazy else []

        dane = [(ramka, punkty, skala_osoby(punkty, ramka)) for ramka, punkty in zip(ramki, punkty_osob)]
        wszystkie = [t for lista in telefony_okien for t in lista]
        przydzial, obok = przypisz_telefony(dane, wszystkie, prog_twarzy)
        osoby = [Osoba(ramka, punkty, skala, tel, rece_przy_twarzy(punkty, skala), powod)
                 for (ramka, punkty, skala), (tel, powod) in zip(dane, przydzial)]
        return Wynik(time.time(), (szer, wys), tuple(osoby), tuple(obok),
                     (time.perf_counter() - start) * 1000)
