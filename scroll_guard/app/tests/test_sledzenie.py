"""Testy śledzenia: telefon jednej osoby nie nabija licznika drugiej."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sledzenie import OsobaWKlatce, Sledzenie, dopasuj, krok_sledzenia  # noqa: E402
from ustawienia import Ustawienia  # noqa: E402

UST = Ustawienia(limit_s=60, kara_s=120, przerwa_s=45, czulosc="normalna")
FPS = 3
TY = (900, 100, 1700, 1080)        # duża osoba przy laptopie
KOLEGA = (0, 0, 400, 700)          # osoba z boku


def przewin(st, od, do, osoby_fn):
    odpalenia, i, t = [], 0, od
    while t < do:
        st = krok_sledzenia(st, osoby_fn(i), t, UST)
        if st.odpal:
            odpalenia.append(t)
        i += 1
        t = od + i / FPS
    return st, odpalenia


class TestSledzenie(unittest.TestCase):
    def test_telefon_kolegi_nie_nabija_twojego_licznika(self):
        # ty: głowa pochylona nad laptopem (ręce blisko twarzy), bez telefonu; kolega scrolluje
        osoby = lambda i: [OsobaWKlatce(TY, False, True), OsobaWKlatce(KOLEGA, True, True)]  # noqa: E731
        st, _ = przewin(Sledzenie(), 0, 30, osoby)
        ty = st.slad(st.przypisanie[0])
        kolega = st.slad(st.przypisanie[1])
        self.assertFalse(ty.ocena.scrolluje)
        self.assertEqual(ty.ocena.seria_s, 0)
        self.assertTrue(kolega.ocena.scrolluje)
        self.assertGreater(kolega.ocena.seria_s, 20)

    def test_pochylona_glowa_sama_nic_nie_liczy(self):
        st, odp = przewin(Sledzenie(), 0, 200, lambda i: [OsobaWKlatce(TY, False, True)])
        self.assertEqual(odp, [])
        self.assertEqual(st.slad(st.przypisanie[0]).ocena.seria_s, 0)

    def test_kara_gdy_ktokolwiek_przekroczy_limit_i_wspolna(self):
        osoby = lambda i: [OsobaWKlatce(TY, False, False), OsobaWKlatce(KOLEGA, True, False)]  # noqa: E731
        st, odp = przewin(Sledzenie(), 0, 100, osoby)
        self.assertEqual(len(odp), 1)
        self.assertGreater(st.kara_zostalo(odp[0] + 1), 100)

    def test_ta_sama_osoba_po_lekkim_ruchu(self):
        # ramka przesuwa się o kilka pikseli na klatkę — licznik się nie zeruje
        osoby = lambda i: [OsobaWKlatce((900 + i, 100, 1700 + i, 1080), True, False)]  # noqa: E731
        st, _ = przewin(Sledzenie(), 0, 40, osoby)
        self.assertEqual(len(st.slady), 1)
        self.assertGreater(st.slady[0].ocena.seria_s, 30)

    def test_krotkie_znikniecie_z_kadru_nie_zeruje(self):
        osoby_tel = lambda i: [OsobaWKlatce(TY, True, False)]  # noqa: E731
        st, _ = przewin(Sledzenie(), 0, 30, osoby_tel)
        id_ = st.przypisanie[0]
        st, _ = przewin(st, 30, 35, lambda i: [])           # 5 s bez wykrycia osoby
        st, _ = przewin(st, 35, 45, osoby_tel)
        self.assertEqual(st.przypisanie[0], id_)
        self.assertGreater(st.slad(id_).ocena.seria_s, 30)

    def test_dopasowanie_nie_laczy_dalekich_ramek(self):
        st, _ = przewin(Sledzenie(), 0, 2, lambda i: [OsobaWKlatce(TY, False, False)])
        self.assertEqual(dopasuj([KOLEGA], st.slady), [None])
        self.assertEqual(dopasuj([TY], st.slady), [0])


if __name__ == "__main__":
    unittest.main()
