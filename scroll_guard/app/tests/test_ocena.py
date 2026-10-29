"""Testy logiki czasu i ustawień. Uruchom: python -m unittest discover -s tests"""
from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ocena import Ocena, krok  # noqa: E402
from ustawienia import Ustawienia, zamaskuj_zrodlo, zastosuj  # noqa: E402

FPS = 3
UST = Ustawienia(limit_s=60, kara_s=120, przerwa_s=45, czulosc="normalna")


def przewin(o: Ocena, od: float, do: float, wzor, ust=UST, rece=False):
    """Podaje klatki co 1/FPS s; wzor(i) mówi, czy na i-tej klatce jest telefon."""
    odpalenia = []
    i, t = 0, od
    while t < do:
        o = krok(o, t, wzor(i), rece, ust)
        if o.odpal:
            odpalenia.append(t)
        i += 1
        t = od + i / FPS
    return o, odpalenia


ZAWSZE = lambda i: True       # noqa: E731
NIGDY = lambda i: False       # noqa: E731


class TestOcena(unittest.TestCase):
    def test_ciagle_scrollowanie_odcina_raz_przy_limicie(self):
        _, odp = przewin(Ocena(), 0, 100, ZAWSZE)
        self.assertEqual(len(odp), 1)
        self.assertAlmostEqual(odp[0], 60.7, delta=1.0)

    def test_wolna_analiza_co_3_s_liczy_pelny_czas(self):
        # add-on na słabym procesorze: jedna klatka co 3 s, a limit ma minąć po ~60 s, nie później
        o, odp = Ocena(), []
        for t in range(0, 120, 3):
            o = krok(o, float(t), True, False, UST)
            if o.odpal:
                odp.append(t)
        self.assertEqual(len(odp), 1)
        self.assertLessEqual(odp[0], 72)

    def test_bez_telefonu_nic_sie_nie_dzieje(self):
        o, odp = przewin(Ocena(), 0, 300, NIGDY)
        self.assertEqual(odp, [])
        self.assertFalse(o.scrolluje)
        self.assertEqual(o.seria_s, 0)

    def test_krotka_przerwa_nie_zeruje_licznika(self):
        o, odp = przewin(Ocena(), 0, 40, ZAWSZE)
        o, odp2 = przewin(o, 40, 60, NIGDY)
        self.assertGreater(o.seria_s, 25)
        o, odp3 = przewin(o, 60, 100, ZAWSZE)
        self.assertEqual(len(odp + odp2 + odp3), 1)

    def test_dluga_przerwa_zeruje_licznik(self):
        o, _ = przewin(Ocena(), 0, 40, ZAWSZE)
        o, _ = przewin(o, 40, 110, NIGDY)
        self.assertEqual(o.seria_s, 0)
        _, odp = przewin(o, 110, 150, ZAWSZE)
        self.assertEqual(odp, [])

    def test_telefon_widoczny_tylko_na_czesci_klatek_wystarcza(self):
        # telefon złapany na 2 z 5 klatek (40%) — normalna czułość ma to uznać
        _, odp = przewin(Ocena(), 0, 100, lambda i: i % 5 in (0, 2))
        self.assertEqual(len(odp), 1)

    def test_rzadkie_mignięcia_nie_wystarczaja(self):
        # pojedyncza fałszywa klatka co 5 s
        _, odp = przewin(Ocena(), 0, 300, lambda i: i % 15 == 0)
        self.assertEqual(odp, [])

    def test_w_czasie_kary_nie_liczy_i_potem_od_zera(self):
        o, odp = przewin(Ocena(), 0, 61, ZAWSZE)
        self.assertEqual(len(odp), 1)
        kara_do = o.kara_do
        o, odp2 = przewin(o, 61, kara_do, ZAWSZE)
        self.assertEqual(odp2, [])
        self.assertEqual(o.seria_s, 0)
        o, odp3 = przewin(o, kara_do, kara_do + 30, ZAWSZE)
        self.assertEqual(odp3, [])
        self.assertGreater(o.seria_s, 20)

    def test_tylko_podglad_nie_odcina(self):
        ust = replace(UST, czuwanie=False)
        o, odp = przewin(Ocena(), 0, 200, ZAWSZE, ust=ust)
        self.assertEqual(odp, [])
        self.assertGreater(o.seria_s, 150)

    def test_rece_przy_twarzy_bez_telefonu_nie_licza(self):
        o, _ = przewin(Ocena(), 0, 30, NIGDY, rece=True)
        self.assertFalse(o.scrolluje)

    def test_rece_przy_twarzy_podtrzymuja_po_zobaczeniu_telefonu(self):
        o, _ = przewin(Ocena(), 0, 10, ZAWSZE)
        o, _ = przewin(o, 10, 16, NIGDY, rece=True)
        self.assertTrue(o.scrolluje)

    def test_ksiazka_po_telefonie_szybko_konczy_scrollowanie(self):
        # odkłada telefon i czyta: ręce przy twarzy, telefonu brak
        o, _ = przewin(Ocena(), 0, 20, ZAWSZE)
        stany = []
        t = 20.0
        while t < 60:
            o = krok(o, t, False, True, UST)
            stany.append((t, o.scrolluje))
            t += 1 / FPS
        koniec = next(t for t, s in stany if not s)
        self.assertLess(koniec - 20, 13)

    def test_limit_w_czasie_wygaszania_nie_odcina(self):
        # 55 s z telefonem, potem książka: stan gaśnie kilka sekund, ale limit 60 s nie może paść
        o, odp = przewin(Ocena(), 0, 55, ZAWSZE)
        t, odp2 = 55.0, []
        while t < 90:
            o = krok(o, t, False, True, UST)
            if o.odpal:
                odp2.append(t)
            t += 1 / FPS
        self.assertEqual(odp + odp2, [])
        self.assertFalse(o.scrolluje)
        self.assertLess(o.seria_s, 56)

    def test_dziura_w_obrazie_liczy_sie_jak_przerwa(self):
        o, _ = przewin(Ocena(), 0, 40, ZAWSZE)
        o = krok(o, 140, True, False, UST)       # 100 s bez klatek
        self.assertLess(o.seria_s, 3)


class TestUstawienia(unittest.TestCase):
    def test_ograniczenia_i_walidacja(self):
        u = zastosuj(Ustawienia(), {"limit_s": 1, "kara_s": 10**9, "esp": "http://192.168.0.50/"})
        self.assertEqual(u.limit_s, 10)
        self.assertEqual(u.kara_s, 4 * 3600)
        self.assertEqual(u.esp, "192.168.0.50")
        with self.assertRaises(ValueError):
            zastosuj(Ustawienia(), {"esp": "evil.com/x?y"})
        with self.assertRaises(ValueError):
            zastosuj(Ustawienia(), {"czulosc": "turbo"})
        with self.assertRaises(ValueError):
            zastosuj(Ustawienia(), {"limit_s": "dużo"})

    def test_maskowanie_hasla_i_brak_nadpisania(self):
        u = zastosuj(Ustawienia(), {"zrodlo": "rtsp://admin:tajne@192.168.0.9:554/stream1"})
        maska = zamaskuj_zrodlo(u.zrodlo)
        self.assertNotIn("tajne", maska)
        self.assertEqual(zastosuj(u, {"zrodlo": maska}).zrodlo, u.zrodlo)


if __name__ == "__main__":
    unittest.main()
