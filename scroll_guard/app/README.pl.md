# Strażnik scrollowania

Kamera w rogu pokoju patrzy, czy siedzisz w telefonie. Jeśli trwa to dłużej niż
limit ustawiony na stronie, ESP z przekaźnikiem odcina prąd routera na czas kary.

## Start

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./start.command
```

Modele YOLO26 pobierają się same przy pierwszym starcie do `modele/`.

Strona: http://127.0.0.1:8911 (po angielsku). Kamerę wybierasz w More: kamera IP (RTSP), ESP32 z kamerą albo kamera laptopa (docs/cameras.md). Przy kamerze IP bierz główny
strumień w pełnej rozdzielczości (w Tapo `stream1`), bo z daleka telefon ma kilkadziesiąt pikseli.
Podgląd z telefonu w tej samej sieci: `./start.command --lan`, potem http://<IP-maca>:8911.

## Jak wykrywa

1. YOLO26 (poza) znajduje ludzi i punkty ciała: twarz, barki, nadgarstki.
2. Każdą osobę wycina z pełnej klatki, powiększa i szuka w wycinku telefonu (YOLO26m).
3. Telefon liczy się, gdy jest w ręce i w zasięgu wzroku albo przy twarzy. Odległości
   mierzy w szerokościach barków, więc tak samo działa na siedząco, na leżąco i z daleka.
   Telefon leżący na stole obok się nie liczy. **Twarz musi być w kadrze.** Gdy siedzisz
   plecami do kamery, telefon przy dłoni zwykle leży na biurku, więc strażnik go nie liczy.
   Kamerę ustaw tak, żeby widziała twarz w miejscach, gdzie scrollujesz (łóżko, kanapa, biurko).
   Czułość (ostrożnie / normalnie / czujnie) zmienia też, jak daleko od twarzy może być telefon.
4. Decyzję podejmuje z ostatnich 10 s, a nie z pojedynczej klatki. Krótka przerwa nie zeruje
   licznika, dopiero przerwa dłuższa niż ustawiona.

Ruchu kciuka z drugiego końca pokoju nie widać. Strażnik wykrywa „telefon trzymany przed
sobą”, a to, czy tak scrollujesz, wynika z czasu trwania.

## ESP (firmware osobno)

Serwer woła `GET http://<esp>/ban?s=<sekundy>`. ESP odcina przekaźnik i **sam** przywraca
prąd po tym czasie, bo po zgaszeniu routera nie ma z nim łączności. `GET /unban` przywraca
prąd od razu. Bez adresu ESP strażnik działa w trybie próbnym: liczy i pokazuje, ale niczego nie odcina.

## Testy

```
.venv/bin/python -m unittest discover -s tests
.venv/bin/python tests/sprawdz_obrazy.py <katalog_ze_zdjeciami> [wyjscie]
```
