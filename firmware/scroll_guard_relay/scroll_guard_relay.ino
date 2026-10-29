// Scroll Guard relay — cuts the router's power when the server says "ban".
//
// The relay sits on the router's low-voltage DC line, wired through the NORMALLY
// CLOSED contact: relay off = router powered. A ban energises the relay for N
// seconds. The ESP32 keeps its own timer, because Wi-Fi disappears together with
// the router — nobody can reach it until the ban is over.
//
// HTTP API (port 80):
//   GET /status                     -> {"banned":false,"remaining_s":0,...}
//   GET /ban?s=<seconds>[&key=...]  -> cut power for <seconds> (capped, never shortens a running ban)
//   GET /unban[?key=...]            -> restore power now
// Hold the BOOT button for 2 s to restore power by hand.

#include <WiFi.h>
#include <WebServer.h>
#include <ESPmDNS.h>

#if __has_include("config.h")
#include "config.h"
#else
#warning "config.h not found - building with config.example.h placeholders"
#include "config.example.h"
#endif

WebServer server(80);

static bool banned = false;
static uint32_t banStartMs = 0;
static uint32_t banDurationMs = 0;
static bool mdnsStarted = false;
static uint32_t buttonDownMs = 0;
static bool buttonHandled = false;

// ---------- relay and ban state ----------

static void relayWrite(bool cut) {
  const bool level = RELAY_ACTIVE_LOW ? !cut : cut;
  digitalWrite(RELAY_PIN, level ? HIGH : LOW);
}

static void ledWrite(bool on) {
  if (LED_PIN >= 0) digitalWrite(LED_PIN, on ? HIGH : LOW);
}

// millis() wraps after ~49 days; unsigned subtraction keeps this correct.
static uint32_t remainingMs() {
  if (!banned) return 0;
  const uint32_t elapsed = millis() - banStartMs;
  return elapsed >= banDurationMs ? 0 : banDurationMs - elapsed;
}

static void startBan(uint32_t seconds) {
  if (seconds < 1) seconds = 1;
  if (seconds > MAX_BAN_SECONDS) seconds = MAX_BAN_SECONDS;
  const uint32_t wantedMs = seconds * 1000UL;
  if (banned && remainingMs() >= wantedMs) return;  // never shorten a running ban
  banned = true;
  banStartMs = millis();
  banDurationMs = wantedMs;
  relayWrite(true);
  ledWrite(true);
  Serial.printf("[ban] internet cut for %lu s\n", (unsigned long)seconds);
}

static void endBan(const char *reason) {
  if (!banned) return;
  banned = false;
  banDurationMs = 0;
  relayWrite(false);
  ledWrite(false);
  Serial.printf("[ban] internet restored (%s)\n", reason);
}

// ---------- HTTP ----------

static bool authorized() {
  if (strlen(API_TOKEN) == 0) return true;
  if (server.arg("key") == API_TOKEN) return true;
  server.send(403, "application/json", "{\"ok\":false,\"error\":\"bad key\"}");
  return false;
}

static String statusJson() {
  String json = "{\"ok\":true,\"banned\":";
  json += banned ? "true" : "false";
  json += ",\"remaining_s\":";
  json += String((remainingMs() + 999UL) / 1000UL);
  json += ",\"max_ban_s\":";
  json += String((unsigned long)MAX_BAN_SECONDS);
  json += ",\"uptime_s\":";
  json += String(millis() / 1000UL);
  json += ",\"rssi\":";
  json += String(WiFi.RSSI());
  json += "}";
  return json;
}

static void handleStatus() {
  server.send(200, "application/json", statusJson());
}

static void handleBan() {
  if (!authorized()) return;
  const long seconds = server.arg("s").toInt();
  if (seconds <= 0) {
    server.send(400, "application/json", "{\"ok\":false,\"error\":\"use /ban?s=<seconds>\"}");
    return;
  }
  startBan((uint32_t)seconds);
  server.send(200, "application/json", statusJson());
}

static void handleUnban() {
  if (!authorized()) return;
  endBan("http");
  server.send(200, "application/json", statusJson());
}

static void handleRoot() {
  String html =
      "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
      "<title>scroll guard relay</title>"
      "<body style='font:16px Helvetica Neue,Arial,sans-serif;margin:40px;color:#111'>"
      "<p style='color:#7b5ea7;letter-spacing:4px'>~||-_^+*.</p><h1 style='font-weight:500'>scroll guard relay</h1><p>";
  html += banned ? "internet <b>cut</b>, back in " + String((remainingMs() + 999UL) / 1000UL) + " s"
                 : "internet <b>on</b>";
  html += "</p><p style='color:#666'>GET /status &middot; /ban?s=N &middot; /unban</p></body>";
  server.send(200, "text/html", html);
}

// ---------- button and Wi-Fi ----------

static void pollButton() {
  if (BUTTON_PIN < 0) return;
  const bool down = digitalRead(BUTTON_PIN) == LOW;
  if (!down) {
    buttonDownMs = 0;
    buttonHandled = false;
    return;
  }
  if (buttonDownMs == 0) buttonDownMs = millis();
  if (!buttonHandled && millis() - buttonDownMs >= BUTTON_HOLD_MS) {
    buttonHandled = true;
    endBan("button");
  }
}

static void pollWifi() {
  const bool online = WiFi.status() == WL_CONNECTED;
  if (online && !mdnsStarted) {
    Serial.printf("[wifi] %s  http://%s.local\n", WiFi.localIP().toString().c_str(), HOSTNAME);
    mdnsStarted = MDNS.begin(HOSTNAME);
    if (mdnsStarted) MDNS.addService("http", "tcp", 80);
  }
  if (!online && mdnsStarted) {
    MDNS.end();  // the router is probably off (our own ban) — reconnect later
    mdnsStarted = false;
  }
  // while offline and not banned, blink the LED so a lost connection is visible
  if (!banned && LED_PIN >= 0) ledWrite(!online && (millis() / 500UL) % 2 == 0);
}

void setup() {
  // relay first: a fresh boot always means "internet on"
  pinMode(RELAY_PIN, OUTPUT);
  relayWrite(false);
  if (LED_PIN >= 0) pinMode(LED_PIN, OUTPUT);
  ledWrite(false);
  if (BUTTON_PIN >= 0) pinMode(BUTTON_PIN, INPUT_PULLUP);

  Serial.begin(115200);
  Serial.println("\n[scroll guard relay] boot, internet on");

  WiFi.mode(WIFI_STA);
  WiFi.setHostname(HOSTNAME);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  server.on("/", HTTP_GET, handleRoot);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/ban", HTTP_GET, handleBan);
  server.on("/unban", HTTP_GET, handleUnban);
  server.onNotFound([] { server.send(404, "application/json", "{\"ok\":false,\"error\":\"not found\"}"); });
  server.begin();
}

void loop() {
  if (banned && remainingMs() == 0) endBan("timer");
  pollButton();
  pollWifi();
  server.handleClient();
  delay(5);
}
