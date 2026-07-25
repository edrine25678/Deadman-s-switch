"""
watchdog.py  —  Deadman's Switch watchdog
Monitors the guard (svchost.exe / main_guard.py) via process listing
and a heartbeat file. If the process is missing or the heartbeat is
stale, restarts it with exponential backoff.

Runs as a separate startup entry so both must be killed to stop the system.
"""

import ctypes, os, subprocess, sys, time
from datetime import datetime

if sys.platform == "win32":
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 0)

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

EXE_PATH = os.path.join(BASE_DIR, "dist", "svchost.exe")
PY_PATH  = os.path.join(BASE_DIR, "main_guard.py")

CHECK_INTERVAL = 30

GUARD_NAMES = {"svchost.exe", "main_guard.py"}

HEARTBEAT_FILE = os.path.join(BASE_DIR, "guard.heartbeat")
HEARTBEAT_TIMEOUT = 120          # seconds — restart if heartbeat older than this

# Exponential backoff
BACKOFF_BASE      = 10           # initial wait (seconds)
BACKOFF_MAX       = 300          # never wait longer than this (5 min)
BACKOFF_MULTIPLIER = 2

# Crash-loop detection
CRASH_WINDOW      = 120          # track restarts within this window (seconds)
MAX_RESTARTS_WINDOW = 8          # if exceeded, give up

_PID = os.getpid()

_restart_history = []            # timestamps of recent restarts (for crash-loop detection)
_backoff_current = BACKOFF_BASE  # current backoff delay


def log(msg):
    try:
        p = os.path.join(BASE_DIR, "watchdog.log")
        with open(p, "a") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} [WD:{_PID}] {msg}\n")
    except Exception:
        try:
            sys.stderr.write(f"[WD:{_PID}] {msg}\n")
        except Exception:
            pass


def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True,
                          creationflags=subprocess.CREATE_NO_WINDOW)


def _get_guard_pids():
    """Return PIDs of running guard processes."""
    pids = []
    try:
        out = _run(["tasklist", "/FO", "CSV", "/NH"]).stdout
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.strip('"').split('","')
            if len(parts) >= 2:
                name = parts[0].lower()
                pid = parts[1]
                if name in GUARD_NAMES:
                    pids.append(pid)
    except Exception as exc:
        log(f"get_guard_pids error: {exc}")
    return pids


def _read_heartbeat():
    """Return age in seconds of the heartbeat file, or None if unavailable."""
    try:
        if not os.path.exists(HEARTBEAT_FILE):
            return None
        mtime = os.path.getmtime(HEARTBEAT_FILE)
        return time.time() - mtime
    except Exception:
        return None


def _is_heartbeat_stale():
    age = _read_heartbeat()
    if age is None:
        return None        # unknown — can't decide
    stale = age > HEARTBEAT_TIMEOUT
    if stale:
        log(f"heartbeat stale ({age:.0f}s > {HEARTBEAT_TIMEOUT}s)")
    return stale


def is_guard_healthy():
    """
    Return True if the guard is running AND its heartbeat is fresh.
    Return False if missing or hung.
    """
    running = False
    try:
        out = _run(["tasklist"]).stdout.lower()
        running = any(n in out for n in GUARD_NAMES)
    except Exception as exc:
        log(f"tasklist error: {exc}")
        return True    # be conservative — assume alive

    if not running:
        return False

    pids = _get_guard_pids() if running else []
    if pids:
        log(f"guard running (PIDs: {', '.join(pids)})")

    heartbeat_stale = _is_heartbeat_stale()
    if heartbeat_stale is True:
        log("heartbeat stale even though process exists — guard may be hung")
        return False

    return True


def start_guard():
    global _restart_history, _backoff_current
    now = time.time()

    # Record this restart attempt
    _restart_history.append(now)
    # Prune history outside the crash window
    cutoff = now - CRASH_WINDOW
    _restart_history = [t for t in _restart_history if t >= cutoff]

    attempt_number = len(_restart_history)

    if attempt_number >= MAX_RESTARTS_WINDOW:
        log(f"CRITICAL: {attempt_number} restarts in {CRASH_WINDOW}s - crash-loop detected, giving up")
        sys.exit(1)

    try:
        if os.path.exists(EXE_PATH):
            proc = subprocess.Popen([EXE_PATH], creationflags=subprocess.CREATE_NO_WINDOW)
            log(f"started EXE {EXE_PATH} (PID: {proc.pid}) attempt #{attempt_number}")
        else:
            pw = sys.executable.replace("python.exe", "pythonw.exe")
            if not os.path.exists(pw):
                pw = sys.executable
            proc = subprocess.Popen([pw, PY_PATH], creationflags=subprocess.CREATE_NO_WINDOW)
            log(f"started script {pw} {PY_PATH} (PID: {proc.pid}) attempt #{attempt_number}")
        _backoff_current = BACKOFF_BASE  # reset backoff on success
    except Exception as exc:
        log(f"start_guard error (attempt #{attempt_number}): {exc}")
        _backoff_current = min(_backoff_current * BACKOFF_MULTIPLIER, BACKOFF_MAX)
        log(f"backoff now {_backoff_current}s")
        if attempt_number >= 5:
            log(f"CRITICAL: {attempt_number} consecutive start failures - giving up")
            sys.exit(1)


if __name__ == "__main__":
    log(f"watchdog started (PID={_PID}, base={BASE_DIR})")
    log(f"  CHECK_INTERVAL={CHECK_INTERVAL}s  HEARTBEAT_TIMEOUT={HEARTBEAT_TIMEOUT}s")
    log(f"  guard EXE={EXE_PATH if os.path.exists(EXE_PATH) else 'N/A'}")
    log(f"  guard PY={PY_PATH if os.path.exists(PY_PATH) else 'N/A'}")

    while True:
        time.sleep(CHECK_INTERVAL)
        if not is_guard_healthy():
            log(f"guard unhealthy - restarting (backoff={_backoff_current}s)")
            start_guard()
            time.sleep(_backoff_current)
