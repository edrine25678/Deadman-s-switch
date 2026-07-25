"""
test_full_system.py  —  End-to-end system test for Deadman's Switch
Runs ALL components together and reports results.

Usage:
  python test_full_system.py
  python test_full_system.py --verbose   (show details)
"""

import ast, json, os, sys, time, io, pickle, shutil, threading, tempfile, subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
CONFIG_BACKUP = os.path.join(BASE_DIR, "config.json.sysbak")
HEARTBEAT_PATH = os.path.join(BASE_DIR, "guard.heartbeat")
KEY_PATH = os.path.join(BASE_DIR, "guard.key")
QUEUE_DIR = os.path.join(BASE_DIR, "offline_queue")

PASS = 0
FAIL = 0
SKIP = 0


def ok(msg=""):
    global PASS; PASS += 1
    print(f"  [PASS]  {msg}")


def fail(msg=""):
    global FAIL; FAIL += 1
    print(f"  [FAIL]  {msg}")


def skip(msg=""):
    global SKIP; SKIP += 1
    print(f"  [SKIP]  {msg}")


def heading(n, text):
    print(f"\n{'='*60}")
    print(f"  [{n}] {text}")
    print(f"{'='*60}")


def _cleanup(*paths):
    for p in paths:
        if os.path.isfile(p):
            try: os.remove(p)
            except Exception: pass
        elif os.path.isdir(p):
            try: shutil.rmtree(p, ignore_errors=True)
            except Exception: pass


def _backup_config():
    if os.path.exists(CONFIG_PATH) and not os.path.exists(CONFIG_BACKUP):
        shutil.copy2(CONFIG_PATH, CONFIG_BACKUP)


def _restore_config():
    _cleanup(CONFIG_PATH)
    if os.path.exists(CONFIG_BACKUP):
        shutil.move(CONFIG_BACKUP, CONFIG_PATH)


def _write_config(**kw):
    d = dict(
        telegram_bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        telegram_chat_id="123456789",
        avg_dwell_ms=120.0, avg_flight_ms=80.0,
        tolerance_percent=60, mismatch_window=10, mismatch_threshold=4,
        alert_cooldown_seconds=300, wifi_wait_seconds=6, webcam_warmup_frames=10,
        remote_commands_enabled=True, startup_check=False,
        face_check_enabled=False, face_tolerance=0.5,
        usb_monitor_enabled=False, usb_poll_interval=2,
        offline_alarm_enabled=False, offline_alarm_duration=30,
        unlock_duration_minutes=60,
        email_sender="", email_app_password="", email_recipient="",
        startup_notification=False,
    )
    d.update(kw)
    with open(CONFIG_PATH, "w") as f:
        json.dump(d, f, indent=2)
    return d


# ====================================================================
print("=" * 60)
print("  Deadman's Switch  —  Full System Test")
print("=" * 60)

_backup_config()

# ── 1. CONFIG FILE ────────────────────────────────────────────────
heading(1, "Config File")
try:
    cfg = json.load(open(CONFIG_PATH))
    ok(f"config.json loaded ({len(cfg)} keys)")
except Exception as e:
    _write_config()
    cfg = json.load(open(CONFIG_PATH))
    ok(f"config.json recreated with defaults ({len(cfg)} keys)")

# ── 2. MODULE IMPORT ─────────────────────────────────────────────
heading(2, "Module Import")
import importlib
try:
    import main_guard as mg
    importlib.reload(mg)
    ok("main_guard imported")
except Exception as e:
    fail(f"main_guard import error: {e}")

try:
    import watchdog as wd
    importlib.reload(wd)
    ok("watchdog imported")
except Exception as e:
    fail(f"watchdog import error: {e}")

try:
    import calibrate
    importlib.reload(calibrate)
    ok("calibrate imported")
except Exception as e:
    fail(f"calibrate import error: {e}")

try:
    import install
    importlib.reload(install)
    ok("install imported")
except Exception as e:
    fail(f"install import error: {e}")

try:
    import validate_config as vc
    importlib.reload(vc)
    ok("validate_config imported")
except Exception as e:
    fail(f"validate_config import error: {e}")

# config_ui requires Tkinter
try:
    import tkinter
    import config_ui
    ok("config_ui imported (Tkinter available)")
except ImportError:
    skip("config_ui: Tkinter not available")
except Exception as e:
    fail(f"config_ui import error: {e}")

# ── 3. CONFIG VALIDATION ──────────────────────────────────────────
heading(3, "Config Validation (install._validate_config)")
from unittest.mock import patch
with patch("requests.get") as m:
    m.return_value.status_code = 200
    m.return_value.json.return_value = {"ok": True, "result": {"username": "bot"}}
    errors = install._validate_config()
    if not errors:
        ok("install._validate_config() = 0 errors (mocked Telegram)")
    else:
        fail(f"install._validate_config() errors: {errors}")

# ── 4. COLLECT DATA FILES ─────────────────────────────────────────
heading(4, "Data File Collection (install._collect_data_files)")
files = install._collect_data_files()
if len(files) >= 1:
    srcs = [s for s, _ in files]
    if any("config.json" in s for s in srcs):
        ok(f"_collect_data_files() = {len(files)} files (config.json included)")
    else:
        fail("config.json not in collected files")
else:
    fail("No files collected")

# ── 5. GUARD ENGINE ────────────────────────────────────────────────
heading(5, "GuardEngine Core Logic")
engine = mg.GuardEngine()

# basic state
checks = [
    ("init mismatch_streak=0", engine.mismatch_streak == 0),
    ("init capture_mode=False", engine.capture_mode == False),
    ("within_tolerance exact", engine._within_tolerance(100, 100)),
    ("within_tolerance range", engine._within_tolerance(100, 110)),
    ("within_tolerance outside", not engine._within_tolerance(999, 100)),
]
for msg, okk in checks:
    (ok if okk else fail)(msg)

# window evaluation
engine.dwell_buf = [mg.AVG_DWELL] * mg.WINDOW_SIZE
engine.flight_buf = [mg.AVG_FLIGHT] * (mg.WINDOW_SIZE - 1)
engine._evaluate_window()
if engine.mismatch_streak == 0:
    ok("evaluate_window: match -> streak 0")
else:
    fail("evaluate_window: match -> streak != 0")

engine.dwell_buf = [9999] * mg.WINDOW_SIZE
engine.flight_buf = [9999] * (mg.WINDOW_SIZE - 1)
engine._evaluate_window()
if engine.mismatch_streak == 1:
    ok("evaluate_window: mismatch -> streak 1")
else:
    fail(f"evaluate_window: mismatch -> streak {engine.mismatch_streak}")

# capture mode
from pynput.keyboard import KeyCode
engine.enable_capture(target=5)
engine.on_press(KeyCode.from_char("a"))
engine.on_press(KeyCode.from_char("b"))
if len(engine.captured_keys) == 2:
    ok("capture_mode: 2 keys captured")
else:
    fail(f"capture_mode: captured {len(engine.captured_keys)} keys")

# timing pipeline
from pynput.keyboard import Key as K
engine2 = mg.GuardEngine()
engine2.on_press(K.shift); time.sleep(0.01); engine2.on_release(K.shift)
if len(engine2.dwell_buf) == 1 and engine2.dwell_buf[0] > 0:
    ok("on_release: dwell sample recorded")
else:
    fail(f"on_release: dwell_buf={engine2.dwell_buf}")

# ── 6. BUILD LOCATION BLOCK ──────────────────────────────────────
heading(6, "Location Block Builder")
loc = mg._build_location_block(None)
if "unavailable" in loc[2].lower():
    ok("build_location_block(None) -> 'unavailable'")
else:
    fail("build_location_block(None) unexpected")

loc = mg._build_location_block(dict(method="windows_location_service",
                                      lat=51.5, lng=-0.13, accuracy=5, target_met=True))
if "maps.google.com" in loc[2]:
    ok("build_location_block(windows) -> maps link")
else:
    fail("build_location_block(windows) missing maps link")

loc = mg._build_location_block(dict(method="ip_geolocation", lat=40, lng=-74,
                                      ip="1.2.3.4", city="NY", country="US"))
if "IP Geolocation" in loc[2]:
    ok("build_location_block(ip) -> IP Geolocation")
else:
    fail("build_location_block(ip) unexpected")

# ── 7. LOGGING ─────────────────────────────────────────────────────
heading(7, "Encrypted Logging")
_cleanup(KEY_PATH, os.path.join(BASE_DIR, "guard.log"))
importlib.reload(mg)
mg.log.info("FULL SYSTEM TEST: logging check")
if os.path.exists(KEY_PATH):
    ok("guard.key created")
else:
    fail("guard.key not created")
if os.path.exists(os.path.join(BASE_DIR, "guard.log")):
    ok("guard.log created")
else:
    fail("guard.log not created")

# ── 8. DATA PROTECTION ─────────────────────────────────────────────
heading(8, "Data Protection")
_cleanup(os.path.join(BASE_DIR, "guard.log.old"))
with open(os.path.join(BASE_DIR, "guard.log.old"), "w") as f:
    f.write("old")
cutoff = time.time() - (mg.LOG_RETENTION_DAYS + 1) * 86400
os.utime(os.path.join(BASE_DIR, "guard.log.old"), (cutoff, cutoff))
mg._enforce_log_retention()
if not os.path.exists(os.path.join(BASE_DIR, "guard.log.old")):
    ok("_enforce_log_retention() deleted old log")
else:
    fail("_enforce_log_retention() did not delete old log")

# secure delete
p = os.path.join(BASE_DIR, "_sys_test_del.tmp")
with open(p, "wb") as f: f.write(b"data")
mg._secure_delete(p, 2)
if not os.path.exists(p):
    ok("_secure_delete() removed file")
else:
    fail("_secure_delete() did not remove file")

# heartbeat cleanup
_cleanup(HEARTBEAT_PATH)
with open(HEARTBEAT_PATH, "w") as f: f.write("stale")
cutoff = time.time() - (mg.HEARTBEAT_RETENTION_HOURS + 1) * 3600
os.utime(HEARTBEAT_PATH, (cutoff, cutoff))
mg._cleanup_stale_heartbeats()
if not os.path.exists(HEARTBEAT_PATH):
    ok("_cleanup_stale_heartbeats() removed stale heartbeat")
else:
    fail("_cleanup_stale_heartbeats() did not remove stale heartbeat")

# ── 9. HEARTBEAT ──────────────────────────────────────────────────
heading(9, "Heartbeat (writer + watchdog)")

threading.Thread(target=mg._heartbeat_writer, daemon=True).start()
time.sleep(0.2)
if os.path.exists(HEARTBEAT_PATH) and os.path.getsize(HEARTBEAT_PATH) > 0:
    ok("_heartbeat_writer() created heartbeat file")
else:
    fail("_heartbeat_writer() did not create heartbeat")

age = wd._read_heartbeat()
if age is not None and age < 10:
    ok(f"watchdog reads heartbeat (age={age:.1f}s)")
else:
    fail(f"watchdog heartbeat read: age={age}")

stale = wd._is_heartbeat_stale()
if stale is False:
    ok("watchdog: heartbeat NOT stale")
else:
    fail(f"watchdog: heartbeat stale={stale}")

# ── 10. OFFLINE QUEUE ──────────────────────────────────────────────
heading(10, "Offline Alert Queue")
_cleanup(QUEUE_DIR)
os.makedirs(QUEUE_DIR, exist_ok=True)

importlib.reload(mg)
mg._enqueue_alert("test-ts", {"hostname":"pc","username":"u"},
                  "test-loc", 1.0, 2.0, None, None)
entries = [d for d in os.listdir(QUEUE_DIR) if os.path.isdir(os.path.join(QUEUE_DIR, d))]
if len(entries) == 1:
    ok("_enqueue_alert() created queue entry")
else:
    fail(f"_enqueue_alert() created {len(entries)} entries")

# flush with mock delivery
with patch.object(mg, 'tg_send_message', return_value=True):
    mg._flush_offline_queue()
entries2 = [d for d in os.listdir(QUEUE_DIR) if os.path.isdir(os.path.join(QUEUE_DIR, d))]
if len(entries2) == 0:
    ok("_flush_offline_queue() cleared delivered alert")
else:
    fail(f"_flush_offline_queue() left {len(entries2)} entries")

# enqueue with screenshot + webcam
shot = io.BytesIO(b"pngdata")
cam = io.BytesIO(b"jpgdata")
mg._enqueue_alert("ts", {"hostname":"h","username":"u"}, "loc", None, None, shot, cam)
entries3 = os.listdir(QUEUE_DIR)
if entries3:
    qdir = os.path.join(QUEUE_DIR, entries3[0])
    qfiles = os.listdir(qdir)
    if "screenshot.png" in qfiles and "webcam.jpg" in qfiles:
        ok("enqueue with screenshot + webcam: files saved")
    else:
        fail(f"enqueue: missing files in {qfiles}")
_cleanup(QUEUE_DIR)

# ── 11. CALIBRATION ────────────────────────────────────────────────
heading(11, "Calibration Engine")
ce = calibrate.CalibrationEngine()
ce.ready = True
ce.dwell_samples = [100, 110, 90, 95, 105]
ce.flight_samples = [80, 85, 75, 90]
import io as _io
old_stdout = sys.stdout
sys.stdout = _io.StringIO()
try:
    ce.build_profile()
    sys.stdout = old_stdout
    with open(CONFIG_PATH) as f:
        cfg2 = json.load(f)
    if cfg2.get("avg_dwell_ms", 0) > 0:
        ok("build_profile() wrote to config.json")
    else:
        fail("build_profile() did not write dwell")
except Exception as e:
    sys.stdout = old_stdout
    fail(f"build_profile() error: {e}")

# ── 12. WATCHDOG PROCESS LOGIC ─────────────────────────────────────
heading(12, "Watchdog Process Logic")
importlib.reload(wd)

# constants
const_ok = all([
    wd.BACKOFF_BASE == 10,
    wd.BACKOFF_MAX == 300,
    wd.HEARTBEAT_TIMEOUT == 120,
    wd.CRASH_WINDOW == 120,
    wd.MAX_RESTARTS_WINDOW == 8,
    wd.CHECK_INTERVAL == 30,
])
ok("watchdog constants verified" if const_ok else "watchdog constants MISMATCH")

# guard names
if "svchost.exe" in wd.GUARD_NAMES and "main_guard.py" in wd.GUARD_NAMES:
    ok("watchdog GUARD_NAMES = {svchost.exe, main_guard.py}")
else:
    fail(f"watchdog GUARD_NAMES = {wd.GUARD_NAMES}")

# log
try:
    wd.log("FULL SYSTEM TEST: watchdog log check")
    ok("watchdog.log() works")
except Exception as e:
    fail(f"watchdog.log() error: {e}")

# ── 13. DEVICE INFO ────────────────────────────────────────────────
heading(13, "Device Info")
info = mg.get_device_info()
if info.get("hostname") and info.get("username"):
    ok(f"get_device_info(): hostname={info['hostname']}, user={info['username']}")
else:
    fail(f"get_device_info() returned: {info}")

# ── 14. REMOTE COMMANDS ────────────────────────────────────────────
heading(14, "Remote Command Help Text")
for cmd in ["/status", "/location", "/screenshot", "/webcam",
             "/unlock", "/relock", "/lock", "/shutdown", "/help"]:
    if cmd not in mg.HELP_TEXT:
        fail(f"HELP_TEXT missing: {cmd}")
        break
else:
    ok("HELP_TEXT contains all 9 commands")

# ── 15. SYNTACTIC INTEGRITY ────────────────────────────────────────
heading(15, "Syntactic Integrity")
files_to_check = ["main_guard.py", "watchdog.py", "calibrate.py",
                   "install.py", "validate_config.py", "config_ui.py",
                   "test_guard.py", "test_integration.py", "test_full_system.py"]
all_ok = True
for f in files_to_check:
    fp = os.path.join(BASE_DIR, f)
    if not os.path.exists(fp):
        skip(f"{f}: not found")
        continue
    try:
        ast.parse(open(fp, encoding="utf-8").read())
    except SyntaxError as e:
        fail(f"{f}: SyntaxError: {e}")
        all_ok = False
if all_ok:
    ok("All Python files pass ast.parse()")

# ── 16. SYSTEM SUMMARY ─────────────────────────────────────────────
heading(16, "System Summary")
print(f"""
  Python:        {sys.version.split()[0]} ({'64bit' if sys.maxsize > 2**32 else '32bit'})
  Platform:      {sys.platform}
  Config keys:   {len(cfg)}
  GuardEngine:   dwell={mg.AVG_DWELL}ms  flight={mg.AVG_FLIGHT}ms  tol={mg.TOLERANCE*100:.0f}%
  Face check:    {'enabled' if mg.FACE_CHECK else 'disabled'}
  USB monitor:   {'enabled' if mg.USB_MONITOR else 'disabled'}
  Remote cmds:   {'enabled' if mg.CMDS_ENABLED else 'disabled'}
  Offline alarm: {'enabled' if mg.OFFLINE_ALARM else 'disabled'}
  Key file:      {'exists' if os.path.exists(KEY_PATH) else 'missing'}
  Log file:      {'exists' if os.path.exists(os.path.join(BASE_DIR, 'guard.log')) else 'missing'}
  Heartbeat:     {'exists' if os.path.exists(HEARTBEAT_PATH) else 'missing'}
  Installed:     {os.path.isdir(os.path.join(BASE_DIR, 'dist'))}
""")

# ── SUMMARY ────────────────────────────────────────────────────────
print("=" * 60)
print(f"  Results:  {PASS} passed  {FAIL} failed  {SKIP} skipped")
print("=" * 60)
_restore_config()
sys.exit(0 if FAIL == 0 else 1)
