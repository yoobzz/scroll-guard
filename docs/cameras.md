# Cameras

Three kinds of camera work. Detection is the same for all of them; what differs is what the camera can see.

| | IP camera (RTSP) | ESP32 camera | Laptop camera |
|---|---|---|---|
| Source | `rtsp://user:password@IP:554/stream1` | `http://IP:81/stream` | `laptop` |
| Sees | the whole room from a corner | the whole room, if mounted closer | only you, sitting at the laptop |
| Resolution | 2560×1440 (Tapo C2xx), 1920×1080 typical | up to 1600×1200 (OV2640) | 1280×720 |
| At night | IR night vision (detection in IR untested) | no IR, noise in low light | lit only by the screen |
| Cost | about €25–40 | about €6–15 | free |
| HA add-on | yes | yes | no |
| During a ban | drops off Wi-Fi with the router, reconnects after | same | keeps working, no network in the way |
| Setup | vendor app, camera account for RTSP | flash a stock Arduino example | none (macOS asks for camera permission) |

On the page, **More → Camera** has a button for each. The IP and ESP32 buttons fill in an address template with the part you need to change already selected; type over it and press Save. The laptop button switches straight away.

## IP camera (RTSP): the recommended setup

**Pros**
- High resolution: across a room a phone is still dozens of pixels wide, which is what detection needs.
- Wide angle, mounted high in a corner: one camera covers the bed, the sofa and the desk.
- Night vision (IR). Detection in grey IR images has not been tested yet.
- Stable H.264 stream that doesn't depend on any computer being open.

**Cons**
- Costs money and is set up through the vendor's app and account.
- The RTSP password is stored in the settings (a local file, readable only by you).
- Many cheap cameras talk to the vendor's cloud. You can block the camera's internet access in your router; RTSP keeps working on the LAN.

**Setup**
- TP-Link Tapo: in the Tapo app, camera → Settings → Advanced settings → Camera account, set a user name and password. The stream is `rtsp://<user>:<password>@<camera-ip>:554/stream1`. Use `stream1` (full resolution), not `stream2`.
- Other brands: search for "<model> RTSP URL" and use the main (highest resolution) stream.

## ESP32 camera (ESP32-CAM, XIAO ESP32S3 Sense)

A separate ESP32 board with a camera, running Espressif's stock **CameraWebServer** example. It has nothing to do with the relay board, which stays as it is.

**Pros**
- Cheap and tiny. It fits on a shelf or a wall where an IP camera would be too big.
- Fully local and open: no app, no account, no cloud.
- Works with the Home Assistant add-on too.

**Cons**
- Small 2 MP sensor (OV2640). Across a whole room a phone gets very few pixels, so mount it closer, 2–3 m from where you scroll, and use the largest frame size.
- At 1600×1200 the Wi-Fi stream gives only a few frames per second. That's enough, because the server analyses at most 3 frames a second, but the picture is noisier than an IP camera's.
- Poor in the dark: no IR, and in low light the OV2640 produces mostly green noise.
- 2.4 GHz Wi-Fi only. One viewer at a time: while Scroll Guard reads the stream you can't open it in a browser.
- The AI Thinker ESP32-CAM has no USB port. You need a USB-serial adapter or the ESP32-CAM-MB base board to flash it, and a solid 5 V / 1 A supply, or it keeps resetting. The XIAO ESP32S3 Sense has USB-C and is easier.
- Not yet tested on real hardware together with Scroll Guard. The stream format was tested against a simulated CameraWebServer stream.

**Setup** (Arduino IDE, board package esp32 by Espressif 3.x)

1. File → Examples → ESP32 → Camera → **CameraWebServer**, then save a copy.
2. In `board_config.h` comment out `CAMERA_MODEL_ESP_EYE` and uncomment your board: `CAMERA_MODEL_AI_THINKER` or `CAMERA_MODEL_XIAO_ESP32S3`.
3. In `CameraWebServer.ino` fill in `ssid` and `password`.
4. Same file: right after start the example drops to 320×240 ("drop down frame size for higher initial frame rate"), which is far too small. Change
   ```cpp
   s->set_framesize(s, FRAMESIZE_QVGA);
   ```
   to `FRAMESIZE_UXGA` (1600×1200), or `FRAMESIZE_SXGA` (1280×1024) for more frames per second.
5. Board: **AI Thinker ESP32-CAM**, or **XIAO_ESP32S3** with PSRAM set to **OPI PSRAM**. Upload.
6. The serial monitor prints `Camera Ready! Use 'http://192.168.x.x' to connect`. The stream is on port **81**: enter `http://192.168.x.x:81/stream` in Scroll Guard (More → ESP32 camera), or as `camera_url` in the add-on.

Give the board a fixed address in your router (DHCP reservation) so the URL doesn't change.

With step 4 changed, the example compiles with board package 3.3.3 for both boards (`esp32:esp32:esp32cam` and `esp32:esp32:XIAO_ESP32S3:PSRAM=opi`).

## Laptop camera

The built-in camera of the computer that runs the server.

**Pros**
- Nothing to buy or mount.
- Face-on and close, so detection is easy and quick.
- Keeps working during a ban, because it doesn't need the network.

**Cons**
- It only sees you while you sit at that laptop with the lid open. Scrolling in bed or on the sofa goes unnoticed.
- The laptop has to stay on and open, and the camera light stays on.
- Only for the Mac / Linux server. The Home Assistant add-on runs on another machine, so the button is hidden there.
- macOS asks for camera permission for the app that runs the server (Terminal, if you use `start.command`).

**Setup**
- On the page: More → **Laptop camera**. From the command line: `serwer.py --zrodlo laptop`.
- Mac: needs ffmpeg (`brew install ffmpeg`). The built-in camera is picked by name, skipping virtual ones (OBS), iPhone Continuity Camera and Desk View. To pick a specific camera use `mac:<device name>`; list the names with `ffmpeg -f avfoundation -list_devices true -i ""`. Without ffmpeg it falls back to OpenCV's first camera, which may be a virtual one.
- Linux: opens `/dev/video0`.

## Placement (any camera)

- It has to see faces where you scroll. With your back to the camera nothing counts.
- Mount it above head height, tilted down, so people don't hide each other.
- Avoid having a bright window behind you.
