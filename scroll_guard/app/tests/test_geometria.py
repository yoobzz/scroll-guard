"""Testy geometrii: kiedy telefon jest „w użyciu”, a kiedy tylko leży obok."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from detektor import (Telefon, bez_duplikatow, ocen_telefon, przypisz_telefony,  # noqa: E402
                      rece_przy_twarzy, skala_osoby)

PROG = 1.9   # normalna czułość


def osoba(twarz=(500, 300), nadgarstek=(520, 420), barki=((440, 380), (560, 380)), biodra=((460, 600), (540, 600))):
    """17 punktów COCO; niewymienione mają pewność 0 (niewidoczne)."""
    p = np.zeros((17, 3))
    if twarz is not None:
        p[0] = (*twarz, 0.9)                       # nos
        p[1] = (twarz[0] - 10, twarz[1] - 8, 0.9)  # oczy
        p[2] = (twarz[0] + 10, twarz[1] - 8, 0.9)
    p[5], p[6] = (*barki[0], 0.9), (*barki[1], 0.9)
    p[11], p[12] = (*biodra[0], 0.9), (*biodra[1], 0.9)
    if nadgarstek is not None:
        p[9] = (*nadgarstek, 0.9)
    return p


RAMKA = (400, 250, 600, 700)


class TestGeometria(unittest.TestCase):
    def setUp(self):
        self.p = osoba()
        self.s = skala_osoby(self.p, RAMKA)

    def test_skala_to_szerokosc_barkow(self):
        self.assertAlmostEqual(self.s, 176, delta=1)   # 0.8 * tułów 220 > barki 120

    def test_telefon_w_dloni_przed_twarza(self):
        ok, _ = ocen_telefon(self.p, self.s, Telefon((505, 395, 535, 430), 0.8), PROG)
        self.assertTrue(ok)

    def test_telefon_przy_uchu_bez_widocznej_dloni(self):
        p = osoba(nadgarstek=None)
        ok, _ = ocen_telefon(p, self.s, Telefon((505, 280, 530, 320), 0.8), PROG)
        self.assertTrue(ok)

    def test_telefon_przy_dloni_tylem_do_kamery_nie_liczy_sie(self):
        p = osoba(twarz=None)
        ok, powod = ocen_telefon(p, self.s, Telefon((505, 395, 535, 430), 0.8), PROG)
        self.assertFalse(ok)
        self.assertIn("twarzy", powod)

    def test_telefon_na_biurku_daleko_od_twarzy(self):
        # dłoń na klawiaturze, telefon obok niej, ale 2.5 barku od twarzy
        p = osoba(nadgarstek=(560, 740))
        ok, _ = ocen_telefon(p, self.s, Telefon((580, 730, 620, 760), 0.9), PROG)
        self.assertFalse(ok)

    def test_telefon_daleko_od_dloni(self):
        ok, _ = ocen_telefon(self.p, self.s, Telefon((700, 300, 730, 340), 0.9), PROG)
        self.assertFalse(ok)

    def test_skala_z_twarzy_gdy_barki_poza_kadrem(self):
        # zbliżenie z laptopa: widać tylko twarz (oczy 60 px od siebie), barków i bioder brak
        p = np.zeros((17, 3))
        p[0] = (640, 300, 0.9)
        p[1], p[2] = (610, 270, 0.9), (670, 270, 0.9)
        self.assertAlmostEqual(skala_osoby(p, (300, 0, 1000, 720)), 60 / 0.16, delta=1)

    def test_ta_sama_osoba_dwa_razy_to_jedna(self):
        ramki = [(350, 40, 1270, 720), (110, 10, 1100, 720), (360, 50, 900, 700), (1500, 0, 1800, 700)]
        wynik = bez_duplikatow(ramki)
        self.assertEqual(wynik[0], (110, 10, 1100, 720))
        self.assertIn((1500, 0, 1800, 700), wynik)
        self.assertNotIn((360, 50, 900, 700), wynik)

    def test_telefon_kolegi_nie_trafia_do_osoby_blisko_kamery(self):
        # ty: duża osoba blisko kamery (barki 800 px), kolega z tyłu z telefonem w dłoni
        ty_p = osoba(twarz=(1300, 300), nadgarstek=(900, 1000), barki=((900, 600), (1700, 600)),
                     biodra=((1000, 1300), (1600, 1300)))
        ty_ramka = (700, 0, 1900, 1440)
        kol_p = osoba(twarz=(300, 300), nadgarstek=(420, 520), barki=((220, 420), (380, 420)),
                      biodra=((240, 700), (360, 700)))
        kol_ramka = (150, 150, 450, 800)
        tel = Telefon((400, 490, 450, 560), 0.8)   # w dłoni kolegi, poza twoją ramką
        dane = [(ty_ramka, ty_p, skala_osoby(ty_p, ty_ramka)), (kol_ramka, kol_p, skala_osoby(kol_p, kol_ramka))]
        przydzial, obok = przypisz_telefony(dane, [tel], PROG)
        self.assertIsNone(przydzial[0][0])
        self.assertIs(przydzial[1][0], tel)
        self.assertEqual(obok, [])

    def test_ten_sam_telefon_z_dwoch_wycinkow_liczy_sie_raz(self):
        a, b = Telefon((505, 395, 535, 430), 0.8), Telefon((506, 396, 534, 431), 0.6)
        dane = [(RAMKA, self.p, self.s)]
        przydzial, obok = przypisz_telefony(dane, [a, b], PROG)
        self.assertIs(przydzial[0][0], a)
        self.assertEqual(obok, [])

    def test_rece_przy_twarzy(self):
        self.assertTrue(rece_przy_twarzy(self.p, self.s))
        self.assertFalse(rece_przy_twarzy(osoba(nadgarstek=(520, 690)), self.s))


if __name__ == "__main__":
    unittest.main()
