"""Testy styku z ESP i Home Assistantem: adresy z kluczem, opcje add-onu, encje."""
from __future__ import annotations

import sys
import unittest
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ha import encje  # noqa: E402
from odciecie import adres  # noqa: E402
from ustawienia import MASKA, Ustawienia, do_strony, z_opcji_ha, zastosuj  # noqa: E402


class TestEsp(unittest.TestCase):
    def test_adres_bez_klucza_i_z_kluczem(self):
        self.assertEqual(adres("192.168.0.50", "/ban", s=900), "http://192.168.0.50/ban?s=900")
        self.assertEqual(adres("scroll-guard.local", "/ban", "abc_1", s=60),
                         "http://scroll-guard.local/ban?s=60&key=abc_1")
        self.assertEqual(adres("10.0.0.2:8080", "/unban", "k"), "http://10.0.0.2:8080/unban?key=k")
        self.assertEqual(adres("10.0.0.2", "/status"), "http://10.0.0.2/status")

    def test_klucz_maskowany_i_walidowany(self):
        u = zastosuj(Ustawienia(), {"esp_token": "tajny-klucz_1"})
        self.assertEqual(do_strony(u)["esp_token"], MASKA)
        self.assertEqual(zastosuj(u, {"esp_token": MASKA}).esp_token, "tajny-klucz_1")
        self.assertEqual(zastosuj(u, {"esp_token": ""}).esp_token, "")
        with self.assertRaises(ValueError):
            zastosuj(u, {"esp_token": "spacja nie"})


class TestHomeAssistant(unittest.TestCase):
    def test_opcje_addonu_na_ustawienia(self):
        dane = z_opcji_ha({"rtsp_url": "rtsp://u:p@10.0.0.9:554/stream1", "esp_host": "", "esp_token": "",
                           "limit_minutes": 15, "ban_minutes": 30, "break_seconds": 60,
                           "sensitivity": "sensitive", "enforce": False})
        u = zastosuj(Ustawienia(esp="10.0.0.2"), dane)
        self.assertEqual(u.zrodlo, "rtsp://u:p@10.0.0.9:554/stream1")
        self.assertEqual(u.esp, "10.0.0.2")             # pusta opcja nie kasuje ustawienia ze strony
        self.assertEqual((u.limit_s, u.kara_s, u.przerwa_s), (900, 1800, 60))
        self.assertEqual(u.czulosc, "czula")
        self.assertFalse(u.czuwanie)

    def test_encje(self):
        stan = {"scrolluje": True, "kara_zostalo_s": 0, "seria_s": 125.7, "osoby": 2,
                "ustawienia": asdict(Ustawienia())}
        e = encje(stan)
        self.assertEqual(e["binary_sensor.scroll_guard_scrolling"]["state"], "on")
        self.assertEqual(e["binary_sensor.scroll_guard_internet_cut"]["state"], "off")
        self.assertEqual(e["sensor.scroll_guard_streak"]["state"], 125)
        self.assertEqual(e["sensor.scroll_guard_people"]["state"], 2)


if __name__ == "__main__":
    unittest.main()
