# Scroll Guard add-on

Watches an RTSP camera, notices when someone has been scrolling a phone for longer than the limit, and cuts the internet through an ESP32 relay on the router's power line. The page (preview + settings) opens from the sidebar.

Hardware, wiring and the firmware are described in the repository: <https://github.com/yoobzz/scroll-guard>.

## Installation

**From the repository** (the GitHub repository has to be public):

1. Settings → Add-ons → Add-on store → ⋮ → Repositories.
2. Add `https://github.com/yoobzz/scroll-guard` and close.
3. Find **Scroll Guard** in the store and install it.

**As a local add-on** (works with a private copy too):

1. Copy the `scroll_guard` folder into `/addons/` on the Home Assistant host, using the Samba share or the SSH / Terminal add-on.
2. Add-on store → ⋮ → Check for updates.
3. **Scroll Guard** appears under "Local add-ons". Install it.

The first install builds the image on your machine and downloads PyTorch (CPU), which takes a while. The first start then downloads the YOLO26 models into the add-on's data folder.

Supported: `amd64` and `aarch64`. That covers mini PCs, NUCs and 64-bit Raspberry Pi OS / HA OS.

## Configuration

| Option | Default | |
|---|---|---|
| `rtsp_url` | – | camera stream, e.g. `rtsp://user:password@192.168.1.20:554/stream1` (TP-Link Tapo, full-resolution stream) |
| `esp_host` | – | ESP32 relay, e.g. `scroll-guard.local` or its IP. Empty = dry run, nothing is cut. |
| `esp_token` | – | the `API_TOKEN` from the firmware's `config.h`, if you set one |
| `limit_minutes` | 10 | how long someone may scroll without a break |
| `ban_minutes` | 15 | how long the internet stays off |
| `break_seconds` | 45 | a break this long resets the counter |
| `sensitivity` | normal | `cautious` = fewer false alarms, `sensitive` = catches more |
| `enforce` | true | off = only watch and count |
| `model_size` | light | `light` (yolo26n-pose + yolo26s) or `full` (yolo26m models, needs a fast CPU) |

Settings changed on the add-on's page also take effect immediately. On every restart, the options above are applied again. Empty text options do not overwrite what you entered on the page.

**Check the speed:** the line under the preview shows "analiza klatki" (frame analysis) in ms. It should stay under about 4000 ms. Slower than that and the timers stop counting reliably; switch `model_size` to `light`. For reference: about 1900 ms with the light models on 4 CPU cores with 4 people in view; fewer people in view = faster.

## Entities and event

The add-on publishes:

- `binary_sensor.scroll_guard_scrolling`: someone is scrolling now
- `binary_sensor.scroll_guard_internet_cut`: a ban is running
- `sensor.scroll_guard_streak`: current streak (s), attribute `limit_s`
- `sensor.scroll_guard_ban_remaining`: seconds left of the ban
- `sensor.scroll_guard_people`: people in view

and fires the `scroll_guard_ban` event (`{"seconds": N}`) on every cut.

These states are written by the add-on and are not registered entities. They come back within a minute after a Home Assistant restart.

With the event you can skip the ESP32 and switch the router's plug instead. Use a **Zigbee or Z-Wave** plug: a Wi-Fi plug loses its connection to Home Assistant once the router is off and would never be switched back on. An example automation is in [docs/api.md](https://github.com/yoobzz/scroll-guard/blob/main/docs/api.md#home-assistant-add-on-only).

## Good to know

- The camera has to see faces where you scroll. With your back to the camera the phone is not counted.
- During a ban the whole local network is down, including the camera, the ESP32 and Home Assistant's own connection to them. The ESP32 restores power by itself when the ban is over. The router then needs 1–3 minutes to boot.
- Video stays on your machine. Frames are analysed in memory and never saved.
- The page is in Polish.
