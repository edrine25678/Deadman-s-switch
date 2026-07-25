"""
validate_config.py  —  Pre-deployment configuration validator
Run BEFORE install.py to check everything is set up correctly.

Usage:
  python validate_config.py
  python validate_config.py --verbose   (show full details)
"""

import json, os, sys, time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
REFERENCE_FACE_PATH = os.path.join(BASE_DIR, "reference_face.pkl")
GUARD_LOG_PATH = os.path.join(BASE_DIR, "guard.log")
GUARD_KEY_PATH = os.path.join(BASE_DIR, "guard.key")
OFFLINE_QUEUE_DIR = os.path.join(BASE_DIR, "offline_queue")
DIST_DIR = os.path.join(BASE_DIR, "dist")

PASS = "[PASS]"
FAIL = "[FAIL]"

_tests_run = 0
_tests_passed = 0
_tests_failed = 0
_tests_warned = 0


def heading(text):
    print()
    print("=" * 60)
    print(f"  {text}")
    print("=" * 60)


def test(name):
    global _tests_run
    _tests_run += 1
    return name


def passed(msg=""):
    global _tests_passed
    _tests_passed += 1
    print(f"  {PASS}  PASS  {msg}" if msg else f"  {PASS}  PASS")


def failed(msg=""):
    global _tests_failed
    _tests_failed += 1
    print(f"  {FAIL}  {msg}" if msg else f"  {FAIL}")


def warn(msg=""):
    global _tests_warned
    _tests_warned += 1
    print(f"  [WARN]  {msg}" if msg else f"  [WARN]")


def check(condition, name, detail=""):
    test(name)
    if condition:
        passed(detail)
    else:
        failed(detail)
    return condition


def verify_path(path, name):
    exists = os.path.exists(path)
    return check(exists, f"{name} exists",
                 f"{'found' if exists else 'missing'}: {path}")


def main():
    global _tests_run, _tests_passed, _tests_failed, _tests_warned
    _tests_run = 0; _tests_passed = 0; _tests_failed = 0; _tests_warned = 0

    verbose = "--verbose" in sys.argv

    print()
    print("  Deadman's Switch  —  Configuration Validator")
    print("  " + "-" * 45)

    # ── 1. Config file ──────────────────────────────────────────────
    heading("1. Config File")

    if not verify_path(CONFIG_PATH, "config.json"):
        failed("Cannot continue without config.json")
        _print_summary()
        sys.exit(1)

    with open(CONFIG_PATH, "r") as fh:
        cfg = json.load(fh)

    # ── 2. Required config values ────────────────────────────────────
    heading("2. Required Config Values")

    required_keys = [
        "telegram_bot_token",
        "telegram_chat_id",
        "avg_dwell_ms",
        "avg_flight_ms",
    ]
    for key in required_keys:
        check(key in cfg, f"config key '{key}' exists",
              f"{'present' if key in cfg else 'missing'}")

    check(cfg.get("telegram_bot_token") is not None
          and not str(cfg["telegram_bot_token"]).startswith("YOUR")
          and len(str(cfg["telegram_bot_token"])) > 20,
          "telegram_bot_token looks valid",
          f"length={len(str(cfg.get('telegram_bot_token','')))}")

    chat_id = str(cfg.get("telegram_chat_id", ""))
    check(bool(chat_id) and not chat_id.startswith("YOUR"),
          "telegram_chat_id is set",
          f"chat_id={'set' if chat_id and not chat_id.startswith('YOUR') else 'missing/placeholder'}")

    # ── 3. Numeric range validation ──────────────────────────────────
    heading("3. Numeric Config Values")

    numeric_checks = [
        ("avg_dwell_ms", float, 10, 10000),
        ("avg_flight_ms", float, 5, 5000),
        ("tolerance_percent", (int, float), 1, 200),
        ("mismatch_window", int, 1, 1000),
        ("mismatch_threshold", int, 1, 1000),
        ("alert_cooldown_seconds", int, 0, 86400),
        ("wifi_wait_seconds", int, 0, 300),
        ("webcam_warmup_frames", int, 0, 100),
        ("face_tolerance", (int, float), 0.0, 2.0),
        ("usb_poll_interval", int, 1, 3600),
        ("offline_alarm_duration", int, 1, 3600),
        ("unlock_duration_minutes", int, 1, 525600),
    ]
    for name, expected_type, lo, hi in numeric_checks:
        val = cfg.get(name)
        present = val is not None
        check(present, f"'{name}' is set",
              f"value={'set' if present else 'default (None)'}")
        if present:
            type_ok = isinstance(val, expected_type) if isinstance(expected_type, type) else isinstance(val, expected_type)
            if not type_ok:
                warn(f"'{name}' type={type(val).__name__}, expected {expected_type.__name__}")
            else:
                in_range = lo <= val <= hi
                check(in_range, f"'{name}' in range [{lo}, {hi}]",
                      f"value={val}" if in_range else f"value={val} outside [{lo}, {hi}]")

    # ── 4. Boolean config values ─────────────────────────────────────
    heading("4. Boolean Config Values")

    bool_keys = [
        "remote_commands_enabled",
        "startup_check",
        "face_check_enabled",
        "usb_monitor_enabled",
        "offline_alarm_enabled",
    ]
    for key in bool_keys:
        val = cfg.get(key)
        present = val is not None
        if present:
            check(isinstance(val, bool), f"'{key}' is boolean",
                  f"type={type(val).__name__}, value={val}")
        else:
            warn(f"'{key}' not set, will use default (true)")

    # ── 5. Telegram token ────────────────────────────────────────────
    heading("5. Telegram Token")

    token = str(cfg.get("telegram_bot_token", ""))
    if not token or token.startswith("YOUR"):
        failed("Telegram token is placeholder - skipping API test")
    else:
        try:
            import requests
            r = requests.get(
                f"https://api.telegram.org/bot{token}/getMe",
                timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get("ok"):
                    bot_name = data["result"].get("username", "unknown")
                    passed(f"Token valid — bot: @{bot_name}")
                else:
                    failed(f"API error: {data.get('description', 'unknown')}")
            else:
                failed(f"HTTP {r.status_code}")
        except requests.exceptions.ConnectionError:
            failed("Network unreachable — cannot validate Telegram token")
        except Exception as exc:
            failed(f"Exception: {exc}")

    # ── 6. Email authentication ──────────────────────────────────────
    heading("6. Email Authentication")

    email_sender = cfg.get("email_sender", "")
    email_password = cfg.get("email_app_password", "")
    email_recipient = cfg.get("email_recipient", "")

    if not email_sender or email_sender.startswith("YOUR"):
        warn("Email sender not configured — skipping email test")
    elif not email_password:
        warn("Email app password not set")
    elif not email_recipient:
        warn("Email recipient not set")
    else:
        try:
            import smtplib
            server = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10)
            server.login(email_sender, email_password)
            server.quit()
            passed(f"SMTP login successful — {email_sender}")
        except smtplib.SMTPAuthenticationError:
            failed("SMTP auth failed — use a Gmail App Password (not your regular password)")
        except Exception as exc:
            failed(f"SMTP error: {exc}")

    # ── 7. Calibration data ──────────────────────────────────────────
    heading("7. Calibration Data")

    dwell = cfg.get("avg_dwell_ms", 0)
    flight = cfg.get("avg_flight_ms", 0)
    check(dwell > 0, "avg_dwell_ms > 0",
          f"value={dwell}" if dwell > 0 else "value=0 — run calibrate.py")
    check(flight > 0, "avg_flight_ms > 0",
          f"value={flight}" if flight > 0 else "value=0 — run calibrate.py")

    verify_path(REFERENCE_FACE_PATH, "reference_face.pkl")

    if os.path.exists(REFERENCE_FACE_PATH):
        try:
            import pickle
            with open(REFERENCE_FACE_PATH, "rb") as f:
                ref = pickle.load(f)
            if isinstance(ref, list):
                check(len(ref) > 0, "reference_face.pkl contains encodings",
                      f"{len(ref)} face encoding(s)")
            else:
                passed("reference_face.pkl loaded (single encoding)")
        except Exception as exc:
            failed(f"reference_face.pkl corrupt: {exc}")

    # ── 8. Webcam accessibility ──────────────────────────────────────
    heading("8. Webcam Accessibility")

    try:
        import cv2
        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            for _ in range(5):
                cap.read()
            ret, frame = cap.read()
            cap.release()
            if ret and frame is not None and frame.size > 0:
                passed(f"Webcam opened and captured frame ({frame.shape[1]}x{frame.shape[0]})")
            else:
                failed("Webcam opened but failed to capture frame")
        else:
            failed("No webcam detected (VideoCapture(0) failed)")
    except ImportError:
        warn("OpenCV (cv2) not installed — cannot test webcam")
    except Exception as exc:
        failed(f"Webcam error: {exc}")

    # ── 9. Face recognition dependencies ────────────────────────────
    heading("9. Face Recognition Dependencies")

    try:
        import face_recognition
        passed("face_recognition module importable")
    except ImportError as exc:
        failed(f"face_recognition import failed: {exc}")

    try:
        import face_recognition_models
        models_dir = os.path.join(os.path.dirname(face_recognition_models.__file__), "models")
        if os.path.isdir(models_dir):
            dat_files = [f for f in os.listdir(models_dir) if f.endswith(".dat")]
            check(len(dat_files) == 4, f"face_recognition_models has {len(dat_files)} model files",
                  f"{dat_files}" if verbose else f"{len(dat_files)} .dat files")
        else:
            warn("face_recognition_models/models/ directory not found")
    except ImportError as exc:
        failed(f"face_recognition_models import failed: {exc}")

    try:
        import dlib
        passed("dlib module importable")
    except ImportError as exc:
        failed(f"dlib import failed: {exc}")

    # ── 10. File system ──────────────────────────────────────────────
    heading("10. File System & Runtime Files")

    verify_path(GUARD_KEY_PATH, "guard.key")
    writable = os.access(BASE_DIR, os.W_OK)
    check(writable, f"BASE_DIR writable ({BASE_DIR})",
          "writable" if writable else "not writable")

    dist_ok = os.path.isdir(DIST_DIR)
    if dist_ok:
        dist_exes = [f for f in os.listdir(DIST_DIR) if f.endswith(".exe")]
        check(len(dist_exes) > 0, f"dist/ has compiled EXEs",
              f"{len(dist_exes)} EXE(s): {', '.join(dist_exes)}" if dist_exes else "no EXEs found")
    else:
        warn("dist/ directory not found — run install.py first")

    # ── 11. Python & dependency versions ─────────────────────────────
    heading("11. Python Environment")

    check(sys.version_info >= (3, 8), f"Python version >= 3.8",
          f"{sys.version}")

    required_packages = [
        "requests", "cryptography", "pynput", "PIL",
        "cv2", "numpy", "pyautogui",
    ]
    for pkg in required_packages:
        try:
            __import__(pkg.replace("cv2", "cv2"))
            if verbose:
                passed(f"{pkg} available")
        except ImportError:
            failed(f"{pkg} not installed — run: pip install {pkg}")

    # ── Summary ──────────────────────────────────────────────────────
    _print_summary()
    return 0 if _tests_failed == 0 else 1


def _print_summary():
    total = _tests_passed + _tests_failed
    print()
    print("=" * 60)
    print(f"  Results:  {_tests_passed} passed"
          f"  {_tests_failed} failed"
          f"  {_tests_warned} warnings"
          f"  ({total} checks)")
    print("=" * 60)
    if _tests_failed:
        print("  Some checks FAILED — review above before deploying.")
    else:
        print("  All checks PASSED — ready to deploy.")
    print()


if __name__ == "__main__":
    sys.exit(main())
