// Scroll Guard relay — configuration.
//
// Copy this file to `config.h` (same folder) and fill in your Wi-Fi.
// `config.h` is git-ignored, so your password never ends up in the repo.
// Without `config.h` the sketch still compiles with these placeholders (useful for CI).
#pragma once

// ---- Wi-Fi (2.4 GHz) ------------------------------------------------------
#define WIFI_SSID "your-wifi-name"
#define WIFI_PASSWORD "your-wifi-password"
#define HOSTNAME "scroll-guard"  // reachable as http://scroll-guard.local

// Optional shared secret. Empty = no auth (anyone on your LAN can call /ban).
// If set, put the same value in the web UI (MORE -> ESP token).
#define API_TOKEN ""

// ---- Pins -------------------------------------------------------------------
// Defaults for an ESP32 DevKit (WROOM-32) and an ESP32-C3 DevKit.
#if defined(CONFIG_IDF_TARGET_ESP32C3)
#define RELAY_PIN 3    // -> relay module IN
#define BUTTON_PIN 9   // on-board BOOT button (long press = restore internet)
#define LED_PIN -1     // C3 DevKits usually have an RGB LED here; -1 = no status LED
#else
#define RELAY_PIN 26   // -> relay module IN
#define BUTTON_PIN 0   // on-board BOOT button (long press = restore internet)
#define LED_PIN 2      // on-board blue LED: on while internet is cut
#endif

// Relay module trigger level.
// Recommended: a module with an H/L trigger jumper set to "H" (high level trigger) -> 0.
// Classic 5 V "low level trigger" modules -> 1, but read docs/hardware.md first:
// a 3.3 V GPIO often cannot switch them fully off.
#define RELAY_ACTIVE_LOW 0

// ---- Safety -----------------------------------------------------------------
#define MAX_BAN_SECONDS (4UL * 3600UL)  // hard cap, whatever the server asks for
#define BUTTON_HOLD_MS 2000UL           // hold BOOT this long to cancel a ban
