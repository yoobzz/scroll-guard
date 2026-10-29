# API

Three interfaces: the ESP32 relay, the detection server, and the Home Assistant entities the add-on publishes.

## ESP32 relay (port 80)

All endpoints are `GET` and answer with JSON. If `API_TOKEN` is set in `config.h`, `/ban` and `/unban` need `&key=<token>`. A wrong key returns `403 {"ok":false,"error":"bad key"}`.

| Endpoint | What it does |
|---|---|
| `/` | small status page |
| `/status` | current state, see below |
| `/ban?s=<seconds>[&key=…]` | cuts the router's power for `<seconds>`. Capped at `MAX_BAN_SECONDS`. A running ban is only ever extended, never shortened. A missing or invalid `s` returns `400`. |
| `/unban[?key=…]` | restores power now |

`/status`, and the reply to `/ban` and `/unban`:

```json
{"ok": true, "banned": true, "remaining_s": 897, "max_ban_s": 14400, "uptime_s": 5321, "rssi": -58}
```

```bash
curl "http://scroll-guard.local/ban?s=10"     # test: internet off for 10 s
curl "http://scroll-guard.local/unban"
```

Remember that a ban takes the router down, and with it your connection to the ESP32. `/unban` only works if you can still reach the board: over mobile data you can't, and the BOOT button is the way back.

## Detection server (port 8911)

The server listens on `127.0.0.1` (or on all interfaces with `--lan`, or behind HA ingress in the add-on). The JSON field names are Polish. Their English meanings are below.

Every request needs a local `Host` header (an IP, `localhost` or `*.local`), which blocks DNS rebinding. POST requests also need `Content-Type: application/json` and a body of at most 10 kB, which blocks other websites from posting through your browser.

| Method | Path | |
|---|---|---|
| GET | `/` | web page |
| GET | `/podglad.mjpg` | live preview (MJPEG) with the boxes and labels drawn in |
| GET | `/api/stan` | state (below) |
| POST | `/api/ustawienia` | change settings: send only the fields you want to change. Returns the settings with the password and key masked. Invalid values → `400 {"blad": "…"}`. |
| POST | `/api/test-odciecia` | **really cuts the internet for 20 s** through the ESP32, if an address is set (body: `{}`) |

### `GET /api/stan`

| Field | Meaning |
|---|---|
| `scrolluje` | someone is scrolling right now |
| `scrollujacych` | how many people are scrolling |
| `seria_s` | current streak in seconds, for the person closest to the limit |
| `przerwa_s` | that person's current break in seconds |
| `udzial` | share of the last 10 s of frames showing their phone in use (0–1) |
| `kara_zostalo_s` | seconds left of the current ban (0 = no ban) |
| `obraz_ok` | a fresh camera frame arrived in the last 5 s |
| `kamera` | camera status text |
| `osoby` | people in view |
| `telefon` | confidence of the best phone detection, or `null` |
| `powody` | one short reason per person: why it counts, or why it doesn't |
| `analiza_ms` | time to analyse the last frame |
| `blad` | last error, or `null` |
| `odciecie` | last call to the ESP32 (`co` what, `wynik` result, `ok`, `kiedy` unix time), plus `esp: {online, banned, remaining_s}` from its `/status` (polled every 30 s) |
| `ustawienia` | current settings, with secrets masked |

### Settings (`POST /api/ustawienia`)

| Field | Type | Range | Meaning |
|---|---|---|---|
| `zrodlo` | string | | camera: RTSP URL, video or image file, camera index, or `mac` |
| `esp` | string | IP or hostname | ESP32 address. Empty = dry run. |
| `esp_token` | string | `[A-Za-z0-9_-]{0,64}` | same as `API_TOKEN` in the firmware |
| `limit_s` | int | 10–14400 | how long someone may scroll without a break |
| `kara_s` | int | 10–14400 | ban length |
| `przerwa_s` | int | 5–600 | a break this long resets the streak |
| `czulosc` | string | `ostrozna` / `normalna` / `czula` | sensitivity: cautious / normal / sensitive |
| `czuwanie` | bool | | `false` = only watch and count, never cut |

```bash
curl -X POST http://127.0.0.1:8911/api/ustawienia \
  -H 'Content-Type: application/json' -d '{"limit_s": 900, "kara_s": 1800}'
```

Values containing `•••` (the masked password or key as the page shows them) are ignored, so sending the page's settings back does not wipe your secrets.

## Home Assistant (add-on only)

The add-on writes these states through the Supervisor API every 5 s (only when something changed, plus a refresh every 60 s):

| Entity | State |
|---|---|
| `binary_sensor.scroll_guard_scrolling` | `on` while someone is scrolling |
| `binary_sensor.scroll_guard_internet_cut` | `on` during a ban |
| `sensor.scroll_guard_streak` | current streak in seconds (attribute `limit_s`) |
| `sensor.scroll_guard_ban_remaining` | seconds left of the ban |
| `sensor.scroll_guard_people` | people in view |

These are plain state objects, not entities registered by an integration. They have no unique ID, so they can't be renamed in the UI and they disappear after a HA restart until the add-on writes them again (within 60 s).

Event on every cut: `scroll_guard_ban` with data `{"seconds": <ban length>}`.

```yaml
# example: a Zigbee plug with the router instead of the ESP32
automation:
  - alias: Scroll Guard cuts the router
    triggers:
      - trigger: event
        event_type: scroll_guard_ban
    actions:
      - action: switch.turn_off
        target: { entity_id: switch.router_plug }
      - delay:
          seconds: "{{ trigger.event.data.seconds }}"
      - action: switch.turn_on
        target: { entity_id: switch.router_plug }
    mode: restart
```
