"""Polecenia do ESP z przekaźnikiem na zasilaniu routera (firmware: firmware/scroll_guard_relay).

Protokół:
  GET http://<esp>/ban?s=<sekundy>[&key=<klucz>]   ESP odcina prąd routera i SAM go przywraca po czasie
  GET http://<esp>/unban[?key=<klucz>]             przywraca od razu
  GET http://<esp>/status                          {"banned":..., "remaining_s":...}
ESP musi liczyć czas samodzielnie: po odcięciu routera znika Wi-Fi i nikt się
z nim nie dogada, dopóki router nie wstanie.
Bez ustawionego ESP działa tryb próbny: wszystko się liczy, nic nie jest odcinane.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

PROBY = 3
ODSTEP_PROB_S = 2.0
LIMIT_S = 3.0
CO_ILE_STATUS_S = 30.0


def adres(esp: str, sciezka: str, token: str = "", **parametry) -> str:
    """http://<esp><sciezka>?... z kluczem, jeśli jest ustawiony."""
    if token:
        parametry["key"] = token
    zapytanie = urllib.parse.urlencode(parametry)
    return f"http://{esp}{sciezka}" + (f"?{zapytanie}" if zapytanie else "")


class Odcinacz:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ostatnio: dict = {}
        self._esp: dict = {}

    def stan(self) -> dict:
        with self._lock:
            return {**self._ostatnio, "esp": dict(self._esp)}

    def odetnij(self, esp: str, sekundy: int, token: str = "") -> None:
        self._w_tle(adres(esp, "/ban", token, s=int(sekundy)) if esp else "", f"cut for {int(sekundy)} s")

    def przywroc(self, esp: str, token: str = "") -> None:
        self._w_tle(adres(esp, "/unban", token) if esp else "", "restore")

    def pilnuj_statusu(self, pobierz_esp) -> None:
        """Wątek w tle: co 30 s pyta ESP o stan (pobierz_esp() -> adres albo "")."""
        threading.Thread(target=self._petla_statusu, args=(pobierz_esp,), daemon=True, name="esp").start()

    def _petla_statusu(self, pobierz_esp) -> None:
        while True:
            esp = pobierz_esp()
            if esp:
                try:
                    with urllib.request.urlopen(adres(esp, "/status"), timeout=LIMIT_S) as odp:
                        dane = json.loads(odp.read(500).decode("utf-8", "replace"))
                    stan = {"online": True, "banned": bool(dane.get("banned")),
                            "remaining_s": int(dane.get("remaining_s") or 0), "kiedy": time.time()}
                except (urllib.error.URLError, OSError, ValueError):
                    stan = {"online": False, "kiedy": time.time()}
            else:
                stan = {}
            with self._lock:
                self._esp = stan
            time.sleep(CO_ILE_STATUS_S)

    def _w_tle(self, url: str, opis: str) -> None:
        threading.Thread(target=self._wyslij, args=(url, opis), daemon=True).start()

    def _zapisz(self, opis: str, wynik: str, ok: bool) -> None:
        with self._lock:
            self._ostatnio = {"co": opis, "wynik": wynik, "ok": ok, "kiedy": time.time()}
        print(f"[relay] {opis}: {wynik}", flush=True)

    def _wyslij(self, url: str, opis: str) -> None:
        if not url:
            self._zapisz(opis, "dry run: no ESP address, nothing was cut", False)
            return
        ostatni_blad = ""
        for proba in range(1, PROBY + 1):
            try:
                with urllib.request.urlopen(url, timeout=LIMIT_S) as odp:
                    tresc = odp.read(300).decode("utf-8", "replace").strip()
                self._zapisz(opis, f"ESP replied: {tresc or odp.status}", True)
                return
            except urllib.error.HTTPError as blad:
                ostatni_blad = "wrong ESP key" if blad.code == 403 else f"HTTP {blad.code}"
                break                                  # ESP odpowiedział — ponawianie nic nie da
            except (urllib.error.URLError, OSError) as blad:
                ostatni_blad = str(getattr(blad, "reason", blad))
                if proba < PROBY:
                    time.sleep(ODSTEP_PROB_S)
        self._zapisz(opis, f"ESP did not take the command ({ostatni_blad})", False)
