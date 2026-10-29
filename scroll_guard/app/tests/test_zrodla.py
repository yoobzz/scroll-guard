"""Testy rozpoznawania źródła obrazu i wyboru wbudowanej kamery laptopa."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from zrodla import kamera_wbudowana, rodzaj_zrodla, urzadzenia_wideo  # noqa: E402

LISTA_FFMPEG = """\
[AVFoundation indev @ 0xbd0c38140] AVFoundation video devices:
[AVFoundation indev @ 0xbd0c38140] [0] OBS Virtual Camera
[AVFoundation indev @ 0xbd0c38140] [1] Kasia's iPhone Camera
[AVFoundation indev @ 0xbd0c38140] [2] MacBook Air Desk View Camera
[AVFoundation indev @ 0xbd0c38140] [3] MacBook Air Camera
[AVFoundation indev @ 0xbd0c38140] [4] Capture screen 0
[AVFoundation indev @ 0xbd0c38140] AVFoundation audio devices:
[AVFoundation indev @ 0xbd0c38140] [0] MacBook Air Microphone
Error opening input file .
"""


class TestZrodla(unittest.TestCase):
    def test_lista_urzadzen_tylko_wideo(self):
        self.assertEqual(urzadzenia_wideo(LISTA_FFMPEG), [
            "OBS Virtual Camera", "Kasia's iPhone Camera", "MacBook Air Desk View Camera",
            "MacBook Air Camera", "Capture screen 0"])

    def test_wbudowana_kamera_wygrywa_z_wirtualnymi_i_telefonem(self):
        self.assertEqual(kamera_wbudowana(urzadzenia_wideo(LISTA_FFMPEG)), "MacBook Air Camera")

    def test_starszy_mac_facetime(self):
        self.assertEqual(kamera_wbudowana(["Capture screen 0", "FaceTime HD Camera (Built-in)"]),
                         "FaceTime HD Camera (Built-in)")

    def test_bez_wbudowanej_bierze_pierwsza_prawdziwa(self):
        self.assertEqual(kamera_wbudowana(["OBS Virtual Camera", "Logitech BRIO", "Capture screen 0"]),
                         "Logitech BRIO")

    def test_same_wirtualne_to_brak(self):
        self.assertIsNone(kamera_wbudowana(["OBS Virtual Camera", "Capture screen 0"]))

    def test_rodzaje(self):
        self.assertEqual(rodzaj_zrodla(""), "")
        self.assertEqual(rodzaj_zrodla("laptop"), "laptop")
        self.assertEqual(rodzaj_zrodla("mac"), "laptop")
        self.assertEqual(rodzaj_zrodla("mac:FaceTime HD Camera"), "laptop")
        self.assertEqual(rodzaj_zrodla("rtsp://u:p@192.168.0.20:554/stream1"), "rtsp")
        self.assertEqual(rodzaj_zrodla("http://192.168.0.60:81/stream"), "http")
        self.assertEqual(rodzaj_zrodla("0"), "indeks")
        self.assertEqual(rodzaj_zrodla("~/test.mp4"), "plik")


if __name__ == "__main__":
    unittest.main()
