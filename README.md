# Deadman's Switch — Keystroke-Dynamics Anti-Theft System

Silently monitors your PC's typing rhythm. If someone else uses your device,
it enables Wi-Fi, triangulates the location, captures a screenshot, and sends
everything to your Telegram account — all without alerting the unauthorised user.

---

## Quick-start (5 steps)

### 1. Install dependencies
```
pip install -r requirements.txt
```

### 2. Create a Telegram bot
1. Open Telegram → search **@BotFather** → send `/newbot`
2. Copy the **bot token** (looks like `123456:ABC-DEF…`)
3. Message your new bot once, then open:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. Find `"chat":{"id":XXXXXXX}` — that is your **chat ID**

### 3. Edit config.json
```json
{
  "telegram_bot_token": "123456:ABC-DEF...",
  "telegram_chat_id":   "123456789",
  ...
}
```

Or use the configuration UI:
```
python config_ui.py
```

### 4. Calibrate to your typing
```
python calibrate.py
```
Type naturally for ~70 keystrokes. Your baseline is saved to `config.json` automatically.

### 5. Install to startup
```
python install.py          (run as Administrator for best results)
```
The guard will now start invisibly every time Windows boots.

---

## Configuration UI

A graphical tool for setting up all features:
```
python config_ui.py
```

Features:
- **Telegram tab** — enter token, validate it, auto-detect chat ID
- **Email tab** — configure Gmail SMTP backup, test credentials
- **Calibration tab** — run calibrate.py/calibrate_face.py with progress indicator
- **Testing tab** — test Telegram, email, webcam, and location providers
- **About tab** — privacy disclosure and uninstall instructions

---

## How detection works

| Step | What happens |
|------|-------------|
| You type normally | Windows stay counted as **matches** |
| Someone else types | Their different rhythm accumulates **mismatches** |
| 4 mismatch windows hit | Alert pipeline fires silently |
| Pipeline runs | Wi-Fi on → location → screenshot → Telegram |
| 5-minute cooldown | Prevents alert spam |

### Tuning sensitivity
In `config.json`:
- **`tolerance_percent`** — how much deviation is allowed (default 60). Lower = stricter.
- **`mismatch_threshold`** — how many bad windows trigger an alert (default 4). Lower = faster trigger.
- **`mismatch_window`** — keystrokes per evaluation window (default 10). Lower = faster reaction.
- **`face_check_enabled`** — if a face matches the reference, alert is cancelled (default true).

---

## Pre-deployment validation

Before installing, run the config validator:
```
python validate_config.py
```
This checks all 50+ configuration values, tests Telegram/email connectivity,
verifies calibration data, webcam access, and face recognition dependencies.

---

## Files

```
guard/
├── config.json           ← your settings & typing baseline
├── config_ui.py          ← graphical configuration wizard
├── validate_config.py    ← pre-deployment validation tool
├── calibrate.py          ← typing baseline calibrator
├── calibrate_face.py     ← face reference capture
├── main_guard.py         ← the guard process (runs at startup)
├── watchdog.py           ← monitors & restarts guard if it crashes
├── install.py            ← deploy/remove from Windows startup
├── requirements.txt
├── guard.log             ← encrypted event log (AES-256)
├── guard.heartbeat       ← health-check file for watchdog
├── reference_face.pkl    ← stored face encodings
└── README.md
```

---

## Uninstall
```
python install.py --remove
```
This will:
1. Remove both startup registry entries (and verify deletion)
2. Kill all running guard/watchdog processes
3. Delete compiled `.exe` files from `dist/`
4. Clean up build artifacts (`build/`, `*.spec`, `__pycache__/`)
5. Remove runtime data (`guard.log`, `guard.key`, `guard.heartbeat`, `offline_queue/`)
6. Print a detailed summary of what was removed

Manual cleanup (optional):
```
rm config.json reference_face.pkl    # remove calibration data
```

---

## Troubleshooting

### "Location unavailable" in alerts
1. **Windows Location Service**: Settings → Privacy & security → Location → ON
2. **App permission**: Ensure apps are allowed to access location
3. **Internet access**: IP geolocation fallback requires internet
4. **No GPS**: Without GPS hardware, accuracy is city-level via IP

### Telegram commands not responding
1. **Token invalid**: Run `validate_config.py` to check
2. **Chat ID mismatch**: Only the authorised chat ID can send commands
3. **Bot blocked**: If you blocked the bot, unblock it first
4. **Network**: Guard needs internet to poll Telegram

### Guard crashes on startup
1. **Missing dependencies**: `pip install -r requirements.txt`
2. **Face recognition model**: Ensure `face_recognition_models` is installed
3. **Webcam in use**: Close other apps using the camera
4. **Check crash log**: Look for `crash_log.txt` in the guard directory

### False alerts (too many mismatches)
1. **Recalibrate**: Run `python calibrate.py` to update your baseline
2. **Increase tolerance**: Raise `tolerance_percent` in config.json
3. **Increase threshold**: Raise `mismatch_threshold` to require more bad windows
4. **Enable face check**: Set `face_check_enabled: true` — if your face is detected, the alert is cancelled

### "Windows Location Service error" in logs
1. Enable Location: Settings → Privacy → Location → ON
2. Restart the Location Service: `Start-Service lfsvc` (Admin PowerShell)
3. If unavailable, the system falls back to IP geolocation automatically

---

## Common error messages

| Error | Cause | Fix |
|-------|-------|-----|
| `Telegram API error: token invalid` | Bot token is wrong or revoked | Get a new token from @BotFather |
| `Email auth failed` | Wrong password or not an App Password | Generate a Gmail App Password |
| `Unable to open shape_predictor_68_face_landmarks.dat` | Missing face model in bundled EXE | Rebuild with updated `install.py` |
| `No webcam found` | Camera disconnected or in use | Check camera connection |
| `Windows Location Service error` | Location service disabled | Enable in Settings |
| `get_device_info failed` | WMIC not available | Run as Administrator |
| `Heartbeat stale` | Guard process hung | Watchdog will auto-restart |

---

## Platform requirements

| Requirement | Windows | Notes |
|------------|---------|-------|
| Python | 3.8+ | 3.14 recommended |
| OpenCV (`cv2`) | Any | Required for webcam |
| face_recognition | Any | Optional — for face check |
| dlib | Any | Required by face_recognition |
| PyInstaller | Any | Only needed if compiling to .exe |
| Windows Location Service | Windows 10/11 | Optional — IP fallback available |
| Gmail SMTP | Any | Optional — for email backup |
| Telegram | Any | Required for remote alerts |

### Installing dlib on Windows
```
pip install dlib-bin
```
If that fails, install Visual Studio Build Tools and:
```
pip install dlib
```

---

## Security considerations

### Data stored on disk
- **guard.log**: AES-256 encrypted (Fernet), auto-rotated at 5 MB, 2 backups
- **guard.key**: Fernet encryption key — keep this safe; without it logs cannot be decrypted
- **reference_face.pkl**: Contains face encodings (128-d vectors, not the original image)
- **config.json**: Stores Telegram token and email password — protect this file

### Data transmitted
- **Telegram**: Alert messages, location, screenshots, webcam photos
- **Email**: Same alert data sent via Gmail SMTP
- **IP geolocation**: Your public IP is sent to third-party APIs (ip-api.com, ipinfo.io, ipwhois.app)

### What is NOT collected
- Key content (passwords, messages, text) — only **timing** data is analysed
- Browser history, files, personal documents
- Microphone audio
- Network traffic

### Responsible use
This software is designed for **legitimate device protection only**:
- Monitor only devices you own or have explicit permission to monitor
- Comply with all applicable laws in your jurisdiction
- Inform users if installed on shared devices
- Provide a clear uninstall method (included)

---

## Privacy note
The guard analyses **timing only** (how long keys are held, gaps between keys).
The actual keys you press are never stored, logged, or transmitted.
All event logs are encrypted with AES-256 (Fernet) before writing to disk.
