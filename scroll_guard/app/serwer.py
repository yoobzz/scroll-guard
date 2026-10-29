"""Strażnik scrollowania — strona lokalna z podglądem kamery i ustawieniami.

Start:  ./start.command   albo   .venv/bin/python serwer.py [--port 8911] [--lan]
Strona: http://127.0.0.1:8911
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import ustawienia as U
from detektor import Detektor
from straznik import Straznik

KATALOG = Path(__file__).resolve().parent
STRONA = KATALOG / "strona" / "index.html"
PORT = 8911
MAKS_CIALO = 10_000
GRANICA = b"klatka"
DOZWOLONE_HOSTY = re.compile(r"^(127\.0\.0\.1|localhost|\[::1\]|\d{1,3}(\.\d{1,3}){3}|[\w-]+\.local)(:\d+)?$")


INGRESS_BRAMA = "172.30.32.2"   # jedyny adres, z którego Home Assistant wpuszcza ruch do add-onu


def zbuduj_obsluge(straznik: Straznik, ingress: bool = False):
    class Obsluga(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format, *args):  # noqa: A002 — cisza w konsoli
            pass

        def _host_ok(self) -> bool:
            if ingress:
                # w add-onie: tylko przez Home Assistanta (ingress), nazwa hosta jest wtedy wewnętrzna
                return self.client_address[0] == INGRESS_BRAMA
            # ochrona przed DNS rebinding: tylko adresy IP / localhost / .local
            return bool(DOZWOLONE_HOSTY.match(self.headers.get("Host", "")))

        def _wyslij(self, kod: int, tresc: bytes, typ: str) -> None:
            self.send_response(kod)
            self.send_header("Content-Type", typ)
            self.send_header("Content-Length", str(len(tresc)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(tresc)

        def _json(self, kod: int, dane) -> None:
            self._wyslij(kod, json.dumps(dane, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def do_GET(self):  # noqa: N802
            if not self._host_ok():
                return self._json(403, {"blad": "zły nagłówek Host"})
            sciezka = self.path.split("?")[0]
            if sciezka == "/":
                return self._wyslij(200, STRONA.read_bytes(), "text/html; charset=utf-8")
            if sciezka == "/api/stan":
                return self._json(200, straznik.stan())
            if sciezka == "/podglad.mjpg":
                return self._strumien()
            self._json(404, {"blad": "nie ma"})

        def do_POST(self):  # noqa: N802
            # tylko application/json: przeglądarka nie wyśle tego z obcej strony bez CORS
            if not self._host_ok() or "application/json" not in self.headers.get("Content-Type", ""):
                return self._json(403, {"blad": "odrzucone"})
            dlugosc = int(self.headers.get("Content-Length") or 0)
            if dlugosc > MAKS_CIALO:
                return self._json(413, {"blad": "za duże"})
            try:
                dane = json.loads(self.rfile.read(dlugosc) or b"{}")
            except json.JSONDecodeError:
                return self._json(400, {"blad": "to nie jest JSON"})
            if self.path == "/api/ustawienia":
                try:
                    nowe = straznik.zmien_ustawienia(dane)
                except ValueError as blad:
                    return self._json(400, {"blad": str(blad)})
                return self._json(200, U.do_strony(nowe))
            if self.path == "/api/test-odciecia":
                straznik.testuj_odciecie(20)
                return self._json(200, {"ok": True})
            self._json(404, {"blad": "nie ma"})

        def _strumien(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={GRANICA.decode()}")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            nr = -1
            try:
                while True:
                    jpeg, nr = straznik.czekaj_na_jpeg(nr)
                    if not jpeg:
                        continue
                    self.wfile.write(b"--" + GRANICA + b"\r\nContent-Type: image/jpeg\r\n"
                                     + f"Content-Length: {len(jpeg)}\r\n\r\n".encode() + jpeg + b"\r\n")
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                pass
            self.close_connection = True

    return Obsluga


def main() -> int:
    p = argparse.ArgumentParser(description="Strażnik scrollowania")
    p.add_argument("--port", type=int, default=PORT)
    p.add_argument("--lan", action="store_true", help="pokaż stronę też innym w sieci (np. z telefonu)")
    p.add_argument("--zrodlo", help="nadpisz źródło obrazu (rtsp://..., plik, mac = kamera Maca)")
    p.add_argument("--opcje", type=Path, help="opcje add-onu Home Assistanta (/data/options.json)")
    p.add_argument("--ingress", action="store_true", help="tryb add-onu: słuchaj na 0.0.0.0, wpuszczaj tylko ingress HA")
    a = p.parse_args()

    ust = U.wczytaj()
    if a.opcje and a.opcje.exists():
        ust = U.zastosuj(ust, U.z_opcji_ha(json.loads(a.opcje.read_text(encoding="utf-8"))))
        U.zapisz(ust)
    if a.zrodlo:
        ust = U.zastosuj(ust, {"zrodlo": a.zrodlo})
    print("[serwer] ładuję modele…", flush=True)
    modele = Path(os.environ.get("SCROLL_GUARD_MODELS") or KATALOG / "modele")
    straznik = Straznik(ust, Detektor(modele))
    straznik.start()
    adres = "0.0.0.0" if (a.lan or a.ingress) else "127.0.0.1"
    serwer = ThreadingHTTPServer((adres, a.port), zbuduj_obsluge(straznik, ingress=a.ingress))
    serwer.daemon_threads = True
    print(f"[serwer] strona: http://127.0.0.1:{a.port}", flush=True)
    try:
        serwer.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
