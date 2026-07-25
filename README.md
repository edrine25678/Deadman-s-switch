
# Deadman's Switch — Keystroke-Dynamics Anti-Theft System

Silently monitors your PC's typing rhythm. If someone else uses your device, it enables Wi-Fi, triangulates the location, captures a screenshot, and sends everything to your Telegram account — without alerting the unauthorized user.

## Features

- **Keystroke Dynamics** — Detects unauthorized users by analyzing dwell/flight timing
- **Facial Recognition** — Optional webcam verification reduces false positives
- **Multi-Channel Alerts** — Telegram primary, Gmail SMTP backup
- **Location Tracking** — Windows Location Service + 3-provider IP geolocation fallback
- **Evidence Capture** — Automatic screenshots and webcam photos during alerts
- **Remote Commands** — Control via Telegram: `/status`, `/lock`, `/screenshot`, `/webcam`, `/location`, `/shutdown`
- **Encrypted Logging** — AES-256 (Fernet) encrypted event logs with rotation
- **Watchdog Persistence** — Crash detection with exponential-backoff restart
- **GUI Configuration** — Tkinter setup wizard for all features

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Create a Telegram Bot

1. Open Telegram → search **@BotFather** → send `/newbot`
2. Copy the bot token (format: `123456:ABC-DEF…`)
3. Message your new bot once, then visit:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. Find `"chat":{"id":XXXXXXX}` — that is your **chat ID**

### 3. Configure

```bash
python config_ui.py          # GUI wizard (recommended)
# or manually edit config.json
```

### 4. Calibrate

```bash
python calibrate.py          # ~70 keystrokes to build baseline
python calibrate_face.py     # optional face reference capture
```

### 5. Validate

```bash
python validate_config.py    # 50+ checks: config, Telegram, email, webcam, dependencies
```

### 6. Install to Startup

```bash
python install.py            # run as Administrator
```

### Uninstall

```bash
python install.py --remove
```

## How Detection Works

| Step | What happens |
|------|-------------|
| You type normally | Windows count as **matches** |
| Someone else types | Different rhythm accumulates **mismatches** |
| 4 mismatch windows hit | Alert pipeline fires silently |
| Pipeline runs | Wi-Fi on → location → screenshot → Telegram |
| 5-minute cooldown | Prevents alert spam |

### Tuning Sensitivity

| Parameter | Default | Effect |
|-----------|---------|--------|
| `tolerance_percent` | 60 | How much deviation is allowed. Lower = stricter |
| `mismatch_threshold` | 4 | Bad windows before alert. Lower = faster trigger |
| `mismatch_window` | 10 | Keystrokes per evaluation. Lower = faster reaction |
| `face_check_enabled` | true | Cancel alert if authorized face is detected |

## Project Structure

```
guard_pro/
├── Core
│   ├── main_guard.py         # Main monitoring process
│   ├── watchdog.py           # Process monitor & restarter
│   └── install.py            # Install/uninstall from startup
│
├── Configuration
│   ├── config_ui.py          # Tkinter GUI wizard
│   ├── validate_config.py    # Pre-deployment validator
│   ├── calibrate.py          # Keystroke baseline profiler
│   ├── calibrate_face.py     # Face reference capture
│   └── config.example.json   # Template (copy to config.json)
│
├── Tests
│   ├── test_guard.py         # Unit tests (68)
│   ├── test_integration.py   # Integration tests (28)
│   └── test_full_system.py   # End-to-end tests (39)
│
└── README.md
```

## Testing

```bash
python -m pytest test_guard.py -v          # 68 unit tests
python -m unittest test_integration.py -v  # 28 integration tests
python test_full_system.py                 # 39 E2E tests
```

## Security

- **No key logging** — only timing (dwell/flight) is analyzed; actual keys are never stored
- **Encrypted logs** — AES-256 (Fernet) before writing to disk
- **Telegram-only** — all alerts and remote commands go through Telegram's encrypted API
- **Responsible use** — monitor only devices you own or have permission to monitor

## Data Privacy

The system does not collect or transmit:
- Key content (passwords, messages, typed text)
- Browser history, files, or personal documents
- Microphone audio
- Network traffic


# Deadman-s-switch
Silently monitors your PC's typing rhythm. If someone else uses your device, it enables Wi-Fi, triangulates the location, captures a screenshot, and sends everything to your Telegram account — without alerting the unauthorized user.

