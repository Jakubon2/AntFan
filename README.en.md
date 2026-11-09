# AntFan – a fan driven by power and heart rate (ANT+ / Bluetooth)

[Česky](README.md)

**Who it is for:** anyone who rides a trainer at home (Rouvy, Zwift, MyWhoosh or just riding) and doesn't want to get off the bike to adjust the fan. When you push harder, start sweating and your heart rate climbs, AntFan turns the fan up on its own. When you ease off or take a break, it turns it down again. No buttons to press.

**What you need:** a Windows PC or a Mac, an HR strap, a power meter or a smart trainer (ANT+ via a USB dongle, or Bluetooth) and a fan that can be controlled over Wi-Fi: Xiaomi, a plain fan on a Shelly smart plug, or anything in Home Assistant. You can try it without any of that in **Simulation** mode.

AntFan is a desktop app for Windows 10/11 and macOS (Apple Silicon) that:

1. connects to an ANT+ USB dongle and/or Bluetooth sensors,
2. finds HR straps, power meters and smart trainers (ANT+ FE-C, Bluetooth FTMS) nearby,
3. shows power, cadence and HR live, with a chart of the last 10 minutes,
4. sets the fan speed from these values: Xiaomi fans over local Wi-Fi, a plain fan on a Shelly plug, or anything in Home Assistant.

The app is available in English and Czech. By default it follows the system language; change it in **Settings → Appearance → Language**.

## Supported devices

| Device | Works | Does not work |
|---|---|---|
| **ANT+ dongle** | Garmin ANT+ USB stick (ANTUSB2, `0fcf:1008`), Garmin mini stick (ANTUSB-m, `0fcf:1009`) and most cheap clones (CooSpo, CYCPLUS, Anself…) that report the same IDs | first-generation stick (`0fcf:1004`) |
| **HR strap** | any ANT+ strap: Garmin HRM, Wahoo TICKR, Scosche Rhythm+, Garmin watches with *HR broadcast*; over Bluetooth also Polar H9, H10, Verity Sense | – |
| **Power meter** | any ANT+ power meter: pedals (Garmin Rally, Favero Assioma), cranks (Stages, 4iiii, Quarq); over Bluetooth any with the Cycling Power service | – |
| **Smart trainer** | any ANT+ FE-C trainer: Tacx, Wahoo KICKR, Elite, Zwift Hub…; over Bluetooth any with FTMS or Cycling Power | Bluetooth trainers with a proprietary protocol only |
| **Fan** | Xiaomi Smart Standing Fan 2 Lite (`dmaker.fan.1c`, tested), other Xiaomi fans by spec, a plain fan via Shelly, anything via Home Assistant | other brands without Home Assistant |
| **Computer** | Windows 10 and 11, macOS 11+ on Apple Silicon (M1 and newer) | Intel Macs (arm64 build only), Linux not yet |

A separate speed/cadence sensor is not used; cadence comes from the power meter or trainer.

## Installation

### Windows
1. Download **`AntFan.exe`** from [Releases](../../releases) and run it. No Python needed.
2. **Dongle driver:** AntFan talks to the dongle via libusb, so the dongle needs the **libusbK** or **WinUSB** driver. If you already have libusbK (e.g. for GoldenCheetah), nothing to do. Otherwise download [Zadig](https://zadig.akeo.ie/), choose *Options → List All Devices*, select "ANT USBStick2" (or "ANT USB-m Stick"), pick **libusbK** and click *Replace Driver*.
   > Garmin Express and some apps use their own driver and may not see the dongle after switching. Only one app can use the dongle at a time.
3. **From source:** install Python 3.10+ from <https://www.python.org/downloads/windows/> (tick *Add python.exe to PATH*) and run `run.bat`. To build the exe yourself, run `build_exe.bat`; the result is `dist\AntFan.exe`.

The exe is built by GitHub Actions (`.github/workflows/build-exe.yml`) and checked with `AntFan.exe --selftest`.

### macOS
No dongle driver is needed on a Mac.

1. Download **`AntFan-macOS.zip`** from [Releases](../../releases) and unzip it.
2. Drag **`AntFan.app`** to *Applications*.
3. **First launch:** the app is not signed by Apple, so macOS says *"AntFan" Not Opened*. Click **Done** (not *Move to Trash*), then either:
   - open **System Settings → Privacy & Security**, scroll down, click **Open Anyway** next to the AntFan message, confirm and launch AntFan again,
   - or remove the download flag in Terminal:
   ```bash
   xattr -dr com.apple.quarantine /Applications/AntFan.app
   ```
   This is needed only once. (Older macOS also allows **right-click → Open**.)
4. Plug in the ANT+ dongle (USB-C adapter) and start measuring.

Settings and the log are in `~/Library/Application Support/AntFan/` (Settings → Diagnostics → *Open log folder*). Zwift Launcher and Garmin Express keep running after their window is closed, check the menu bar.

**From source:** Python 3.10+ from <https://www.python.org/downloads/macos/>, then in the project folder:
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python -m antfan
```
Bluetooth works only in the built AntFan.app (macOS requires `NSBluetoothAlwaysUsageDescription`).

## Connecting the fan

In **Settings → Fan** choose the type:

| Type | What it controls | Levels |
|---|---|---|
| **Xiaomi** | Xiaomi / Mijia / Smartmi / dmaker fans on your Wi-Fi (no cloud) | levels or % speed depending on the model |
| **Shelly plug** | a plain fan plugged into a Shelly relay (Gen1 and Plus/Pro, no password) | on/off from a chosen level |
| **Home Assistant** | any `fan.*` entity (% speed) or `switch.*` entity | depends on the entity |

**Xiaomi:** AntFan sends commands directly on your network (UDP 54321), encrypted with the fan's **token**. Pair the fan in Mi Home (2.4 GHz Wi-Fi, same network as the PC), then click **Get from Xiaomi account…**, scan the QR code in Mi Home and confirm on your phone. No password is entered; AntFan fills in the IP and token. Reserve a fixed IP for the fan in your router. **Test** detects the model and picks the right control (many `dmaker`, `xiaomi`, `zhimi`, `leshow`, `viomi`, `dreame` models; other models are looked up on <https://miot-spec.org>). Only `dmaker.fan.1c` is tested on real hardware. AntFan can mute the beeps and turn off the display light. The token changes when the fan is reset or re-paired.

**Shelly:** enter the IP, output (0 for single-channel) and the level it switches on from. Set the speed on the fan itself.

**Home Assistant:** enter the address (e.g. `http://homeassistant.local:8123`), a long-lived token (Profile → Security → Long-lived access tokens) and the entity, e.g. `fan.fan` or `switch.fan_plug`.

The number of AntFan levels (1–5) can differ from the fan's levels; AntFan spreads them evenly.

## Sensors

1. Plug the dongle in, ideally on a **USB extension cable** close to the bike (USB 3 ports interfere with 2.4 GHz).
2. Wake the sensors: put on and wet the HR strap, turn the cranks.
3. Click **Scan for sensors** (15 s). ANT+ and Bluetooth are scanned together; Bluetooth sensors are marked **(BT)**.
4. Click your sensors to select them and press **Start**. The selection is remembered.

**Find my sensors** (smart pairing): in an apartment building you may see your neighbors' sensors. AntFan scans for 20 s while you pedal and wet the strap; the sensors that react are yours. **Apply** saves the selection.

**Bluetooth sensors:** Heart Rate, Cycling Power and FTMS. ANT+ and Bluetooth can be combined. A Bluetooth sensor often allows only 1–2 connections, so do not connect the same sensor to Rouvy and AntFan over Bluetooth.

**Battery:** the Battery column shows % or new / good / OK / low / critical. A low battery shows a one-time warning in the ride window (Settings → Sensors).

### Riding with Rouvy, Zwift and others
One ANT+ dongle can be used by only one app. When Rouvy, Zwift, TrainerRoad, MyWhoosh and similar apps are running, AntFan shows a hint bar:
- **Two dongles:** one per app, pair over ANT+ in both. AntFan takes the free dongle by itself.
- **Rouvy holds the dongle:** AntFan uses Bluetooth. **Switch to Bluetooth sensors** selects the BT versions of your sensors. Pair over ANT+ only in Rouvy.
- **AntFan holds the dongle:** pair your sensors over Bluetooth in Rouvy.

AntFan never resets a dongle used by another app. Details: **Settings → Other apps**.

## Fan control

The switch at the bottom of the window: **Auto** follows the rules, **Off/1/2/3** sets the level manually. Everything else is in **Settings** and is saved immediately.

| Mode | Behavior |
|---|---|
| **Smart: power raises, HR holds** (default) | Power steps up immediately. HR does not step up, but holds the level until it drops, so the fan does not slow down in short rests between intervals. |
| Higher level of power and HR | The higher of the two wins. |
| Power only / HR only | One source only. |
| Wind by ride speed | Fan speed follows the speed from the trainer (FE-C), e.g. projected by Rouvy. Off below 5 km/h, 100 % at the full-speed value (default 45 km/h). Optional minimum by power and HR for slow climbs. |

If one source is missing, the other is used automatically.

- **Thresholds** (Settings → Control) in **% FTP / % max HR** (default 30 / 60 / 85 % FTP and 55 / 70 / 82 % max HR) or in **W / bpm**.
- **Smooth speed** (Settings → Control → Output): instead of levels, speed rises linearly from the min. % at the 1st threshold to 100 % at the last one.
- **Behavior:** hysteresis, smoothing, delay before stepping down, **lead** (step up right away when instant power stays above the next threshold), **cooldown** after the workout (default 3 min at level 1) and the level with no sensor data.
- **Simulation** (Settings → Diagnostics) generates fake sensors and a fan to try the rules.

## More features

- **Phone control:** values and the **Auto | Off | 1–3** switch on a phone on the same Wi-Fi, nothing to install. Click **Phone on**, scan the QR code or open `http://<PC IP>:8686/m/<key>`. On Windows allow **private networks**; on macOS enable AntFan in **System Settings → Privacy & Security → Local Network**. The address contains a random key; **New key** invalidates it. The page language follows the app setting, or the phone's language when set to System. API: `GET /m/<key>/api/state`, `POST /m/<key>/api/level` with `{"level": "auto"}` or `{"level": 2}`.
- **Drink reminder** (off by default, Settings → Drinking): a subtle "Drink · about 150 ml" bar during the ride, based on ride time, power and room temperature. Rough values only.
- **Overlay bar** (off by default): a small strip on top of Rouvy with the fan level, reason and alerts. Click the level to cycle Auto → 1 → 2 → … → Off, drag to move. Rouvy must run in borderless/windowed mode.
- **Profiles:** each profile has its own FTP, max HR, thresholds, mode and behavior. Switch via "Profile: …" in the ride window or Settings → Control.
- **Ride summary:** after **Stop** (rides of 5+ minutes): duration, avg/max power, NP, IF, TSS, work in kJ, avg/max HR, cadence, time in power zones (Coggan, 7 zones) and HR zones (5), time per fan level and **HR drift** (decoupling). Every ride is saved as CSV in `%APPDATA%\AntFan\jizdy\` (macOS: `~/Library/Application Support/AntFan/jizdy/`). **Settings → Rides** lists past rides.
- **Appearance:** light / dark / system theme and language (System / Čeština / English).

## Troubleshooting

- **"Dongle is used by another app" when nothing runs:** AntFan releases the dongle after errors, retries with a USB reset, allows only one instance and tells you which app holds the dongle. **Settings → Diagnostics → Reset dongle** acts like unplugging it. Try another USB port (not a hub) and on Windows check the libusbK driver in Device Manager.
- **Power drops to 0 W:** the **Signal** column shows the % of messages received in the last 5 s (red below 80 %). Move the dongle closer to the bike. AntFan tells you below the sensor list whether the cause is the PC (all sensors drop at once) or one sensor. The dongle also reports every message it expected but missed, so the log says for each dropout whether the radio lost it (sensor, range, interference) or it got lost on the way to the program (USB, driver, busy PC).
- **Phone page does not load** (works on the PC): the phone's IP must start like the PC's (same Wi-Fi, not mobile data); turn off VPN and VPN-like apps on the phone (ad blockers, NextDNS, WARP, antivirus, Samsung *Secure Wi-Fi*); guest/office/school Wi-Fi often isolates devices; after **New key** scan the new QR code.
- **Rouvy or the whole PC stutters with AntFan:** AntFan itself uses ~0 % CPU, so the cause is usually USB or drivers. Test AntFan without measuring (dongle closed); if that is fine, move the dongle to a rear USB 2.0 port (not a hub), ideally on an extension cable away from the PC and the Bluetooth adapter. If it still stutters with the dongle closed, turn off the overlay bar and phone control. LatencyMon (free) shows which driver stalls the system.
- **"ANT+ dongle not found":** check that it is plugged in and has the libusbK/WinUSB driver.
- **Fan not responding:** wrong IP, another network or a firewall. **"wrong token"**: get the token again.
- Log: `%APPDATA%\AntFan\antfan.log`, settings: `%APPDATA%\AntFan\config.json`. Send the log when asking for help; it contains no token.

## Development

```bash
python -m unittest discover tests            # Czech (default)
ANTFAN_LANG=en python -m unittest discover tests
```
Texts are translated with `_()` from `antfan/i18n.py`; the Czech text is the key, English is in `antfan/i18n_en.py`. `tests/test_i18n.py` checks that every key has a translation and that the English UI has no Czech left.
