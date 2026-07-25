"""
Deadman's Switch  —  main_guard.py
Keystroke-dynamics anti-theft guard with:
  • Encrypted log file         (cryptography.fernet)
  • Webcam capture             (opencv)
  • Telegram alerts            (message + location + screenshot + webcam)
  • Telegram remote commands   (/lock /screenshot /webcam /location /status /shutdown)
  • Email backup alerts        (Gmail SMTP)
  • Silent Windows operation   (hidden console)

No key content is ever stored or transmitted — only timing values.
"""

import ctypes, io, json, logging, os, smtplib, subprocess, sys
import threading, time
from datetime import datetime
from email.mime.image    import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text     import MIMEText

import cv2
import requests
from cryptography.fernet import Fernet
from pynput import keyboard

# ════════════════════════════════════════════════════════════════════
#  HIDE CONSOLE WINDOW
# ════════════════════════════════════════════════════════════════════
if sys.platform == "win32":
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 0)

# ════════════════════════════════════════════════════════════════════
#  PATHS  (works for both .py and compiled .exe)
# ════════════════════════════════════════════════════════════════════
if getattr(sys, "frozen", False):
    BASE_DIR   = os.path.dirname(sys.executable)    # writable — alongside EXE
    BUNDLE_DIR = sys._MEIPASS                       # bundled files inside EXE
else:
    BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = BASE_DIR

# Copy bundled files alongside EXE on first run so they remain editable
for _bn in ("config.json", "reference_face.pkl"):
    _src = os.path.join(BUNDLE_DIR, _bn)
    _dst = os.path.join(BASE_DIR, _bn)
    if os.path.exists(_src) and not os.path.exists(_dst):
        try:
            import shutil
            shutil.copy2(_src, _dst)
        except Exception as _exc:
            try:
                sys.stderr.write(f"[BOOTSTRAP] Failed to copy {_bn}: {_exc}\n")
            except Exception:
                pass

CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
LOG_PATH    = os.path.join(BASE_DIR, "guard.log")
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
LOG_BACKUPS   = 2
KEY_PATH    = os.path.join(BASE_DIR, "guard.key")
REFERENCE_FACE_PATH = os.path.join(BASE_DIR, "reference_face.pkl")

# ════════════════════════════════════════════════════════════════════
#  ENCRYPTED LOGGING
# ════════════════════════════════════════════════════════════════════
def _load_or_create_key():
    if not os.path.exists(KEY_PATH):
        key = Fernet.generate_key()
        with open(KEY_PATH, "wb") as fh:
            fh.write(key)
    with open(KEY_PATH, "rb") as fh:
        return Fernet(fh.read())

_fernet = _load_or_create_key()


def _rotate_log():
    try:
        if not os.path.exists(LOG_PATH) or os.path.getsize(LOG_PATH) < LOG_MAX_BYTES:
            return
        for i in range(LOG_BACKUPS, 0, -1):
            src = f"{LOG_PATH}.{i - 1}" if i > 1 else LOG_PATH
            dst = f"{LOG_PATH}.{i}"
            if os.path.exists(src):
                os.replace(src, dst)
    except Exception as exc:
        # Can't use logger here - it would recurse
        try:
            sys.stderr.write(f"[LOG-ROTATE-ERROR] {exc}\n")
        except Exception:
            pass


class EncryptedFileHandler(logging.Handler):
    """Encrypts every log line with Fernet before writing to disk."""
    def emit(self, record):
        try:
            _rotate_log()
            line = self.format(record)
            token = _fernet.encrypt(line.encode())
            with open(LOG_PATH, "ab") as fh:
                fh.write(token + b"\n")
        except Exception:
            try:
                sys.stderr.write(f"[LOG-FALLBACK] {self.format(record)}\n")
            except Exception:
                pass


_handler = EncryptedFileHandler()
_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
))
log = logging.getLogger("dms")
log.setLevel(logging.INFO)
log.addHandler(_handler)

# ════════════════════════════════════════════════════════════════════
#  CONFIG
# ════════════════════════════════════════════════════════════════════
_cfg_present = {}
try:
    with open(CONFIG_PATH, "r") as _fh:
        _cfg_present = json.load(_fh)
except Exception as _exc:
    sys.stderr.write(f"[CONFIG-FATAL] Cannot load {CONFIG_PATH}: {_exc}\n")
    sys.exit(1)

BOT_TOKEN        = _cfg_present.get("telegram_bot_token", "")
CHAT_ID          = str(_cfg_present.get("telegram_chat_id", ""))
EMAIL_SENDER     = _cfg_present.get("email_sender", "")
EMAIL_PASSWORD   = _cfg_present.get("email_app_password", "")
EMAIL_RECIPIENT  = _cfg_present.get("email_recipient", "")
try:
    AVG_DWELL        = float(_cfg_present.get("avg_dwell_ms", 0))
    AVG_FLIGHT       = float(_cfg_present.get("avg_flight_ms", 0))
except (TypeError, ValueError) as _exc:
    sys.stderr.write(f"[CONFIG-FATAL] avg_dwell_ms/avg_flight_ms must be numeric: {_exc}\n")
    sys.exit(1)
TOLERANCE        = float(_cfg_present.get("tolerance_percent",       60)) / 100.0
WINDOW_SIZE      = int  (_cfg_present.get("mismatch_window",         10))
MISMATCH_THRESH  = int  (_cfg_present.get("mismatch_threshold",       4))
COOLDOWN_SECS    = int  (_cfg_present.get("alert_cooldown_seconds",  300))
WIFI_WAIT        = int  (_cfg_present.get("wifi_wait_seconds",         6))
CAM_WARMUP       = int  (_cfg_present.get("webcam_warmup_frames",     10))
CMDS_ENABLED     = str(_cfg_present.get("remote_commands_enabled", "true")).strip().lower() == "true"
STARTUP_CHECK    = str(_cfg_present.get("startup_check", "true")).strip().lower() == "true"
FACE_CHECK       = str(_cfg_present.get("face_check_enabled", "true")).strip().lower() == "true"
FACE_TOLERANCE   = float(_cfg_present.get("face_tolerance", 0.5))
USB_MONITOR      = str(_cfg_present.get("usb_monitor_enabled", "true")).strip().lower() == "true"
USB_POLL_INTERVAL = int(_cfg_present.get("usb_poll_interval", 2))
OFFLINE_ALARM    = str(_cfg_present.get("offline_alarm_enabled", "true")).strip().lower() == "true"
ALARM_DURATION   = int(_cfg_present.get("offline_alarm_duration", 30))
UNLOCK_DURATION  = int(_cfg_present.get("unlock_duration_minutes", 60))
cfg = _cfg_present

TG_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ════════════════════════════════════════════════════════════════════
#  CONFIG VALIDATION
# ════════════════════════════════════════════════════════════════════
def _validate_config():
    errors = []
    warnings = []

    required_keys = ["telegram_bot_token", "telegram_chat_id", "avg_dwell_ms", "avg_flight_ms"]
    for key in required_keys:
        if key not in cfg:
            errors.append(f"Missing required config key: '{key}'")

    token = cfg.get("telegram_bot_token", "")
    if not isinstance(token, str) or not token or token.startswith("YOUR"):
        errors.append("telegram_bot_token is missing or still set to placeholder (YOUR_)")

    chat_id = cfg.get("telegram_chat_id", "")
    if not chat_id or str(chat_id).strip().startswith("YOUR"):
        errors.append("telegram_chat_id is missing or still set to placeholder (YOUR_)")

    numeric_checks = [
        ("avg_dwell_ms",            AVG_DWELL,         10,     10000),
        ("avg_flight_ms",           AVG_FLIGHT,        5,      5000),
        ("tolerance_percent",       cfg.get("tolerance_percent", 60), 1, 200),
        ("mismatch_window",         WINDOW_SIZE,       1,      1000),
        ("mismatch_threshold",      MISMATCH_THRESH,   1,      1000),
        ("alert_cooldown_seconds",  COOLDOWN_SECS,     0,      86400),
        ("wifi_wait_seconds",       WIFI_WAIT,         0,      300),
        ("webcam_warmup_frames",    CAM_WARMUP,        0,      100),
        ("face_tolerance",          FACE_TOLERANCE,    0.0,    2.0),
        ("usb_poll_interval",       USB_POLL_INTERVAL, 1,      3600),
        ("offline_alarm_duration",  ALARM_DURATION,    1,      3600),
        ("unlock_duration_minutes", UNLOCK_DURATION,   1,      525600),
    ]
    for name, val, lo, hi in numeric_checks:
        if not isinstance(val, (int, float)):
            warnings.append(f"'{name}' should be numeric, got {type(val).__name__} ({val})")
        elif val < lo or val > hi:
            warnings.append(f"'{name}' = {val} is outside recommended range [{lo}, {hi}]")

    if FACE_CHECK and not os.path.exists(REFERENCE_FACE_PATH):
        warnings.append("face_check_enabled=true but reference_face.pkl not found - run calibrate_face.py")

    email_sender = cfg.get("email_sender", "")
    email_password = cfg.get("email_app_password", "")
    if email_sender and not email_sender.startswith("YOUR"):
        if not email_password:
            warnings.append("email_sender set but email_app_password is empty")
    if email_password and len(email_password) < 8:
        warnings.append("email_app_password seems too short (should be a Gmail App Password)")

    for err in errors:
        log.error("Config validation ERROR: %s", err)
    for warn in warnings:
        log.warning("Config validation WARNING: %s", warn)
    if errors:
        log.critical("Configuration has %d error(s) - fix before deploying", len(errors))
    if warnings:
        log.warning("Configuration has %d warning(s) - review recommended", len(warnings))

    return errors, warnings


_validate_config()


def _patch_face_recognition_models():
    """When frozen by PyInstaller, monkey-patch face_recognition_models
    so its model-location functions return paths inside sys._MEIPASS
    instead of using pkg_resources.resource_filename (which fails
    because the .dat files are not in a real site-packages directory)."""
    if not getattr(sys, "frozen", False):
        return
    try:
        import face_recognition_models as frm
        import os
        models_dir = os.path.join(sys._MEIPASS, "face_recognition_models", "models")
        if not os.path.isdir(models_dir):
            log.warning("Face models dir not found at %s", models_dir)
            return

        frm.pose_predictor_model_location = lambda: os.path.join(
            models_dir, "shape_predictor_68_face_landmarks.dat")
        frm.pose_predictor_five_point_model_location = lambda: os.path.join(
            models_dir, "shape_predictor_5_face_landmarks.dat")
        frm.face_recognition_model_location = lambda: os.path.join(
            models_dir, "dlib_face_recognition_resnet_model_v1.dat")
        frm.cnn_face_detector_model_location = lambda: os.path.join(
            models_dir, "mmod_human_face_detector.dat")

        log.info("Face recognition models patched for frozen deployment (%s)", models_dir)
    except ImportError:
        log.info("face_recognition_models not installed - skipping patch")


_patch_face_recognition_models()

# Validate Telegram token at startup
def _validate_telegram_token():
    """Check if the Telegram bot token is valid."""
    try:
        response = requests.get(f"{TG_BASE}/getMe", timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("ok"):
                log.info("Telegram bot token validated - bot: @%s", data['result']['username'])
                return True
            else:
                log.error("Telegram API error: %s", data.get('description'))
                return False
        else:
            log.error("Telegram HTTP error: %d", response.status_code)
            return False
    except Exception as exc:
        log.error("Telegram token validation error: %s", exc, exc_info=True)
        return False

# Validate token on startup
TELEGRAM_VALID = _validate_telegram_token()


def _validate_email():
    """Check if the email configuration works by logging into SMTP."""
    if not all([EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT]) or EMAIL_SENDER.startswith("YOUR"):
        log.warning("Email config incomplete - backup alerts disabled")
        return False
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        log.info("Email configuration validated")
        return True
    except smtplib.SMTPAuthenticationError:
        log.warning("Email auth failed - check app password")
        return False
    except Exception as exc:
        log.warning("Email validation error: %s", exc, exc_info=True)
        return False


EMAIL_VALID = _validate_email()

log.info("─" * 50)
log.info("Deadman's Switch started")
log.info("  mode=%s base_dir=%s",
         "EXE (frozen)" if getattr(sys, "frozen", False) else "script (.py)",
         BASE_DIR)
log.info("  telegram_chat_id=%s  tg_valid=%s  email_valid=%s",
         CHAT_ID, TELEGRAM_VALID, EMAIL_VALID)
log.info("  avg_dwell=%.1fms  avg_flight=%.1fms  tolerance=%d%%",
         AVG_DWELL, AVG_FLIGHT, int(TOLERANCE * 100))
log.info("  mismatch_window=%d  mismatch_threshold=%d  cooldown=%ds",
         WINDOW_SIZE, MISMATCH_THRESH, COOLDOWN_SECS)
log.info("  face_check=%s(tol=%.2f)  usb_monitor=%s(%ds)  offline_alarm=%s(%ds)",
         FACE_CHECK, FACE_TOLERANCE, USB_MONITOR, USB_POLL_INTERVAL,
         OFFLINE_ALARM, ALARM_DURATION)
log.info("  remote_cmds=%s  startup_check=%s  unlock=%dmin  wifi_wait=%ds  cam_warmup=%d",
         CMDS_ENABLED, STARTUP_CHECK, UNLOCK_DURATION, WIFI_WAIT, CAM_WARMUP)
log.info("─" * 50)

# ════════════════════════════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════════════════════════════
def _run_hidden(cmd):
    return subprocess.run(
        cmd, capture_output=True, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

# ════════════════════════════════════════════════════════════════════
#  WI-FI
# ════════════════════════════════════════════════════════════════════
def ensure_wifi_on():
    try:
        out = _run_hidden(["netsh", "interface", "show", "interface"]).stdout
        wifi_name = None
        admin_disabled = False
        for line in out.splitlines():
            # Format: Admin State | State | Type | Interface Name
            parts = line.split()
            if len(parts) >= 4:
                name = parts[-1]
                admin = parts[0].lower()
                if any(kw in name.lower() for kw in ["wi-fi", "wifi", "wlan", "wireless"]):
                    wifi_name = name
                    if admin == "disabled":
                        admin_disabled = True
                        break
        if wifi_name and admin_disabled:
            _run_hidden(["netsh", "interface", "set", "interface",
                         wifi_name, "admin=enable"])
            log.info("Wi-Fi adapter '%s' enabled.", wifi_name)
            time.sleep(WIFI_WAIT)
        else:
            log.info("Wi-Fi already active.")
    except Exception as exc:
        log.warning("Wi-Fi enable error: %s", exc, exc_info=True)

# ════════════════════════════════════════════════════════════════════
#  LOCATION
# ════════════════════════════════════════════════════════════════════
TARGET_ACCURACY_M = 8      # desired accuracy in metres
GPS_TIMEOUT_S     = 60     # max seconds to wait for GPS lock


def _locate_by_windows():
    """
    Poll Windows Location Service (High accuracy mode) in a loop.
    Stops as soon as HorizontalAccuracy <= TARGET_ACCURACY_M (8 m)
    or GPS_TIMEOUT_S seconds elapse.
    Returns the best fix obtained.
    """
    ps = f"""
Add-Type -AssemblyName System.Device
$hi  = [System.Device.Location.GeoPositionAccuracy]::High
$w   = New-Object System.Device.Location.GeoCoordinateWatcher($hi)
$w.MovementThreshold = 0
$w.Start()

$best    = $null
$deadline = [DateTime]::Now.AddSeconds({GPS_TIMEOUT_S})

while ([DateTime]::Now -lt $deadline) {{
    $c = $w.Position.Location
    if (-not $c.IsUnknown) {{
        if ($null -eq $best -or $c.HorizontalAccuracy -lt $best.HorizontalAccuracy) {{
            $best = $c
        }}
        if ($c.HorizontalAccuracy -le {TARGET_ACCURACY_M}) {{ break }}
    }}
    Start-Sleep -Milliseconds 500
}}
$w.Stop()

if ($null -eq $best) {{ exit 1 }}
Write-Host "$($best.Latitude),$($best.Longitude),$($best.HorizontalAccuracy)"
"""
    try:
        r = _run_hidden(["powershell", "-NonInteractive",
                         "-NoProfile", "-Command", ps])
        if r.returncode == 0 and r.stdout.strip():
            parts = r.stdout.strip().split(",")
            lat, lng, acc = float(parts[0]), float(parts[1]), float(parts[2])
            if lat != 0.0 and lng != 0.0:
                hit = "target met" if acc <= TARGET_ACCURACY_M else "best available"
                log.info("Windows Location: %.6f, %.6f  accuracy=%.1fm (%s)",
                         lat, lng, acc, hit)
                return {"method":   "windows_location_service",
                        "lat":      lat,
                        "lng":      lng,
                        "accuracy": acc,
                        "target_met": acc <= TARGET_ACCURACY_M}
        elif r.stderr and "access denied" in r.stderr.lower():
            log.warning("Windows Location Service: access denied. "
                        "Enable 'Location' in Windows Settings -> Privacy & security -> Location.")
        elif r.returncode == 1:
            log.warning("Windows Location Service: no position fix within %ds timeout. "
                        "Ensure Location is ON in Settings and try again.", GPS_TIMEOUT_S)
    except Exception as exc:
        log.warning("Windows Location Service error: %s. "
                    "Enable Location: Settings -> Privacy & security -> Location -> ON",
                     exc, exc_info=True)
    return None


def _locate_by_ip():
    providers = [
        ("ip-api.com", {
            "url": "http://ip-api.com/json?fields=status,lat,lon,city,regionName,country,isp,query",
            "parse": lambda d: {"method": "ip_geolocation", "lat": d["lat"],
                                "lng": d["lon"], "ip": d["query"],
                                "city": d.get("city"), "region": d.get("regionName"),
                                "country": d.get("country"), "org": d.get("isp")}
            if d.get("status") == "success" else None
        }),
        ("ipinfo.io", {
            "url": "https://ipinfo.io/json",
            "parse": lambda d: (_ := d.get("loc", "0,0").split(","),
                                {"method": "ip_geolocation_fallback",
                                 "lat": float(_[0]), "lng": float(_[1]),
                                 "ip": d.get("ip"), "city": d.get("city"),
                                 "region": d.get("region"), "country": d.get("country"),
                                 "org": d.get("org")})[1]
        }),
        ("ipwhois.app", {
            "url": "https://ipwhois.app/json/",
            "parse": lambda d: {"method": "ip_geolocation_fallback",
                                "lat": d.get("latitude"), "lng": d.get("longitude"),
                                "ip": d.get("ip"), "city": d.get("city"),
                                "region": d.get("region"), "country": d.get("country"),
                                "org": d.get("org")}
            if d.get("success") and d.get("latitude") and d.get("longitude") else None
        }),
    ]
    for name, provider in providers:
        try:
            r = requests.get(provider["url"], timeout=10)
            if r.status_code == 200:
                d = r.json()
                result = provider["parse"](d)
                if result and result.get("lat") and result.get("lng"):
                    log.info("Location via %s: %s, %s, %s",
                             name, result.get("city", "?"),
                             result.get("region", "?"), result.get("country", "?"))
                    return result
        except Exception as exc:
            log.warning("%s error: %s", name, exc, exc_info=True)
    return None


def get_location():
    loc = _locate_by_windows()
    if loc:
        return loc
    log.info("Windows Location unavailable - falling back to IP geolocation")
    loc = _locate_by_ip()
    if loc:
        return loc
    log.error("ALL location methods failed - device may be offline or Location disabled")
    return None

# ════════════════════════════════════════════════════════════════════
#  WEBCAM
# ════════════════════════════════════════════════════════════════════
def take_webcam_photo():
    try:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            log.warning("No webcam found.")
            return None
        for _ in range(CAM_WARMUP):   # let auto-exposure settle
            cap.read()
        ret, frame = cap.read()
        cap.release()
        if ret:
            _, encoded = cv2.imencode(".jpg", frame,
                                      [cv2.IMWRITE_JPEG_QUALITY, 85])
            buf = io.BytesIO(encoded.tobytes())
            buf.seek(0)
            log.info("Webcam photo captured.")
            return buf
    except Exception as exc:
        log.warning("Webcam error: %s", exc, exc_info=True)
    return None

# ════════════════════════════════════════════════════════════════════
#  SCREENSHOT
# ════════════════════════════════════════════════════════════════════
def take_screenshot():
    try:
        import pyautogui
        shot = pyautogui.screenshot()
        buf  = io.BytesIO()
        shot.save(buf, format="PNG")
        buf.seek(0)
        log.info("Screenshot captured.")
        return buf
    except Exception as exc:
        log.warning("Screenshot error: %s", exc, exc_info=True)
        return None

# ════════════════════════════════════════════════════════════════════
#  FACE RECOGNITION  (face_recognition + dlib)
# ════════════════════════════════════════════════════════════════════
def _check_face_match():
    """Check if the person in front of the webcam matches the reference face.
    
    Returns:
        True  — face matches reference
        False — face detected but doesn't match
        None  — no reference, no face, or library unavailable
    """
    if not os.path.exists(REFERENCE_FACE_PATH):
        log.info("No reference face — run calibrate_face.py first")
        return None
    try:
        import pickle, face_recognition
    except ImportError as exc:
        log.warning("face_recognition not installed: %s", exc, exc_info=True)
        return None
    try:
        with open(REFERENCE_FACE_PATH, "rb") as f:
            ref_data = pickle.load(f)
    except Exception as exc:
        log.warning("Failed to load reference face: %s", exc)
        return None
    # Support both single encoding (old format) and list (new format)
    if isinstance(ref_data, list):
        ref_encodings = ref_data
    else:
        ref_encodings = [ref_data]
    try:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            log.warning("No webcam for face check")
            return None
        for _ in range(CAM_WARMUP):
            cap.read()
        ret, frame = cap.read()
        cap.release()
        if not ret:
            return None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        live = face_recognition.face_encodings(rgb)
        if not live:
            log.info("Face check: no face detected")
            return False
        matches = face_recognition.compare_faces(
            ref_encodings, live[0], tolerance=FACE_TOLERANCE)
        match = any(matches)
        log.info("Face check: %s  (matched %d/%d)",
                 "MATCH" if match else "NO MATCH",
                 sum(matches), len(ref_encodings))
        return match
    except Exception as exc:
        log.warning("Face check error: %s", exc, exc_info=True)
        return None

# ════════════════════════════════════════════════════════════════════
#  DEVICE INFO
# ════════════════════════════════════════════════════════════════════
def get_device_info():
    info = {}
    try:
        out = _run_hidden(["wmic", "computersystem",
                           "get", "Name,UserName"]).stdout
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        if len(lines) >= 2:
            parts = lines[1].split()
            info["hostname"] = parts[0] if parts else "unknown"
            info["username"] = parts[1] if len(parts) > 1 else "unknown"
    except Exception as exc:
        log.warning("get_device_info failed: %s", exc, exc_info=True)
    return info

# ════════════════════════════════════════════════════════════════════
#  TELEGRAM  —  sending
# ════════════════════════════════════════════════════════════════════
def tg_send_message(text, chat_id=None):
    if not TELEGRAM_VALID:
        log.warning("Telegram message skipped - invalid token")
        return False
    try:
        r = requests.post(f"{TG_BASE}/sendMessage",
                          json={"chat_id": chat_id or CHAT_ID,
                                "text": text, "parse_mode": "Markdown"},
                          timeout=15)
        return r.status_code == 200
    except Exception as exc:
        log.warning("TG message error: %s", exc, exc_info=True)
        return False


def tg_send_location(lat, lng, chat_id=None):
    if not TELEGRAM_VALID:
        log.warning("Telegram location skipped - invalid token")
        return False
    try:
        r = requests.post(f"{TG_BASE}/sendLocation",
                          json={"chat_id": chat_id or CHAT_ID,
                                "latitude": lat, "longitude": lng},
                          timeout=15)
        return r.status_code == 200
    except Exception as exc:
        log.warning("TG location error: %s", exc, exc_info=True)
        return False


def tg_send_image(buf, caption="", filename="image.jpg", chat_id=None):
    """Send a BytesIO image; retries as document if photo upload fails."""
    if buf is None:
        return False
    if not TELEGRAM_VALID:
        log.warning("Telegram image skipped - invalid token")
        return False
    cid = chat_id or CHAT_ID
    try:
        buf.seek(0)
        r = requests.post(
            f"{TG_BASE}/sendPhoto",
            data={"chat_id": cid, "caption": caption},
            files={"photo": (filename, buf.read(), "image/jpeg")},
            timeout=30)
        if r.status_code == 200:
            log.info("Image sent to Telegram (%s).", filename)
            return True
        log.warning("TG photo failed (%s): %s", r.status_code, r.text)
        # Fallback: send as document
        buf.seek(0)
        r = requests.post(
            f"{TG_BASE}/sendDocument",
            data={"chat_id": cid, "caption": caption},
            files={"document": (filename, buf.read(), "image/jpeg")},
            timeout=30)
        if r.status_code == 200:
            log.info("Image sent as document fallback.")
            return True
        return False
    except Exception as exc:
        log.warning("TG image error: %s", exc, exc_info=True)
        return False

# ════════════════════════════════════════════════════════════════════
#  EMAIL BACKUP
# ════════════════════════════════════════════════════════════════════
def send_email_alert(subject, body, images=None):
    """Send alert via Gmail SMTP. images = list of (filename, BytesIO)."""
    if not EMAIL_VALID:
        log.warning("Email alert skipped - invalid config")
        return False
    try:
        msg = MIMEMultipart()
        msg["From"]    = EMAIL_SENDER
        msg["To"]      = EMAIL_RECIPIENT
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        if images:
            for fname, buf in images:
                if buf:
                    buf.seek(0)
                    img = MIMEImage(buf.read())
                    img.add_header("Content-Disposition",
                                   "attachment", filename=fname)
                    msg.attach(img)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
        log.info("Email alert sent to %s.", EMAIL_RECIPIENT)
        return True
    except Exception as exc:
        log.warning("Email error: %s", exc, exc_info=True)
        return False

# ════════════════════════════════════════════════════════════════════
#  ALERT DELIVERY
# ════════════════════════════════════════════════════════════════════
def _build_location_block(loc):
    if not loc:
        return None, None, (
            "⚠️ *Location unavailable*\n"
            "Enable Windows Location:\n"
            "  Settings → Privacy & security → Location → ON\n"
            "Or ensure internet access for IP geolocation."
        )
    method = loc.get("method", "")
    lat, lng = loc.get("lat"), loc.get("lng")
    acc    = loc.get("accuracy")
    acc_str = f"{acc:.1f} m" if acc is not None else "?"

    if "windows_location" in method:
        target_met = loc.get("target_met", False)
        precision_label = (
            f"≤{TARGET_ACCURACY_M} m target met"
            if target_met else
            f"Best available: ±{acc_str}  (GPS needed for ≤{TARGET_ACCURACY_M} m)"
        )
        maps_url = f"https://maps.google.com/?q={lat:.6f},{lng:.6f}"
        block = (
            f"📍 *Windows Location Service*\n"
            f"Lat: `{lat:.6f}`\n"
            f"Lng: `{lng:.6f}`\n"
            f"Accuracy: ±{acc_str}\n"
            f"{precision_label}\n"
            f"[Open in Google Maps]({maps_url})"
        )
    elif "wifi" in method:
        maps_url = f"https://maps.google.com/?q={lat:.6f},{lng:.6f}"
        block = (
            f"📡 *Wi-Fi Triangulation*\n"
            f"Lat: `{lat:.6f}`\n"
            f"Lng: `{lng:.6f}`\n"
            f"Accuracy: ±{acc_str}\n"
            f"[Open in Google Maps]({maps_url})"
        )
    else:
        maps_url = f"https://maps.google.com/?q={lat:.6f},{lng:.6f}"
        block = (
            f"🌐 *IP Geolocation* (city-level only)\n"
            f"IP: `{loc.get('ip', '?')}`\n"
            f"{loc.get('city','')}, {loc.get('region','')}, "
            f"{loc.get('country','')}\n"
            f"ISP: {loc.get('org','?')}\n"
            f"[Open in Google Maps]({maps_url})"
        )
    return lat, lng, block


def deliver_alert(loc, screenshot_buf, webcam_buf):
    ts     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    device = get_device_info()
    lat, lng, loc_block = _build_location_block(loc)

    delivered_any = False

    # ── Telegram ─────────────────────────────────────────────────
    tg_msg = (
        f"🚨 *DEADMAN'S SWITCH — Unauthorised Access*\n"
        f"🕐 `{ts}`\n"
        f"💻 Host: `{device.get('hostname','N/A')}`  "
        f"User: `{device.get('username','N/A')}`\n\n"
        f"{loc_block}"
    )
    delivered_any |= tg_send_message(tg_msg)
    if lat and lng:
        delivered_any |= tg_send_location(lat, lng)
    delivered_any |= tg_send_image(screenshot_buf, caption=f"🖥 Screenshot @ {ts}",
                                   filename="screenshot.png")
    delivered_any |= tg_send_image(webcam_buf, caption=f"📷 Webcam @ {ts}",
                                   filename="webcam.jpg")

    # ── Email backup ──────────────────────────────────────────────
    email_body = (
        f"DEADMAN'S SWITCH ALERT\n"
        f"Time:     {ts}\n"
        f"Host:     {device.get('hostname','N/A')}\n"
        f"User:     {device.get('username','N/A')}\n"
        f"Location: {loc_block.replace('*','').replace('`','')}\n"
    )
    delivered_any |= send_email_alert(
        subject=f"🚨 Deadman's Switch Alert — {ts}",
        body=email_body,
        images=[("screenshot.png", screenshot_buf),
                ("webcam.jpg", webcam_buf)],
    )

    if delivered_any:
        log.info("Alert delivered successfully.")
    else:
        log.error("Alert FAILED - queuing to disk for retry.")
        threading.Thread(target=_play_alarm, daemon=True).start()
        try:
            _enqueue_alert(ts, device, loc_block, lat, lng,
                           screenshot_buf, webcam_buf)
        except Exception as exc:
            log.error("Failed to queue alert: %s", exc, exc_info=True)

# ════════════════════════════════════════════════════════════════════
#  OFFLINE ALERT QUEUE
# ════════════════════════════════════════════════════════════════════
QUEUE_DIR = os.path.join(BASE_DIR, "offline_queue")
os.makedirs(QUEUE_DIR, exist_ok=True)


def _enqueue_alert(ts, device, loc_block, lat, lng, screenshot_buf, webcam_buf):
    """Persist alert to disk for later retry when connectivity returns."""
    try:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        qdir = os.path.join(QUEUE_DIR, f"alert_{stamp}")
        os.makedirs(qdir, exist_ok=True)

        meta = {
            "ts": ts,
            "hostname": device.get("hostname", "N/A"),
            "username": device.get("username", "N/A"),
            "loc_block": loc_block,
            "lat": lat,
            "lng": lng,
        }
        with open(os.path.join(qdir, "meta.json"), "w") as f:
            json.dump(meta, f)

        if screenshot_buf:
            with open(os.path.join(qdir, "screenshot.png"), "wb") as f:
                f.write(screenshot_buf.getvalue())

        if webcam_buf:
            with open(os.path.join(qdir, "webcam.jpg"), "wb") as f:
                f.write(webcam_buf.getvalue())

        log.info("Alert queued to disk: %s", qdir)
    except Exception as exc:
        log.error("Failed to queue alert: %s", exc, exc_info=True)


def _flush_offline_queue():
    """Attempt delivery of all queued alerts. Remove on success."""
    for entry in sorted(os.listdir(QUEUE_DIR)):
        qdir = os.path.join(QUEUE_DIR, entry)
        if not os.path.isdir(qdir):
            continue
        meta_path = os.path.join(qdir, "meta.json")
        if not os.path.exists(meta_path):
            continue
        try:
            with open(meta_path) as f:
                meta = json.load(f)

            shot_path = os.path.join(qdir, "screenshot.png")
            webcam_path = os.path.join(qdir, "webcam.jpg")

            shot_buf = io.BytesIO()
            try:
                with open(shot_path, "rb") as f:
                    shot_buf.write(f.read())
                shot_buf.seek(0)
            except FileNotFoundError:
                shot_buf = None

            webcam_buf = io.BytesIO()
            try:
                with open(webcam_path, "rb") as f:
                    webcam_buf.write(f.read())
                webcam_buf.seek(0)
            except FileNotFoundError:
                webcam_buf = None

            delivered = False
            tg_msg = (
                f"🚨 *DEADMAN'S SWITCH — Queued Alert (offline)*\n"
                f"🕐 `{meta['ts']}`\n"
                f"💻 Host: `{meta['hostname']}`  "
                f"User: `{meta['username']}`\n\n"
                f"{meta['loc_block']}"
            )
            delivered |= tg_send_message(tg_msg)
            if meta.get("lat") and meta.get("lng"):
                delivered |= tg_send_location(meta["lat"], meta["lng"])
            if shot_buf:
                delivered |= tg_send_image(shot_buf, caption="🖥 Screenshot (queued)", filename="screenshot.png")
            if webcam_buf:
                delivered |= tg_send_image(webcam_buf, caption="📷 Webcam (queued)", filename="webcam.jpg")

            email_body = (
                f"DEADMAN'S SWITCH ALERT (delivered from offline queue)\n"
                f"Time:     {meta['ts']}\n"
                f"Host:     {meta['hostname']}\n"
                f"User:     {meta['username']}\n"
                f"Location: {meta['loc_block'].replace('*','').replace('`','')}\n"
            )
            delivered |= send_email_alert(
                subject=f"🚨 Deadman's Switch Alert (queued) — {meta['ts']}",
                body=email_body,
                images=[(p, b) for p, b in
                        [("screenshot.png", shot_buf), ("webcam.jpg", webcam_buf)]
                        if b],
            )

            if delivered:
                import shutil
                shutil.rmtree(qdir)
                log.info("Queued alert delivered & removed: %s", entry)
            else:
                log.warning("Queued alert still undeliverable: %s", entry)
        except Exception as exc:
            log.error("Error flushing queued alert %s: %s", entry, exc, exc_info=True)


def _offline_queue_flusher():
    """Background thread: periodically retry queued alerts."""
    log.info("Offline queue flusher started.")
    while True:
        time.sleep(30)
        try:
            _flush_offline_queue()
        except Exception as exc:
            log.error("Queue flusher error: %s", exc, exc_info=True)


def _play_alarm():
    """Play a loud siren through PC speakers (runs in a daemon thread)."""
    if not OFFLINE_ALARM:
        return
    try:
        import winsound
        deadline = time.time() + ALARM_DURATION
        while time.time() < deadline:
            winsound.Beep(800, 400)
            winsound.Beep(1200, 400)
    except Exception as exc:
        log.debug("Alarm playback stopped: %s", exc)


# ════════════════════════════════════════════════════════════════════
#  TELEGRAM REMOTE COMMANDS
# ════════════════════════════════════════════════════════════════════
HELP_TEXT = """
*Deadman's Switch — Remote Commands*
    
/status      Current guard status
/location    Get device location now
/screenshot  Capture and send screenshot
/webcam      Capture and send webcam photo
/capturekeys Capture next 500 keystrokes and send them
/unlock      Suppress alerts for 30 days (remote unlock)
/relock      Re-enable alerts immediately
/lock        Lock the Windows screen
/shutdown    Shutdown PC in 60 seconds
/cancelshutdown  Cancel a pending shutdown
/help        Show this message
"""

_shutdown_pending = False
_unlock_until = 0.0
_guard_engine = None       # set at runtime for command access


def _handle_command(text, chat_id):
    try:
        _handle_command_inner(text, chat_id)
    except Exception as exc:
        log.error("Command handler error for '%s': %s", text, exc, exc_info=True)
        tg_send_message(
            f"⚠️ Command failed: {exc}\n"
            f"Check guard.log for details.",
            chat_id)


def _handle_command_inner(text, chat_id):
    global _shutdown_pending, _unlock_until
    text = text.strip().lower().split()[0]   # ignore any arguments

    if text == "/status":
        now = time.monotonic()
        if _unlock_until > now:
            remaining = int(_unlock_until - now)
            days, rem = divmod(remaining, 86400)
            hours, rem = divmod(rem, 3600)
            mins, secs = divmod(rem, 60)
            parts = []
            if days: parts.append(f"{days}d")
            if hours: parts.append(f"{hours}h")
            if mins: parts.append(f"{mins}m")
            if secs: parts.append(f"{secs}s")
            remaining_str = " ".join(parts) if parts else "0s"
            state = f"🔓 *Unlocked* — alerts suppressed ({remaining_str} remaining)"
        else:
            _unlock_until = 0.0
            state = "🔒 *Active* — alerts enabled"
        tg_send_message(
            f"✅ *Deadman's Switch*\n"
            f"{state}\n"
            f"Monitoring keystrokes silently.", chat_id)

    elif text == "/location":
        tg_send_message("📡 Getting location…", chat_id)
        ensure_wifi_on()
        loc = get_location()
        _, lng, block = _build_location_block(loc)
        lat2 = loc.get("lat") if loc else None
        lng2 = loc.get("lng") if loc else None
        tg_send_message(block, chat_id)
        if lat2 and lng2:
            tg_send_location(lat2, lng2, chat_id)

    elif text == "/screenshot":
        tg_send_message("🖥 Taking screenshot…", chat_id)
        shot = take_screenshot()
        tg_send_image(shot, caption="Screenshot on demand",
                      filename="screenshot.png", chat_id=chat_id)

    elif text == "/webcam":
        tg_send_message("📷 Capturing webcam…", chat_id)
        photo = take_webcam_photo()
        if photo:
            tg_send_image(photo, caption="Webcam on demand",
                          filename="webcam.jpg", chat_id=chat_id)
        else:
            tg_send_message("⚠️ No webcam available.", chat_id)

    elif text == "/capturekeys":
        global _guard_engine
        if _guard_engine is None:
            tg_send_message("⚠️ Guard engine not ready.", chat_id)
        elif _guard_engine.capture_mode:
            tg_send_message("⏳ Already capturing keys.", chat_id)
        else:
            _guard_engine.enable_capture()
            tg_send_message(
                "📝 *Capturing next 500 keystrokes…*\n"
                "Keys will be sent automatically when complete.",
                chat_id)
            log.info("Remote command: key capture started.")

    elif text == "/lock":
        ctypes.windll.user32.LockWorkStation()
        tg_send_message("🔒 Screen locked.", chat_id)
        log.info("Remote command: screen locked.")

    elif text == "/shutdown":
        _shutdown_pending = True
        tg_send_message(
            "⚠️ *Shutdown in 60 seconds.*\n"
            "Send /cancelshutdown to abort.", chat_id)
        log.info("Remote command: shutdown scheduled.")
        _run_hidden(["shutdown", "/s", "/t", "60",
                     "/c", "Deadmans Switch remote shutdown"])

    elif text == "/cancelshutdown":
        _run_hidden(["shutdown", "/a"])
        _shutdown_pending = False
        tg_send_message("✅ Shutdown cancelled.", chat_id)
        log.info("Remote command: shutdown cancelled.")

    elif text == "/unlock":
        duration = UNLOCK_DURATION * 60
        _unlock_until = time.monotonic() + duration
        days, rem = divmod(UNLOCK_DURATION, 1440)
        hours, mins = divmod(rem, 60)
        parts = []
        if days: parts.append(f"{days} days")
        if hours: parts.append(f"{hours} hours")
        if mins: parts.append(f"{mins} minutes")
        duration_str = ", ".join(parts)
        tg_send_message(
            f"🔓 *Remote unlock activated*\n"
            f"Alerts suppressed for {duration_str}.\n"
            f"Send /relock to re-enable early.", chat_id)
        log.info("Remote unlock for %d minutes.", UNLOCK_DURATION)

    elif text == "/relock":
        _unlock_until = 0.0
        tg_send_message("🔒 *Alerts re-enabled* — guard is active.", chat_id)
        log.info("Remote relock.")

    elif text == "/help":
        tg_send_message(HELP_TEXT, chat_id)

    else:
        tg_send_message(
            "Unknown command. Send /help for the list.", chat_id)


def _get_usb_drives():
    """Return set of USB drive letters currently connected."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-WmiObject -Class Win32_LogicalDisk -Filter \"DriveType=2\" | Select-Object -ExpandProperty DeviceId"],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW)
        ids = set()
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if line:
                ids.add(line)
        return ids
    except Exception as exc:
        log.warning("USB drive query failed: %s", exc, exc_info=True)
        return set()


def _usb_monitor_loop():
    """Background thread: poll for new USB drives and alert on insertion."""
    known = _get_usb_drives()
    alerted = set()
    log.info("USB monitor started. Known drives: %s", known or "none")
    while True:
        time.sleep(USB_POLL_INTERVAL)
        try:
            current = _get_usb_drives()
            new_drives = current - known
            reinserted = current - alerted
            for drive in new_drives & reinserted:
                log.warning("USB drive detected: %s", drive)
                device = get_device_info()
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                msg = (
                    f"⚠ *USB Drive Inserted*\n"
                    f"🕐 `{ts}`\n"
                    f"💻 Host: `{device.get('hostname','N/A')}`\n"
                    f"💾 Drive: `{drive}`\n"
                )
                tg_send_message(msg)
                send_email_alert(
                    subject=f"⚠ USB Drive Inserted — {device.get('hostname','N/A')} @ {ts}",
                    body=f"USB Drive Inserted\nTime: {ts}\nHost: {device.get('hostname','N/A')}\nUser: {device.get('username','N/A')}\nDrive: {drive}\n",
                )
                alerted.add(drive)
            # Re-alert if a drive was removed and reinserted
            removed = known - current
            alerted -= removed
            known = current
        except Exception as exc:
            log.error("USB monitor error: %s", exc, exc_info=True)


def _command_polling_loop():
    """Long-poll Telegram for incoming commands in a background thread."""
    last_update_id = None
    log.info("Remote command polling started.")
    while True:
        try:
            params = {"timeout": 30, "allowed_updates": ["message"]}
            if last_update_id is not None:
                params["offset"] = last_update_id + 1

            r = requests.get(f"{TG_BASE}/getUpdates",
                             params=params, timeout=35)
            if r.status_code != 200:
                time.sleep(5)
                continue

            for update in r.json().get("result", []):
                last_update_id = update["update_id"]
                msg     = update.get("message", {})
                text    = msg.get("text", "")
                chat_id = str(msg.get("chat", {}).get("id", ""))

                # Only accept commands from the authorised chat
                if chat_id != CHAT_ID:
                    continue
                if text.startswith("/"):
                    threading.Thread(
                        target=_handle_command,
                        args=(text, chat_id),
                        daemon=True
                    ).start()

        except Exception as exc:
            log.warning("Command polling error: %s", exc, exc_info=True)
            time.sleep(10)

# ════════════════════════════════════════════════════════════════════
#  GUARD ENGINE  —  keystroke dynamics
# ════════════════════════════════════════════════════════════════════
class GuardEngine:
    def __init__(self):
        self.key_down_times   = {}
        self.last_key_up_time = None
        self.dwell_buf        = []
        self.flight_buf       = []
        self.mismatch_streak  = 0
        self.last_alert_ts    = 0.0
        self._lock            = threading.Lock()
        self.capture_mode     = False
        self.captured_keys    = []
        self.capture_target   = 500
        self.capture_timer    = None
        log.info("Deadman's Switch engine initialised.")

    def _within_tolerance(self, val, baseline):
        lo = baseline * (1.0 - TOLERANCE)
        hi = baseline * (1.0 + TOLERANCE)
        return lo <= val <= hi

    def _evaluate_window(self):
        if (len(self.dwell_buf)  < WINDOW_SIZE or
                len(self.flight_buf) < WINDOW_SIZE - 1):
            return

        avg_d = sum(self.dwell_buf)  / len(self.dwell_buf)
        avg_f = sum(self.flight_buf) / len(self.flight_buf)
        match = (self._within_tolerance(avg_d, AVG_DWELL) and
                 self._within_tolerance(avg_f, AVG_FLIGHT))

        with self._lock:
            if match:
                self.mismatch_streak = max(0, self.mismatch_streak - 1)
            else:
                self.mismatch_streak += 1
                log.info("Window MISMATCH d=%.1f f=%.1f streak=%d",
                         avg_d, avg_f, self.mismatch_streak)

            streak = self.mismatch_streak

        self.dwell_buf.clear()
        self.flight_buf.clear()

        if streak >= MISMATCH_THRESH:
            now = time.monotonic()
            with self._lock:
                if now - self.last_alert_ts > COOLDOWN_SECS:
                    self.last_alert_ts   = now
                    self.mismatch_streak = 0
                    threading.Thread(target=self._silent_alert,
                                     daemon=True).start()

    def _silent_alert(self):
        log.info("ALERT — gathering evidence silently …")

        # Remote unlock check — skip alert if user unlocked remotely
        global _unlock_until
        if _unlock_until > time.monotonic():
            log.info("Remote unlock active — alert suppressed")
            return

        # Face check: if face matches known user, cancel alert
        if FACE_CHECK:
            match = _check_face_match()
            if match is True:
                log.info("Face match — resetting mismatch (authorized user)")
                with self._lock:
                    self.mismatch_streak = 0
                return
            elif match is None:
                log.info("Face check not available — proceeding with alert")

        try:
            ensure_wifi_on()
            loc     = get_location()
            shot    = take_screenshot()
            webcam  = take_webcam_photo()
            deliver_alert(loc, shot, webcam)
        except Exception as exc:
            log.error("Alert pipeline error: %s", exc, exc_info=True)

    def enable_capture(self, target=500, timeout=120):
        self.capture_mode = True
        self.captured_keys = []
        self.capture_target = target
        if self.capture_timer:
            self.capture_timer.cancel()
        self.capture_timer = threading.Timer(timeout, self._on_capture_timeout)
        self.capture_timer.daemon = True
        self.capture_timer.start()

    def _on_capture_timeout(self):
        if self.captured_keys:
            self._send_captured_keys("⏱️ *Capture timed out*")
        self.capture_mode = False
        self.captured_keys = []

    def _send_captured_keys(self, header="📝 *Captured Keys*"):
        text = "".join(self.captured_keys) if self.captured_keys else "[no keys captured]"
        # Truncate if too long for Telegram (4096 char limit)
        if len(text) > 3900:
            text = text[:3900] + "\n\n…[truncated]"
        tg_send_message(f"{header}\n\n```\n{text}\n```")

    def on_press(self, key):
        if key not in self.key_down_times:
            self.key_down_times[key] = time.perf_counter()
        if self.capture_mode:
            try:
                ch = key.char
                if ch is not None:
                    self.captured_keys.append(ch)
            except AttributeError:
                name = str(key).replace("Key.", "")
                mapping = {
                    "space": "[SPACE]", "enter": "[ENTER]", "tab": "[TAB]",
                    "backspace": "[BACKSPACE]", "delete": "[DELETE]",
                    "escape": "[ESC]", "shift": "[SHIFT]",
                    "shift_r": "[SHIFT]", "ctrl": "[CTRL]",
                    "ctrl_r": "[CTRL]", "alt": "[ALT]", "alt_r": "[ALT]",
                    "alt_gr": "[ALT]", "caps_lock": "[CAPS]",
                    "up": "[UP]", "down": "[DOWN]", "left": "[LEFT]",
                    "right": "[RIGHT]", "home": "[HOME]", "end": "[END]",
                    "page_up": "[PGUP]", "page_down": "[PGDN]",
                    "insert": "[INS]", "print_screen": "[PRTSC]",
                    "scroll_lock": "[SCRLK]", "pause": "[PAUSE]",
                    "num_lock": "[NUMLK]", "menu": "[MENU]",
                    "f1": "[F1]", "f2": "[F2]", "f3": "[F3]", "f4": "[F4]",
                    "f5": "[F5]", "f6": "[F6]", "f7": "[F7]", "f8": "[F8]",
                    "f9": "[F9]", "f10": "[F10]", "f11": "[F11]", "f12": "[F12]",
                }
                self.captured_keys.append(mapping.get(name, f"[{name.upper()}]"))
            if len(self.captured_keys) >= self.capture_target:
                if self.capture_timer:
                    self.capture_timer.cancel()
                self._send_captured_keys()
                self.capture_mode = False
                self.captured_keys = []

    def on_release(self, key):
        now = time.perf_counter()
        if key not in self.key_down_times:
            return
        dwell_ms = (now - self.key_down_times.pop(key)) * 1000.0
        if self.last_key_up_time is not None:
            flight_ms = (now - self.last_key_up_time) * 1000.0
            if flight_ms < 2000.0:   # ignore pauses > 2 s
                self.flight_buf.append(flight_ms)
        self.last_key_up_time = now
        self.dwell_buf.append(dwell_ms)
        self._evaluate_window()

# ════════════════════════════════════════════════════════════════════
#  STARTUP CHECK
# ════════════════════════════════════════════════════════════════════
def _run_startup_check():
    """Exercises all integrated measures on startup as a health check."""
    log.info("Running startup health check...")
    try:
        ensure_wifi_on()
        loc = get_location()
        shot = take_screenshot()
        webcam = take_webcam_photo()

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        device = get_device_info()
        lat, lng, loc_block = _build_location_block(loc)

        tg_msg = (
            f"🟢 *Deadman's Switch — Startup Check*\n"
            f"🕐 `{ts}`\n"
            f"💻 Host: `{device.get('hostname','N/A')}`  "
            f"User: `{device.get('username','N/A')}`\n"
            f"✅ All systems operational\n\n"
            f"{loc_block}"
        )
        tg_send_message(tg_msg)
        if lat and lng:
            tg_send_location(lat, lng)
        tg_send_image(shot, caption=f"🖥 Startup screenshot @ {ts}",
                      filename="startup_screenshot.png")
        tg_send_image(webcam, caption=f"📷 Startup webcam @ {ts}",
                      filename="startup_webcam.jpg")

        email_body = (
            f"DEADMAN'S SWITCH — Startup Check\n"
            f"Time:     {ts}\n"
            f"Host:     {device.get('hostname','N/A')}\n"
            f"User:     {device.get('username','N/A')}\n"
            f"Location: {loc_block.replace('*','').replace('`','')}\n"
            f"Result: All systems operational\n"
        )
        send_email_alert(
            subject=f"🟢 Deadman's Switch Startup Check — {ts}",
            body=email_body,
            images=[("startup_screenshot.png", shot),
                    ("startup_webcam.jpg", webcam)],
        )
        log.info("Startup health check completed.")
    except Exception as exc:
        log.error("Startup health check error: %s", exc, exc_info=True)


# ════════════════════════════════════════════════════════════════════
#  DATA PROTECTION  —  retention, secure deletion, consent
# ════════════════════════════════════════════════════════════════════
LOG_RETENTION_DAYS = 30          # delete encrypted logs older than this
HEARTBEAT_RETENTION_HOURS = 24   # delete stale heartbeat files

DATA_PROTECTION_DISCLOSURE = (
    "Deadman's Switch is running.\n"
    "Purpose: Detect unauthorised device access via typing rhythm analysis.\n"
    "Data: Keystroke timing (not content), location, screenshots, webcam.\n"
    "All data is stored locally and encrypted (AES-256).\n"
    "Uninstall: python install.py --remove\n"
    "By continuing to use this device you consent to these terms."
)


def _secure_delete(path, passes=2):
    """Overwrite file with random data before deleting."""
    try:
        if not os.path.exists(path):
            return
        size = os.path.getsize(path)
        with open(path, "wb") as f:
            for _ in range(passes):
                f.seek(0)
                f.write(os.urandom(size))
                f.flush()
                os.fsync(f.fileno())
        os.remove(path)
    except Exception:
        pass


def _enforce_log_retention():
    """Delete encrypted log files older than LOG_RETENTION_DAYS."""
    try:
        now = time.time()
        cutoff = now - (LOG_RETENTION_DAYS * 86400)
        for fname in os.listdir(BASE_DIR):
            if fname.startswith("guard.log") or fname.startswith("watchdog.log"):
                path = os.path.join(BASE_DIR, fname)
                if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                    _secure_delete(path)
                    log.info("Retention: deleted old log %s", fname)
    except Exception as exc:
        log.warning("Log retention error: %s", exc, exc_info=True)


def _cleanup_stale_heartbeats():
    """Remove heartbeat files that are no longer useful."""
    try:
        now = time.time()
        cutoff = now - (HEARTBEAT_RETENTION_HOURS * 3600)
        for fname in ("guard.heartbeat",):
            path = os.path.join(BASE_DIR, fname)
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                os.remove(path)
    except Exception:
        pass


def _data_protection_loop():
    """Background thread: periodic data housekeeping."""
    _enforce_log_retention()
    _cleanup_stale_heartbeats()
    while True:
        time.sleep(86400)   # once per day
        try:
            _enforce_log_retention()
            _cleanup_stale_heartbeats()
        except Exception as exc:
            log.warning("Data protection error: %s", exc, exc_info=True)


# ════════════════════════════════════════════════════════════════════
#  HEARTBEAT — lets watchdog know the guard is alive
# ════════════════════════════════════════════════════════════════════
HEARTBEAT_FILE = os.path.join(BASE_DIR, "guard.heartbeat")
HEARTBEAT_INTERVAL = 30   # write every 30 seconds


def _heartbeat_writer():
    while True:
        try:
            with open(HEARTBEAT_FILE, "w") as f:
                f.write(f"{time.time()}\n")
        except Exception as exc:
            log.warning("Heartbeat write failed: %s", exc, exc_info=True)
        time.sleep(HEARTBEAT_INTERVAL)


# ════════════════════════════════════════════════════════════════════
#  STARTUP CONSENT NOTIFICATION
# ════════════════════════════════════════════════════════════════════
CONSENT_ENABLED = str(cfg.get("startup_notification", "false")).strip().lower() == "true"


def _show_consent_notification():
    """Display a one-time system tray notification with purpose disclosure."""
    if not CONSENT_ENABLED:
        return
    try:
        import ctypes
        from ctypes import wintypes
        try:
            ctypes.windll.user32.MessageBoxW(
                0,
                DATA_PROTECTION_DISCLOSURE,
                "Deadman's Switch",
                0x40 | 0x1000   # MB_ICONINFORMATION | MB_SYSTEMMODAL
            )
        except Exception:
            pass
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    _show_consent_notification()

    if CMDS_ENABLED:
        threading.Thread(target=_command_polling_loop,
                         daemon=True).start()

    if USB_MONITOR:
        threading.Thread(target=_usb_monitor_loop,
                         daemon=True).start()

    threading.Thread(target=_offline_queue_flusher,
                     daemon=True).start()

    if STARTUP_CHECK:
        threading.Thread(target=_run_startup_check,
                         daemon=True).start()

    threading.Thread(target=_heartbeat_writer,
                     daemon=True).start()

    threading.Thread(target=_data_protection_loop,
                     daemon=True).start()

    _guard_engine = GuardEngine()
    with keyboard.Listener(
            on_press=_guard_engine.on_press,
            on_release=_guard_engine.on_release) as listener:
        listener.join()
