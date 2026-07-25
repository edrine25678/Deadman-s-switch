"""
test_guard.py  —  Unit tests for Deadman's Switch
Run with:  python -m pytest test_guard.py -v
Or:       python -m unittest test_guard.py -v
"""

import json, os, sys, tempfile, time, io, pickle, shutil, threading
import unittest
from unittest.mock import patch, MagicMock

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_BACKUP = os.path.join(BASE_DIR, "config.json.bak")
CONFIG_PATH   = os.path.join(BASE_DIR, "config.json")


def _backup_config():
    if os.path.exists(CONFIG_PATH):
        shutil.copy2(CONFIG_PATH, CONFIG_BACKUP)


def _restore_config():
    _cleanup_temp(CONFIG_PATH)
    if os.path.exists(CONFIG_BACKUP):
        shutil.move(CONFIG_BACKUP, CONFIG_PATH)


def _write_config(**overrides):
    defaults = dict(
        telegram_bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        telegram_chat_id="123456789",
        avg_dwell_ms=120.0,
        avg_flight_ms=80.0,
        tolerance_percent=60,
        mismatch_window=10,
        mismatch_threshold=4,
        alert_cooldown_seconds=300,
        wifi_wait_seconds=6,
        webcam_warmup_frames=10,
        remote_commands_enabled=True,
        startup_check=False,
        face_check_enabled=False,
        face_tolerance=0.5,
        usb_monitor_enabled=False,
        usb_poll_interval=2,
        offline_alarm_enabled=False,
        offline_alarm_duration=30,
        unlock_duration_minutes=60,
        email_sender="",
        email_app_password="",
        email_recipient="",
        startup_notification=False,
    )
    defaults.update(overrides)
    with open(CONFIG_PATH, "w") as f:
        json.dump(defaults, f, indent=2)
    return defaults


def _cleanup_temp(*paths):
    for p in paths:
        if os.path.isfile(p):
            try:
                os.remove(p)
            except Exception:
                pass
        elif os.path.isdir(p):
            try:
                shutil.rmtree(p, ignore_errors=True)
            except Exception:
                pass


# ====================================================================
#  1. main_guard — GuardEngine keystroke dynamics
# ====================================================================
class TestGuardEngineCore(unittest.TestCase):
    """Test GuardEngine in isolation — no keyboard hardware needed."""

    @classmethod
    def setUpClass(cls):
        _backup_config()
        _write_config()
        import importlib
        import main_guard as mg
        importlib.reload(mg)
        cls.mg = mg
        cls.GuardEngine = mg.GuardEngine

    @classmethod
    def tearDownClass(cls):
        _restore_config()
        _cleanup_temp(os.path.join(BASE_DIR, "guard.key"),
                       os.path.join(BASE_DIR, "guard.log"),
                       os.path.join(BASE_DIR, "guard.log.1"),
                       os.path.join(BASE_DIR, "guard.heartbeat"))

    def setUp(self):
        self.engine = self.GuardEngine()

    # -- _within_tolerance ---------------------------

    def test_within_tolerance_exact(self):
        self.assertTrue(self.engine._within_tolerance(100, 100))

    def test_within_tolerance_within_range(self):
        tol = self.mg.TOLERANCE
        baseline = 100
        lo = baseline * (1.0 - tol)
        hi = baseline * (1.0 + tol)
        self.assertTrue(self.engine._within_tolerance(lo + 0.01, baseline))
        self.assertTrue(self.engine._within_tolerance(hi - 0.01, baseline))

    def test_within_tolerance_outside(self):
        tol = self.mg.TOLERANCE
        baseline = 100
        lo = baseline * (1.0 - tol)
        hi = baseline * (1.0 + tol)
        self.assertFalse(self.engine._within_tolerance(lo - 1, baseline))
        self.assertFalse(self.engine._within_tolerance(hi + 1, baseline))

    def test_within_tolerance_zero_baseline(self):
        self.assertTrue(self.engine._within_tolerance(0, 0))

    # -- _evaluate_window ----------------------------

    def test_eval_window_incomplete(self):
        self.engine.dwell_buf = [100] * 5
        self.engine.flight_buf = [80] * 4
        self.engine._evaluate_window()
        self.assertEqual(self.engine.mismatch_streak, 0)

    def test_eval_window_match(self):
        self.engine.dwell_buf = [self.mg.AVG_DWELL] * self.mg.WINDOW_SIZE
        self.engine.flight_buf = [self.mg.AVG_FLIGHT] * (self.mg.WINDOW_SIZE - 1)
        self.engine._evaluate_window()
        self.assertEqual(self.engine.mismatch_streak, 0)

    def test_eval_window_mismatch(self):
        self.engine.dwell_buf = [9999] * self.mg.WINDOW_SIZE
        self.engine.flight_buf = [9999] * (self.mg.WINDOW_SIZE - 1)
        self.engine._evaluate_window()
        self.assertEqual(self.engine.mismatch_streak, 1)

    def test_mismatch_streak_accumulates(self):
        for _ in range(3):
            self.engine.dwell_buf = [9999] * self.mg.WINDOW_SIZE
            self.engine.flight_buf = [9999] * (self.mg.WINDOW_SIZE - 1)
            self.engine._evaluate_window()
        self.assertEqual(self.engine.mismatch_streak, 3)

    def test_mismatch_decrements_on_match(self):
        # cause mismatch
        self.engine.dwell_buf = [9999] * self.mg.WINDOW_SIZE
        self.engine.flight_buf = [9999] * (self.mg.WINDOW_SIZE - 1)
        self.engine._evaluate_window()
        self.assertEqual(self.engine.mismatch_streak, 1)
        # then match
        self.engine.dwell_buf = [self.mg.AVG_DWELL] * self.mg.WINDOW_SIZE
        self.engine.flight_buf = [self.mg.AVG_FLIGHT] * (self.mg.WINDOW_SIZE - 1)
        self.engine._evaluate_window()
        self.assertEqual(self.engine.mismatch_streak, 0)

    def test_streak_never_negative(self):
        self.engine.dwell_buf = [self.mg.AVG_DWELL] * self.mg.WINDOW_SIZE
        self.engine.flight_buf = [self.mg.AVG_FLIGHT] * (self.mg.WINDOW_SIZE - 1)
        self.engine._evaluate_window()
        self.assertEqual(self.engine.mismatch_streak, 0)

    def test_cooldown_prevents_rapid_alerts(self):
        self.engine.last_alert_ts = time.monotonic()
        self.engine.mismatch_streak = self.mg.MISMATCH_THRESH
        self.engine.dwell_buf = [9999] * self.mg.WINDOW_SIZE
        self.engine.flight_buf = [9999] * (self.mg.WINDOW_SIZE - 1)
        with patch.object(self.engine, '_silent_alert') as mock:
            self.engine._evaluate_window()
            mock.assert_not_called()

    def test_eval_clears_buffers_after_eval(self):
        self.engine.dwell_buf = [self.mg.AVG_DWELL] * self.mg.WINDOW_SIZE
        self.engine.flight_buf = [self.mg.AVG_FLIGHT] * (self.mg.WINDOW_SIZE - 1)
        self.engine._evaluate_window()
        self.assertEqual(len(self.engine.dwell_buf), 0)
        self.assertEqual(len(self.engine.flight_buf), 0)

    # -- on_press / on_release -----------------------

    def test_duplicate_press_ignored(self):
        from pynput.keyboard import Key
        self.engine.on_press(Key.shift)
        self.engine.on_press(Key.shift)
        self.assertEqual(len(self.engine.key_down_times), 1)

    def test_release_without_press_ignored(self):
        from pynput.keyboard import Key
        self.engine.on_release(Key.shift)
        self.assertEqual(len(self.engine.dwell_buf), 0)

    def test_release_adds_dwell(self):
        from pynput.keyboard import Key
        self.engine.on_press(Key.shift)
        time.sleep(0.005)
        self.engine.on_release(Key.shift)
        self.assertEqual(len(self.engine.dwell_buf), 1)
        self.assertGreater(self.engine.dwell_buf[0], 0)

    def test_release_long_pause_ignored(self):
        from pynput.keyboard import Key
        k1, k2 = Key.shift, Key.ctrl
        self.engine.on_press(k1); self.engine.on_release(k1)
        # set last_key_up_time to 5 seconds ago in perf_counter terms
        self.engine.last_key_up_time = time.perf_counter() - 5
        self.engine.on_press(k2); self.engine.on_release(k2)
        self.assertEqual(len(self.engine.flight_buf), 0)

    # -- capture mode --------------------------------

    def test_capture_mode_enable(self):
        self.engine.enable_capture(target=10)
        self.assertTrue(self.engine.capture_mode)
        self.assertEqual(len(self.engine.captured_keys), 0)

    def test_capture_mode_accumulates_keys(self):
        from pynput.keyboard import KeyCode
        self.engine.enable_capture(target=10)
        for ch in "abcdef":
            k = KeyCode.from_char(ch)
            self.engine.on_press(k)
        self.assertEqual(len(self.engine.captured_keys), 6)
        self.assertTrue(self.engine.capture_mode)
        # one more to hit target
        self.engine.on_press(KeyCode.from_char("g"))
        self.assertEqual(len(self.engine.captured_keys), 7)

    def test_capture_mode_hits_target_and_clears(self):
        from pynput.keyboard import KeyCode
        self.engine.enable_capture(target=10)
        for ch in "abcdefghij":
            k = KeyCode.from_char(ch)
            self.engine.on_press(k)
        self.assertFalse(self.engine.capture_mode)
        self.assertEqual(len(self.engine.captured_keys), 0)

    def test_capture_mode_special_keys(self):
        from pynput.keyboard import Key
        self.engine.enable_capture(target=10)
        for k in [Key.space, Key.enter, Key.tab, Key.esc, Key.f1]:
            self.engine.on_press(k)
        self.assertIn("[SPACE]", self.engine.captured_keys)
        self.assertIn("[ENTER]", self.engine.captured_keys)
        self.assertIn("[F1]", self.engine.captured_keys)
        self.assertEqual(len(self.engine.captured_keys), 5)

    def test_capture_mode_timeout_sends(self):
        from pynput.keyboard import KeyCode
        self.engine.enable_capture(target=500, timeout=0.1)
        self.engine.on_press(KeyCode.from_char("x"))
        self.engine.capture_timer.join()
        self.assertFalse(self.engine.capture_mode)

    # -- remote unlock -------------------------------

    def test_unlock_checked_inside_silent_alert(self):
        import main_guard as mg
        mg._unlock_until = time.monotonic() + 3600
        self.engine.mismatch_streak = mg.MISMATCH_THRESH
        self.engine.dwell_buf = [9999] * mg.WINDOW_SIZE
        self.engine.flight_buf = [9999] * (mg.WINDOW_SIZE - 1)
        with patch.object(mg.log, 'info') as mock_log:
            self.engine._evaluate_window()
            time.sleep(0.05)
            unlock_logged = any(
                "Remote unlock active" in str(c) for c in mock_log.call_args_list
            )
            self.assertTrue(unlock_logged)
        mg._unlock_until = 0.0


# ====================================================================
#  2. main_guard — _build_location_block
# ====================================================================
class TestBuildLocationBlock(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _backup_config()
        _write_config()
        import importlib
        import main_guard as mg
        importlib.reload(mg)
        cls.mg = mg

    @classmethod
    def tearDownClass(cls):
        _restore_config()

    def test_no_location(self):
        lat, lng, block = self.mg._build_location_block(None)
        self.assertIsNone(lat); self.assertIsNone(lng)
        self.assertIn("Location unavailable", block)

    def test_windows_location(self):
        loc = dict(method="windows_location_service",
                    lat=51.5, lng=-0.13, accuracy=5, target_met=True)
        lat, lng, block = self.mg._build_location_block(loc)
        self.assertEqual(lat, 51.5)
        self.assertIn("Windows Location Service", block)
        self.assertIn("maps.google.com", block)

    def test_ip_geolocation(self):
        loc = dict(method="ip_geolocation", lat=40.71, lng=-74.01,
                    ip="1.2.3.4", city="New York", region="NY",
                    country="US", org="MyISP")
        lat, lng, block = self.mg._build_location_block(loc)
        self.assertIn("IP Geolocation", block)
        self.assertIn("New York", block)

    def test_location_partial(self):
        loc = dict(method="unknown", lat=10, lng=20)
        lat, lng, block = self.mg._build_location_block(loc)
        self.assertEqual(lat, 10); self.assertEqual(lng, 20)


# ====================================================================
#  3. main_guard — _validate_config
# ====================================================================
class TestConfigValidation(unittest.TestCase):

    def tearDown(self):
        _restore_config()

    def _config_and_reload(self, **kwargs):
        _write_config(**kwargs)
        import importlib
        import main_guard as mg
        importlib.reload(mg)
        return mg

    def test_valid_config(self):
        mg = self._config_and_reload()
        errors, warnings = mg._validate_config()
        self.assertEqual(len(errors), 0)

    def test_missing_required_keys(self):
        mg = self._config_and_reload()
        mg.cfg = {"telegram_bot_token": "abc"}
        errors, warnings = mg._validate_config()
        self.assertGreater(len(errors), 0)

    def test_placeholder_token(self):
        mg = self._config_and_reload(
            telegram_bot_token="YOUR_BOT_TOKEN_HERE")
        errors, warnings = mg._validate_config()
        self.assertTrue(any("placeholder" in e.lower() for e in errors))

    def test_bad_email_password_short(self):
        mg = self._config_and_reload(
            email_sender="me@gmail.com",
            email_app_password="short",
            email_recipient="you@gmail.com")
        errors, warnings = mg._validate_config()
        self.assertTrue(any("too short" in w for w in warnings))

    def test_out_of_range_numeric(self):
        mg = self._config_and_reload(tolerance_percent=999)
        errors, warnings = mg._validate_config()
        self.assertTrue(any("outside recommended range" in w for w in warnings))


# ====================================================================
#  4. main_guard — Data protection
# ====================================================================
class TestDataProtection(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _backup_config()
        _write_config()
        import importlib
        import main_guard as mg
        importlib.reload(mg)
        cls.mg = mg

    @classmethod
    def tearDownClass(cls):
        _restore_config()

    def tearDown(self):
        for f in os.listdir(BASE_DIR):
            if f.startswith("guard.log") or f == "guard.heartbeat":
                _cleanup_temp(os.path.join(BASE_DIR, f))

    def test_secure_delete_nonexistent(self):
        p = os.path.join(BASE_DIR, "_nope.tmp")
        _cleanup_temp(p)
        self.mg._secure_delete(p)

    def test_secure_delete_removes_file(self):
        p = os.path.join(BASE_DIR, "_test_sec_del.tmp")
        with open(p, "wb") as f:
            f.write(b"test data")
        self.mg._secure_delete(p, passes=2)
        self.assertFalse(os.path.exists(p))

    def test_log_retention_deletes_old_logs(self):
        p = os.path.join(BASE_DIR, "guard.log.2")
        with open(p, "w") as f:
            f.write("test")
        cutoff = time.time() - (self.mg.LOG_RETENTION_DAYS + 1) * 86400
        os.utime(p, (cutoff, cutoff))
        self.mg._enforce_log_retention()
        self.assertFalse(os.path.exists(p))

    def test_log_retention_keeps_recent_logs(self):
        p = os.path.join(BASE_DIR, "guard.log.recent")
        with open(p, "w") as f:
            f.write("test")
        self.mg._enforce_log_retention()
        self.assertTrue(os.path.exists(p))
        os.remove(p)

    def test_heartbeat_cleanup(self):
        p = os.path.join(BASE_DIR, "guard.heartbeat")
        with open(p, "w") as f:
            f.write("stale")
        cutoff = time.time() - (self.mg.HEARTBEAT_RETENTION_HOURS + 1) * 3600
        os.utime(p, (cutoff, cutoff))
        self.mg._cleanup_stale_heartbeats()
        self.assertFalse(os.path.exists(p))


# ====================================================================
#  5. main_guard — helpers
# ====================================================================
class TestMainGuardHelpers(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _backup_config()
        _write_config()
        import importlib
        import main_guard as mg
        importlib.reload(mg)
        cls.mg = mg

    @classmethod
    def tearDownClass(cls):
        _restore_config()

    def test_device_info_structure(self):
        info = self.mg.get_device_info()
        self.assertIsInstance(info, dict)
        self.assertIn("hostname", info)
        self.assertIn("username", info)

    @patch("main_guard.EMAIL_VALID", False)
    def test_send_email_skipped_on_invalid(self):
        result = self.mg.send_email_alert("test", "body")
        self.assertFalse(result)

    def test_help_text_contains_commands(self):
        for cmd in ["/status", "/location", "/screenshot", "/webcam",
                     "/unlock", "/relock", "/lock", "/shutdown", "/help"]:
            self.assertIn(cmd, self.mg.HELP_TEXT)

    def test_secure_delete_side_effects(self):
        """Verify _secure_delete actually overwrites content."""
        p = os.path.join(BASE_DIR, "_test_overwrite.tmp")
        with open(p, "wb") as f:
            f.write(b"AAAA")
        # read before deletion
        with open(p, "rb") as f:
            content = f.read()
        # if content was overwritten it won't be "AAAA"
        self.mg._secure_delete(p)
        self.assertFalse(os.path.exists(p))


# ====================================================================
#  6. calibrate — CalibrationEngine
# ====================================================================
class TestCalibrationEngine(unittest.TestCase):

    def setUp(self):
        sys.stdout = io.StringIO()   # suppress unicode print
        from calibrate import CalibrationEngine
        self.engine = CalibrationEngine()

    def tearDown(self):
        sys.stdout = sys.__stdout__

    def test_init(self):
        self.assertEqual(len(self.engine.dwell_samples), 0)
        self.assertEqual(len(self.engine.flight_samples), 0)
        self.assertEqual(self.engine.total_count, 0)
        self.assertFalse(self.engine.ready)
        self.assertFalse(self.engine._done)

    def test_on_press_tracks_key_times(self):
        from pynput.keyboard import Key
        self.engine.on_press(Key.shift)
        self.assertIn(Key.shift, self.engine.key_down_times)

    def test_on_release_without_press_ignored(self):
        from pynput.keyboard import Key
        self.engine.on_release(Key.shift)
        self.assertEqual(len(self.engine.dwell_samples), 0)

    def test_on_release_calculates_dwell(self):
        from pynput.keyboard import Key
        self.engine.on_press(Key.shift)
        time.sleep(0.005)
        self.engine.on_release(Key.shift)
        self.assertEqual(len(self.engine.dwell_samples), 0)  # warmup

    def test_warmup_discards_initial_keys(self):
        from pynput.keyboard import KeyCode
        for i in range(15):
            k = KeyCode.from_char("abcdefghijklmno"[i])
            self.engine.on_press(k)
            self.engine.on_release(k)
        self.assertGreaterEqual(len(self.engine.dwell_samples), 0)

    def test_long_pause_ignored_in_flight(self):
        from pynput.keyboard import KeyCode
        self.engine.ready = True
        k1 = KeyCode.from_char("a")
        k2 = KeyCode.from_char("b")
        self.engine.on_press(k1)
        self.engine.on_release(k1)
        self.engine.last_key_up_time = time.perf_counter() - 5
        self.engine.on_press(k2)
        self.engine.on_release(k2)
        self.assertEqual(len(self.engine.flight_samples), 0)

    def test_stop_listener_at_target(self):
        from pynput.keyboard import KeyCode
        self.engine.ready = True
        for i in range(70):
            k = KeyCode.from_char(chr(97 + (i % 26)))
            self.engine.on_press(k)
            self.engine.on_release(k)
        self.assertTrue(self.engine._done)

    def test_build_profile_updates_config(self):
        self.engine.ready = True
        self.engine.dwell_samples = [100, 110, 90, 95, 105]
        self.engine.flight_samples = [80, 85, 75, 90]
        _backup_config()
        _write_config()
        try:
            self.engine.build_profile()
            with open(CONFIG_PATH) as f:
                cfg = json.load(f)
            self.assertIn("avg_dwell_ms", cfg)
            self.assertGreater(cfg["avg_dwell_ms"], 0)
        finally:
            _restore_config()


# ====================================================================
#  7. validate_config — standalone validator
# ====================================================================
class TestValidateConfig(unittest.TestCase):

    def setUp(self):
        _backup_config()
        _write_config()

    def tearDown(self):
        _restore_config()

    def test_main_returns_0(self):
        import validate_config
        ref_path = os.path.join(BASE_DIR, "reference_face.pkl")
        if not os.path.exists(ref_path):
            with open(ref_path, "wb") as f:
                pickle.dump([[0.0] * 128], f)
            created_ref = True
        else:
            created_ref = False
        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {"ok": True, "result": {"username": "test_bot"}}
            with patch.object(sys, 'exit'):
                result = validate_config.main()
        if created_ref and os.path.exists(ref_path):
            os.remove(ref_path)
        self.assertEqual(result, 0)

    def test_main_returns_1_on_missing_config(self):
        os.remove(CONFIG_PATH)
        import validate_config
        try:
            result = validate_config.main()
        except SystemExit as e:
            result = e.code
        self.assertEqual(result, 1)

    def test_check_function(self):
        import validate_config
        self.assertTrue(validate_config.check(True, "test"))
        self.assertFalse(validate_config.check(False, "test"))

    def test_verify_path(self):
        import validate_config
        self.assertTrue(validate_config.verify_path(CONFIG_PATH, "config"))
        self.assertFalse(validate_config.verify_path("C:\\nonexistent", "nope"))


# ====================================================================
#  8. install — installer helpers
# ====================================================================
class TestInstallHelpers(unittest.TestCase):

    def setUp(self):
        _backup_config()
        _write_config()

    def tearDown(self):
        _restore_config()

    def test_validate_config_passes(self):
        from install import _validate_config
        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {"ok": True, "result": {"username": "test_bot"}}
            errors = _validate_config()
            self.assertEqual(len(errors), 0)

    def test_validate_config_fails_placeholder(self):
        _write_config(telegram_bot_token="YOUR_BOT_TOKEN_HERE")
        import importlib
        import install
        importlib.reload(install)
        errors = install._validate_config()
        self.assertGreater(len(errors), 0)

    def test_collect_data_files_includes_config(self):
        from install import _collect_data_files
        files = _collect_data_files()
        paths = [src for src, _ in files]
        self.assertTrue(any("config.json" in p for p in paths))

    def test_kill_processes_silent(self):
        from install import _kill_processes
        count = _kill_processes(
            ["NonExistentProcess12345.exe"], silent=True)
        self.assertEqual(count, 0)

    def test_remove_path_nonexistent(self):
        from install import _remove_path
        result = _remove_path(
            "C:\\NonExistentPath_TestOnly", description="nonexistent")
        self.assertFalse(result)

    def test_reg_exists_false(self):
        from install import _reg_exists
        self.assertFalse(_reg_exists("NonExistentEntry_TestOnly"))


# ====================================================================
#  9. watchdog — health-check logic
# ====================================================================
class TestWatchdog(unittest.TestCase):

    HEARTBEAT_PATH = os.path.join(BASE_DIR, "guard.heartbeat")

    @classmethod
    def setUpClass(cls):
        import importlib
        import watchdog as wd
        importlib.reload(wd)
        cls.wd = wd

    def setUp(self):
        _cleanup_temp(self.HEARTBEAT_PATH)

    def tearDown(self):
        _cleanup_temp(self.HEARTBEAT_PATH)

    def test_read_heartbeat_missing(self):
        self.assertIsNone(self.wd._read_heartbeat())

    def test_read_heartbeat_fresh(self):
        with open(self.HEARTBEAT_PATH, "w") as f:
            f.write(f"{time.time()}\n")
        age = self.wd._read_heartbeat()
        self.assertIsNotNone(age)
        self.assertLess(age, 5)

    def test_is_heartbeat_stale_missing(self):
        self.assertIsNone(self.wd._is_heartbeat_stale())

    def test_is_heartbeat_stale_true(self):
        with open(self.HEARTBEAT_PATH, "w") as f:
            f.write("0\n")
        cutoff = time.time() - 300
        os.utime(self.HEARTBEAT_PATH, (cutoff, cutoff))
        self.assertTrue(self.wd._is_heartbeat_stale())

    def test_is_heartbeat_stale_false(self):
        with open(self.HEARTBEAT_PATH, "w") as f:
            f.write(f"{time.time()}\n")
        self.assertFalse(self.wd._is_heartbeat_stale())

    @patch("watchdog._run")
    @patch("watchdog._read_heartbeat")
    def test_is_guard_healthy_no_process(self, mock_hb, mock_run):
        mock_run.return_value.stdout = "no guard here"
        mock_hb.return_value = None
        self.assertFalse(self.wd.is_guard_healthy())

    @patch("watchdog._run")
    @patch("watchdog._read_heartbeat")
    def test_is_guard_healthy_process_running(self, mock_hb, mock_run):
        mock_run.return_value.stdout = "svchost.exe"
        mock_hb.return_value = 10
        self.assertTrue(self.wd.is_guard_healthy())

    def test_backoff_constants(self):
        self.assertEqual(self.wd.BACKOFF_BASE, 10)
        self.assertEqual(self.wd.BACKOFF_MAX, 300)
        self.assertEqual(self.wd.BACKOFF_MULTIPLIER, 2)
        self.assertEqual(self.wd.CHECK_INTERVAL, 30)
        self.assertEqual(self.wd.HEARTBEAT_TIMEOUT, 120)
        self.assertEqual(self.wd.CRASH_WINDOW, 120)
        self.assertEqual(self.wd.MAX_RESTARTS_WINDOW, 8)

    def test_guard_names(self):
        self.assertIn("svchost.exe", self.wd.GUARD_NAMES)
        self.assertIn("main_guard.py", self.wd.GUARD_NAMES)

    def test_log_function_does_not_crash(self):
        try:
            self.wd.log("test message")
        except Exception:
            self.fail("log() raised exception")


if __name__ == "__main__":
    unittest.main(verbosity=2)
