"""
install.py  ???  Deadman's Switch installer
Registers BOTH guard and watchdog in Windows startup with innocuous names.
Run as Administrator.

Usage:
  python install.py            install
  python install.py --remove   uninstall
"""

import sys, os, winreg, subprocess, json, requests, smtplib, shutil

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
CONFIG        = os.path.join(BASE_DIR, "config.json")
GUARD_PY      = os.path.join(BASE_DIR, "main_guard.py")
WATCHDOG_PY   = os.path.join(BASE_DIR, "watchdog.py")

GUARD_EXE_NAME     = "svchost.exe"
WATCHDOG_EXE_NAME  = "sihost.exe"
GUARD_REG_NAME     = "WindowsUpdateSvc"
WATCHDOG_REG_NAME  = "ShellInfraSvc"

REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

HIDDEN_IMPORTS = [
    "face_recognition", "face_recognition_models", "dlib", "PIL",
    "scipy.special", "scipy.spatial",
    "cryptography", "pynput.keyboard._win32", "pynput.mouse._win32",
    "sklearn", "numpy", "requests", "cv2", "winsound",
]


def _validate_config():
    with open(CONFIG) as fh:
        cfg = json.load(fh)
    errors = []
    warnings = []

    # Required fields
    required_fields = ["telegram_bot_token", "telegram_chat_id", "avg_dwell_ms", "avg_flight_ms"]
    for key in required_fields:
        if key not in cfg:
            errors.append(f"Missing required config key: '{key}'")

    token = cfg.get("telegram_bot_token", "")
    if not token or token.startswith("YOUR"):
        errors.append("telegram_bot_token is missing or still set to placeholder (YOUR_)")
    elif len(token) < 20:
        errors.append(f"telegram_bot_token seems too short ({len(token)} chars)")

    chat_id = str(cfg.get("telegram_chat_id", ""))
    if not chat_id or chat_id.startswith("YOUR"):
        errors.append("telegram_chat_id is missing or still set to placeholder (YOUR_)")

    # Numeric range validation
    numeric_fields = [
        ("avg_dwell_ms", float, 10, 10000),
        ("avg_flight_ms", float, 5, 5000),
        ("tolerance_percent", float, 1, 200),
        ("mismatch_window", int, 1, 1000),
        ("mismatch_threshold", int, 1, 1000),
        ("alert_cooldown_seconds", int, 0, 86400),
        ("wifi_wait_seconds", int, 0, 300),
        ("webcam_warmup_frames", int, 0, 100),
        ("face_tolerance", float, 0.0, 2.0),
        ("usb_poll_interval", int, 1, 3600),
        ("offline_alarm_duration", int, 1, 3600),
        ("unlock_duration_minutes", int, 1, 525600),
    ]
    for name, _, lo, hi in numeric_fields:
        val = cfg.get(name)
        if val is None:
            warnings.append(f"'{name}' not set, will use default")
        elif not isinstance(val, (int, float)):
            warnings.append(f"'{name}' should be numeric, got {type(val).__name__} ({val})")

    if not errors:
        try:
            if not token.startswith("YOUR"):
                response = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5)
                if response.status_code != 200:
                    data = response.json()
                    if not data.get("ok"):
                        errors.append(f"Invalid Telegram token: {data.get('description', 'Unknown error')}")
        except requests.exceptions.ConnectionError:
            errors.append("Could not validate Telegram token - no network connection")
        except Exception as e:
            errors.append(f"Could not validate Telegram token: {e}")

        email_sender = cfg.get("email_sender", "")
        email_password = cfg.get("email_app_password", "")
        email_recipient = cfg.get("email_recipient", "")
        if email_sender and email_password and email_recipient and not email_sender.startswith("YOUR"):
            try:
                with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
                    server.login(email_sender, email_password)
                warnings.append("Email credentials validated successfully")
            except smtplib.SMTPAuthenticationError:
                errors.append("Email auth failed - use a Gmail App Password (not regular password)")
            except Exception as e:
                warnings.append(f"Email validation failed (non-fatal): {e}")
        elif email_sender and not email_sender.startswith("YOUR"):
            if not email_password or not email_recipient:
                warnings.append("Email sender set but password or recipient missing - email alerts disabled")

    # File checks
    face_check = cfg.get("face_check_enabled", True)
    ref_face = os.path.join(BASE_DIR, "reference_face.pkl")
    if face_check and not os.path.exists(ref_face):
        warnings.append("face_check_enabled is true but reference_face.pkl not found - run calibrate_face.py")

    return errors


def _collect_data_files():
    """Return list of (src_path, dest_dir) for PyInstaller --add-data."""
    files = [(CONFIG, ".")]
    pkl = os.path.join(BASE_DIR, "reference_face.pkl")
    if os.path.exists(pkl):
        files.append((pkl, "."))
    try:
        import face_recognition_models
        models_dir = os.path.join(os.path.dirname(face_recognition_models.__file__), "models")
        if os.path.exists(models_dir):
            for fname in os.listdir(models_dir):
                if fname.endswith(".dat"):
                    files.append((
                        os.path.join(models_dir, fname),
                        "face_recognition_models\\models"
                    ))
    except ImportError:
        pass
    return files


def _build_exe(script, exe_name):
    print(f"[*] Compiling {os.path.basename(script)} ??? {exe_name} ???")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile", "--noconsole",
        "--name", exe_name.replace(".exe", ""),
        "--distpath", os.path.join(BASE_DIR, "dist"),
        "--workpath", os.path.join(BASE_DIR, "build"),
        "--specpath", BASE_DIR,
    ]
    for imp in HIDDEN_IMPORTS:
        cmd.append(f"--hidden-import={imp}")
    for src, dest in _collect_data_files():
        cmd.append(f"--add-data={src};{dest}")
    cmd.append(script)
    result = subprocess.run(cmd, cwd=BASE_DIR)
    exe = os.path.join(BASE_DIR, "dist", exe_name)
    if result.returncode == 0 and os.path.exists(exe):
        print(f"[+] Built: {exe}")
        return exe
    print(f"[!] PyInstaller failed ??? fallback to .py")
    return None


def _pythonw():
    pw = sys.executable.replace("python.exe", "pythonw.exe")
    return pw if os.path.exists(pw) else sys.executable


def _write_reg(name, cmd):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_SZ, cmd)
    print(f"[+] Startup entry: {name} ??? {cmd}")


def _remove_reg(name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, name)
        print(f"[+] Removed startup entry: {name}")
    except FileNotFoundError:
        pass


def install():
    print("\n==  Deadman's Switch  -  Deploy Installer  ==\n")
    errors = _validate_config()
    if errors:
        print("[!] Fix these first:")
        for e in errors:
            print(f"    * {e}")
        sys.exit(1)

    # Clean previous build artifacts
    for d in [os.path.join(BASE_DIR, "build"), os.path.join(BASE_DIR, "__pycache__")]:
        if os.path.exists(d):
            try:
                shutil.rmtree(d)
            except Exception as exc:
                print(f"[!] Failed to remove {d}: {exc}")
    for f in os.listdir(BASE_DIR):
        if f.endswith(".spec") and f not in ("DeadmansSwitch.spec", "DeadmansSwitchWatchdog.spec"):
            try:
                os.remove(os.path.join(BASE_DIR, f))
            except Exception as exc:
                print(f"[!] Failed to remove {f}: {exc}")

    guard_exe = _build_exe(GUARD_PY, GUARD_EXE_NAME)
    guard_cmd = f'"{guard_exe}"' if guard_exe else f'"{_pythonw()}" "{GUARD_PY}"'

    wd_exe = _build_exe(WATCHDOG_PY, WATCHDOG_EXE_NAME)
    wd_cmd = f'"{wd_exe}"' if wd_exe else f'"{_pythonw()}" "{WATCHDOG_PY}"'

    # Copy runtime files alongside EXEs
    dist_dir = os.path.join(BASE_DIR, "dist")
    for fn in ("config.json", "reference_face.pkl", "guard.key"):
        src = os.path.join(BASE_DIR, fn)
        if os.path.exists(src):
            try:
                shutil.copy2(src, os.path.join(dist_dir, fn))
            except Exception as exc:
                print(f"[!] Failed to copy {fn} to dist: {exc}")

    _write_reg(GUARD_REG_NAME, guard_cmd)
    _write_reg(WATCHDOG_REG_NAME, wd_cmd)

    print(f"""
[+] Deployed successfully.

    Guard:  {guard_cmd}
    Watchdog: {wd_cmd}

    Both start automatically at login.
    Processes appear as "{GUARD_EXE_NAME}" and "{WATCHDOG_EXE_NAME}" in tasklist.
""")


def _reg_exists(name):
    """Check if a registry entry exists."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_READ) as k:
            winreg.QueryValueEx(k, name)
            return True
    except FileNotFoundError:
        return False


def _kill_processes(names, silent=False):
    """Kill all processes matching any of the given names. Return count killed."""
    killed = 0
    for name in names:
        try:
            r = subprocess.run(
                ["taskkill", "/F", "/IM", name],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0:
                lines = [l for l in r.stdout.splitlines() if l.strip()]
                killed += len(lines)
                if not silent:
                    print(f"  [-] Killed {name}")
        except subprocess.TimeoutExpired:
            print(f"  [!] Timeout killing {name}")
        except Exception:
            pass
    return killed


def _remove_path(path, description=""):
    """Remove a file or directory with verification."""
    label = description or path
    if not os.path.exists(path):
        print(f"  [-] {label} — not found")
        return False
    try:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            os.remove(path)
        if not os.path.exists(path):
            print(f"  [-] Removed {label}")
            return True
        print(f"  [!] Failed to remove {label}")
        return False
    except Exception as exc:
        print(f"  [!] Error removing {label}: {exc}")
        return False


def uninstall():
    print("\n" + "=" * 60)
    print("  Deadman's Switch  —  Uninstaller")
    print("=" * 60)
    removed_any = False

    # ── 1. Registry ──────────────────────────────────────────────
    print("\n  [1/5] Removing startup registry entries...")
    for name in (GUARD_REG_NAME, WATCHDOG_REG_NAME):
        _remove_reg(name)
        if _reg_exists(name):
            print(f"  [!] Registry entry still exists: {name}")
        else:
            removed_any = True

    # ── 2. Processes ─────────────────────────────────────────────
    print("\n  [2/5] Killing running processes...")
    names = [GUARD_EXE_NAME, WATCHDOG_EXE_NAME, "csrss.exe"]
    count = _kill_processes(names)

    # ── 3. Compiled executables ──────────────────────────────────
    print("\n  [3/5] Removing compiled executables...")
    dist_dir = os.path.join(BASE_DIR, "dist")
    if os.path.isdir(dist_dir):
        for f in os.listdir(dist_dir):
            if f.endswith(".exe"):
                _remove_path(os.path.join(dist_dir, f), f"dist/{f}")
                removed_any = True
    _remove_path(dist_dir, "dist/ directory")

    # ── 4. Build artifacts ───────────────────────────────────────
    print("\n  [4/5] Cleaning up temporary files...")
    for d in ("build", "__pycache__"):
        _remove_path(os.path.join(BASE_DIR, d), f"{d}/ directory")
    for f in os.listdir(BASE_DIR):
        if f.endswith(".spec") and f not in ("DeadmansSwitch.spec", "DeadmansSwitchWatchdog.spec"):
            _remove_path(os.path.join(BASE_DIR, f), f)

    # ── 5. Runtime data ──────────────────────────────────────────
    print("\n  [5/5] Removing runtime data...")
    for f in ("guard.log", "guard.key", "guard.heartbeat", "watchdog.log"):
        _remove_path(os.path.join(BASE_DIR, f), f)
    _remove_path(os.path.join(BASE_DIR, "offline_queue"), "offline_queue/ directory")

    # ── Summary ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    if removed_any:
        print("  Uninstall complete.")
        print("  Note: config.json, reference_face.pkl, and calibrate.py")
        print("  were kept in case you want to reinstall. Delete them manually.")
    else:
        print("  Nothing to uninstall — the system was not deployed.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    if "--remove" in sys.argv:
        uninstall()
    else:
        install()
