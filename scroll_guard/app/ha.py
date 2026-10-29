"""Home Assistant: encje stanu i zdarzenie przy odcięciu.

Działa tylko w add-onie (Supervisor podaje SUPERVISOR_TOKEN i adres http://supervisor).
Encje (do automatyzacji, np. wyłączenie gniazdka z routerem zamiast ESP):
  binary_sensor.scroll_guard_scrolling     ktoś teraz scrolluje
  binary_sensor.scroll_guard_internet_cut  trwa kara
  sensor.scroll_guard_streak               sekundy bieżącej serii (osoba najbliżej limitu)
  sensor.scroll_guard_ban_remaining        sekundy do końca kary
  sensor.scroll_guard_people               osoby w kadrze
Zdarzenie przy każdym odcięciu: scroll_guard_ban {"seconds": N}.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request

API = "http://supervisor/core/api"
CO_ILE_S = 5.0
ODSWIEZ_I_TAK_S = 60.0


def encje(stan: dict) -> dict[str, dict]:
    """Stan strażnika -> {entity_id: {"state", "attributes"}} dla REST API Home Assistanta."""
    return {
        "binary_sensor.scroll_guard_scrolling": {
            "state": "on" if stan["scrolluje"] else "off",
            "attributes": {"friendly_name": "Scroll Guard scrolling", "icon": "mdi:cellphone-text"}},
        "binary_sensor.scroll_guard_internet_cut": {
            "state": "on" if stan["kara_zostalo_s"] > 0 else "off",
            "attributes": {"friendly_name": "Scroll Guard internet cut", "icon": "mdi:wifi-off"}},
        "sensor.scroll_guard_streak": {
            "state": int(stan["seria_s"]),
            "attributes": {"friendly_name": "Scroll Guard streak", "unit_of_measurement": "s",
                           "limit_s": stan["ustawienia"]["limit_s"], "icon": "mdi:timer-sand"}},
        "sensor.scroll_guard_ban_remaining": {
            "state": int(stan["kara_zostalo_s"]),
            "attributes": {"friendly_name": "Scroll Guard ban remaining", "unit_of_measurement": "s",
                           "icon": "mdi:timer-off-outline"}},
        "sensor.scroll_guard_people": {
            "state": int(stan["osoby"]),
            "attributes": {"friendly_name": "Scroll Guard people in view", "icon": "mdi:account-multiple"}},
    }


class HomeAssistant:
    def __init__(self) -> None:
        self._token = os.environ.get("SUPERVISOR_TOKEN", "")
        self._wyslane: dict[str, tuple] = {}
        self._blad_zgloszony = False

    @property
    def aktywny(self) -> bool:
        return bool(self._token)

    def _post(self, sciezka: str, dane: dict) -> None:
        zadanie = urllib.request.Request(
            API + sciezka, data=json.dumps(dane).encode(), method="POST",
            headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(zadanie, timeout=5):
            pass

    def zdarzenie_odciecia(self, sekundy: int) -> None:
        if self.aktywny:
            threading.Thread(target=self._bezpiecznie, args=("/events/scroll_guard_ban", {"seconds": sekundy}),
                             daemon=True).start()

    def publikuj(self, pobierz_stan) -> None:
        if self.aktywny:
            threading.Thread(target=self._petla, args=(pobierz_stan,), daemon=True, name="ha").start()

    def _bezpiecznie(self, sciezka: str, dane: dict) -> bool:
        try:
            self._post(sciezka, dane)
            self._blad_zgloszony = False
            return True
        except (urllib.error.URLError, OSError) as blad:
            if not self._blad_zgloszony:
                print(f"[ha] Home Assistant did not accept the data: {blad}", flush=True)
                self._blad_zgloszony = True
            return False

    def _petla(self, pobierz_stan) -> None:
        while True:
            teraz = time.time()
            for entity_id, dane in encje(pobierz_stan()).items():
                klucz = (dane["state"], json.dumps(dane["attributes"], sort_keys=True))
                poprzednie = self._wyslane.get(entity_id)
                if poprzednie and poprzednie[0] == klucz and teraz - poprzednie[1] < ODSWIEZ_I_TAK_S:
                    continue
                if self._bezpiecznie(f"/states/{entity_id}", dane):
                    self._wyslane[entity_id] = (klucz, teraz)
            time.sleep(CO_ILE_S)
