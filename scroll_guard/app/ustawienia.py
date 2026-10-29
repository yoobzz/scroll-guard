"""Ustawienia strażnika: wartości domyślne, walidacja, zapis do ustawienia.json."""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

KATALOG = Path(__file__).resolve().parent
# W add-onie Home Assistanta dane trwałe muszą leżeć w /data (SCROLL_GUARD_DATA=/data).
KATALOG_DANYCH = Path(os.environ.get("SCROLL_GUARD_DATA") or KATALOG)
PLIK = KATALOG_DANYCH / "ustawienia.json"
MASKA = "•••"

# Czułość = jak duża część klatek z ostatnich sekund musi pokazywać telefon,
# żeby uznać, że scrollujesz (wejście), i jak mała, żeby uznać, że przestałeś;
# pewność wykrycia telefonu; jak daleko od twarzy (w szerokościach barków) może być
# telefon w ręce — dalej łatwiej pomylić z telefonem leżącym na biurku.
CZULOSC = {
    "ostrozna": {"wejscie": 0.45, "wyjscie": 0.20, "pewnosc_tel": 0.35, "twarz": 1.5},
    "normalna": {"wejscie": 0.30, "wyjscie": 0.12, "pewnosc_tel": 0.25, "twarz": 1.9},
    "czula": {"wejscie": 0.18, "wyjscie": 0.07, "pewnosc_tel": 0.18, "twarz": 2.4},
}

LIMIT_S = (10, 4 * 3600)       # od 10 s (do testów) do 4 h
KARA_S = (10, 4 * 3600)
PRZERWA_S = (5, 600)
HOST_ESP = re.compile(r"^[A-Za-z0-9.\-]{1,253}(:\d{1,5})?$")
TOKEN_ESP = re.compile(r"^[A-Za-z0-9_\-]{0,64}$")
CZULOSC_HA = {"cautious": "ostrozna", "normal": "normalna", "sensitive": "czula"}


@dataclass(frozen=True)
class Ustawienia:
    zrodlo: str = ""            # rtsp://…, http://… (ESP32), "laptop", plik albo indeks kamery (zrodla.py)
    esp: str = ""               # IP/host ESP; puste = tryb próbny (nic nie odcina)
    esp_token: str = ""         # opcjonalny klucz, ten sam co API_TOKEN w firmware
    limit_s: int = 600          # ile wolno scrollować bez przerwy
    kara_s: int = 900           # na ile odciąć internet
    przerwa_s: int = 45         # tyle przerwy zeruje licznik
    czulosc: str = "normalna"
    czuwanie: bool = True       # False = tylko podgląd, bez odcinania


def _ogranicz(wartosc, zakres: tuple[int, int]) -> int:
    return max(zakres[0], min(zakres[1], int(wartosc)))


def zastosuj(baza: Ustawienia, dane: dict) -> Ustawienia:
    """Zwraca NOWE ustawienia z poprawionymi polami z `dane`. Rzuca ValueError przy błędzie."""
    if not isinstance(dane, dict):
        raise ValueError("settings must be a JSON object")
    zmiany: dict = {}
    if "zrodlo" in dane:
        zrodlo = str(dane["zrodlo"]).strip()
        if MASKA not in zrodlo:          # zamaskowane hasło = bez zmian
            zmiany["zrodlo"] = zrodlo
    if "esp" in dane:
        esp = str(dane["esp"]).strip().removeprefix("http://").rstrip("/")
        if esp and not HOST_ESP.match(esp):
            raise ValueError("ESP address: an IP or host name only, e.g. 192.168.0.50")
        zmiany["esp"] = esp
    if "esp_token" in dane:
        token = str(dane["esp_token"]).strip()
        if MASKA not in token:           # zamaskowany klucz = bez zmian
            if not TOKEN_ESP.match(token):
                raise ValueError("ESP key: letters, digits, _ and -, at most 64 characters")
            zmiany["esp_token"] = token
    try:
        if "limit_s" in dane:
            zmiany["limit_s"] = _ogranicz(dane["limit_s"], LIMIT_S)
        if "kara_s" in dane:
            zmiany["kara_s"] = _ogranicz(dane["kara_s"], KARA_S)
        if "przerwa_s" in dane:
            zmiany["przerwa_s"] = _ogranicz(dane["przerwa_s"], PRZERWA_S)
    except (TypeError, ValueError) as blad:
        raise ValueError("times must be numbers of seconds") from blad
    if "czulosc" in dane:
        if dane["czulosc"] not in CZULOSC:
            raise ValueError(f"sensitivity: one of {', '.join(CZULOSC)}")
        zmiany["czulosc"] = dane["czulosc"]
    if "czuwanie" in dane:
        zmiany["czuwanie"] = bool(dane["czuwanie"])
    return replace(baza, **zmiany)


def wczytaj(plik: Path = PLIK) -> Ustawienia:
    if not plik.exists():
        return Ustawienia()
    try:
        dane = json.loads(plik.read_text(encoding="utf-8"))
        znane = {f.name for f in fields(Ustawienia)}
        return zastosuj(Ustawienia(), {k: v for k, v in dane.items() if k in znane})
    except (OSError, ValueError) as blad:
        print(f"[settings] can't read {plik}: {blad}, using defaults")
        return Ustawienia()


def zapisz(ust: Ustawienia, plik: Path = PLIK) -> None:
    tymczasowy = plik.with_suffix(".tmp")
    tymczasowy.write_text(json.dumps(asdict(ust), ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(tymczasowy, 0o600)          # w adresie RTSP siedzi hasło do kamery
    tymczasowy.replace(plik)


def zamaskuj_zrodlo(zrodlo: str) -> str:
    """rtsp://user:haslo@host/... -> rtsp://user:•••@host/..."""
    return re.sub(r"^(\w+://[^:/@]+:)[^@]*(@)", rf"\g<1>{MASKA}\g<2>", zrodlo)


def do_strony(ust: Ustawienia) -> dict:
    dane = asdict(ust)
    dane["zrodlo"] = zamaskuj_zrodlo(ust.zrodlo)
    dane["esp_token"] = MASKA if ust.esp_token else ""
    return dane


def z_opcji_ha(opcje: dict) -> dict:
    """Opcje add-onu Home Assistanta (angielskie klucze) -> pola Ustawienia.

    Puste teksty nie nadpisują tego, co ustawiono na stronie.
    """
    dane: dict = {}
    # camera_url do wersji 0.1.0 nazywało się rtsp_url
    for klucz_ha, pole in (("rtsp_url", "zrodlo"), ("camera_url", "zrodlo"), ("esp_host", "esp"),
                           ("esp_token", "esp_token")):
        if str(opcje.get(klucz_ha) or "").strip():
            dane[pole] = str(opcje[klucz_ha]).strip()
    for klucz_ha, pole, mnoznik in (("limit_minutes", "limit_s", 60), ("ban_minutes", "kara_s", 60),
                                    ("break_seconds", "przerwa_s", 1)):
        if opcje.get(klucz_ha) is not None:
            dane[pole] = int(float(opcje[klucz_ha]) * mnoznik)
    if opcje.get("sensitivity") in CZULOSC_HA:
        dane["czulosc"] = CZULOSC_HA[opcje["sensitivity"]]
    if "enforce" in opcje:
        dane["czuwanie"] = bool(opcje["enforce"])
    return dane
