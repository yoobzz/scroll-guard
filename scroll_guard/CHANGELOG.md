# Changelog

## 0.1.0

First release.

- Detection with YOLO26: people and body keypoints on the full frame, then a phone search in each person's upscaled crop.
- A phone counts only when it belongs to that person and is near their visible face (in shoulder widths), so phones on the desk and bowed heads don't count.
- Per-person tracking and timers over a 10 s window. A break of the set length resets the streak.
- ESP32 relay on the router's DC line (NC, fail-safe). The ESP32 keeps the ban timer itself, with an optional key and a manual unban on the BOOT button.
- Page with live preview and settings, served through ingress.
- Home Assistant states (`binary_sensor.scroll_guard_*`, `sensor.scroll_guard_*`) and the `scroll_guard_ban` event.
- `light` / `full` model sets. Timers tolerate up to 5 s between analysed frames, so slower CPUs still count correctly.
