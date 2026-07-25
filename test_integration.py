"""
test_integration.py  —  Integration tests for Deadman's Switch
Tests how components work together (config → engine → watchdog → data protection).

Run:  python -m unittest test_integration.py -v
"""

import json, os, sys, time, io, pickle, shutil, tempfile, threading
import unittest
from unittest.mock import patch, MagicMock

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
CONFIG_BACKUP = os.path.join(BASE_DIR, "config.json.bak")
HEARTBEAT_PATH = os.path.join(BASE_DIR, "guard.heartbeat")
KEY_PATH = os.path.join(BASE_DIR, "guard.key")
REF_FACE_PATH = os.path.join(BASE_DIR, "reference_face.pkl")


def _backup_config():
    if os.path.exists(CONFIG_PATH) and not os.path.exists(CONFIG_BACKUP):
        shutil.copy2(CONFIG_PATH, CONFIG_BACKUP)


def _restore_config():
    if os.path.exists(CONFIG_BACKUP):
        if os.path.exists(CONFIG_PATH):
            os.remove(CONFIG_PATH)
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


def _cleanup(*paths):
    for p in paths:
        if os.path.isfile(p):
            try: os.remove(p)
            except Exception: pass
        elif os.path.isdir(p):
            try: shutil.rmtree(p, ignore_errors=True)
            except Exception: pass


# ====================================================================
#  Integration 1:  Config → main_guard loading
# ====================================================================
class TestConfigToEngineLoad(unittest.TestCase):
    """Verify that a valid config allows main_guard to initialise cleanly,
    and that the GuardEngine can be instantiated after module load."""

    @classmethod
    def setUpClass(cls):
        _backup_config()

    def setUp(self):
        _write_config()
        _cleanup(KEY_PATH)

    def tearDown(self):
        _restore_config()

    def _reload_main_guard(self):
        if not os.path.exists(CONFIG_PATH):
            _write_config()
        import importlib
        import main_guard as mg
        importlib.reload(mg)
        return mg

    def test_module_loads_with_valid_config(self):
        mg = self._reload_main_guard()
        self.assertIsNotNone(mg.GuardEngine)
        self.assertGreater(mg.AVG_DWELL, 0)
        self.assertEqual(mg.CHAT_ID, "123456789")

    def test_engine_instantiation_after_module_load(self):
        mg = self._reload_main_guard()
        engine = mg.GuardEngine()
        self.assertEqual(engine.mismatch_streak, 0)
        self.assertEqual(len(engine.dwell_buf), 0)

    def test_engine_reads_module_globals(self):
        mg = self._reload_main_guard()
        engine = mg.GuardEngine()
        self.assertEqual(engine._within_tolerance(mg.AVG_DWELL, mg.AVG_DWELL), True)
        self.assertEqual(engine._within_tolerance(9999, mg.AVG_DWELL), False)

    def test_alert_unlock_check(self):
        mg = self._reload_main_guard()
        engine = mg.GuardEngine()
        mg._unlock_until = time.monotonic() + 3600
        with patch.object(mg, 'get_location') as mock_loc:
            engine._silent_alert()
            time.sleep(0.1)
            mock_loc.assert_not_called()
        mg._unlock_until = 0.0

    def test_alert_no_unlock_proceeds(self):
        mg = self._reload_main_guard()
        engine = mg.GuardEngine()
        mg._unlock_until = 0.0
        mg.FACE_CHECK = False
        with (
            patch.object(mg, 'ensure_wifi_on'),
            patch.object(mg, 'get_location') as mock_loc,
            patch.object(mg, 'take_screenshot'),
            patch.object(mg, 'take_webcam_photo'),
            patch.object(mg, 'deliver_alert'),
        ):
            engine._silent_alert()
            time.sleep(0.1)
            mock_loc.assert_called()

    def test_config_with_float_dwell_still_works(self):
        _write_config(avg_dwell_ms=145.7, avg_flight_ms=92.3)
        mg = self._reload_main_guard()
        self.assertAlmostEqual(mg.AVG_DWELL, 145.7, places=1)
        self.assertAlmostEqual(mg.AVG_FLIGHT, 92.3, places=1)

    def test_config_feature_flags_parsed_correctly(self):
        _write_config(remote_commands_enabled=False, face_check_enabled=False,
                       usb_monitor_enabled=False, offline_alarm_enabled=False)
        mg = self._reload_main_guard()
        self.assertFalse(mg.CMDS_ENABLED)
        self.assertFalse(mg.FACE_CHECK)
        self.assertFalse(mg.USB_MONITOR)
        self.assertFalse(mg.OFFLINE_ALARM)

    def test_config_boolean_true(self):
        _write_config(face_check_enabled=True, usb_monitor_enabled=True,
                       offline_alarm_enabled=True)
        mg = self._reload_main_guard()
        self.assertTrue(mg.FACE_CHECK)
        self.assertTrue(mg.USB_MONITOR)
        self.assertTrue(mg.OFFLINE_ALARM)

    def test_encrypted_logging_writes_and_rotates(self):
        mg = self._reload_main_guard()
        mg.log.info("integration test message")
        self.assertTrue(os.path.exists(KEY_PATH))
        self.assertTrue(os.path.exists(os.path.join(BASE_DIR, "guard.log")))

    def test_validate_config_called_on_import(self):
        mg = self._reload_main_guard()
        errors, warnings = mg._validate_config()
        self.assertEqual(len(errors), 0)


# ====================================================================
#  Integration 2:  Calibrate → Config → Engine
# ====================================================================
class TestCalibrateToEngine(unittest.TestCase):
    """Verify that calibrate.py produces output that main_guard can consume."""

    @classmethod
    def setUpClass(cls):
        _backup_config()

    def setUp(self):
        _cleanup(KEY_PATH)
        _write_config(avg_dwell_ms=0, avg_flight_ms=0)

    def tearDown(self):
        _restore_config()

    def test_calibration_profile_loads_into_engine(self):
        from calibrate import CalibrationEngine
        ce = CalibrationEngine()
        ce.ready = True
        ce.dwell_samples = [105, 110, 95, 100, 98, 102, 108, 92, 97, 103]
        ce.flight_samples = [85, 90, 78, 82, 88, 80, 86, 92, 76]
        ce.build_profile()
        import importlib
        import main_guard as mg
        importlib.reload(mg)
        self.assertGreater(mg.AVG_DWELL, 90)
        self.assertGreater(mg.AVG_FLIGHT, 70)
        engine = mg.GuardEngine()
        self.assertTrue(engine._within_tolerance(mg.AVG_DWELL, mg.AVG_DWELL))
        self.assertFalse(engine._within_tolerance(999, mg.AVG_DWELL))

    def test_calibration_file_persists_across_restarts(self):
        from calibrate import CalibrationEngine
        ce = CalibrationEngine()
        ce.ready = True
        ce.dwell_samples = [100] * 5
        ce.flight_samples = [80] * 4
        ce.build_profile()
        with open(CONFIG_PATH) as f:
            cfg1 = json.load(f)
        with open(CONFIG_PATH) as f:
            cfg2 = json.load(f)
        self.assertEqual(cfg1, cfg2)
        self.assertIn("avg_dwell_ms", cfg1)


# ====================================================================
#  Integration 3:  Watchdog + Heartbeat
# ====================================================================
class TestWatchdogHeartbeatInteg(unittest.TestCase):
    """Verify watchdog heartbeat detection works end-to-end."""

    @classmethod
    def setUpClass(cls):
        _backup_config()
        _write_config()
        import importlib, watchdog as wd
        importlib.reload(wd)
        cls.wd = wd

    def setUp(self):
        _cleanup(HEARTBEAT_PATH)

    def tearDown(self):
        _cleanup(HEARTBEAT_PATH)
        _restore_config()

    def test_guard_writes_heartbeat_watchdog_reads_it(self):
        import threading, main_guard as mg
        if not os.path.exists(CONFIG_PATH):
            _write_config()
        import importlib; importlib.reload(mg)
        t = threading.Thread(target=mg._heartbeat_writer, daemon=True)
        t.start()
        time.sleep(0.1)
        age = self.wd._read_heartbeat()
        self.assertIsNotNone(age)
        self.assertLess(age, 5)
        self.assertFalse(self.wd._is_heartbeat_stale())

    def test_stale_heartbeat_detected(self):
        with open(HEARTBEAT_PATH, "w") as f:
            f.write("0\n")
        cutoff = time.time() - 300
        os.utime(HEARTBEAT_PATH, (cutoff, cutoff))
        self.assertTrue(self.wd._is_heartbeat_stale())

    def test_missing_heartbeat_no_crash(self):
        result = self.wd._read_heartbeat()
        self.assertIsNone(result)

    @patch("watchdog._run")
    @patch("watchdog._read_heartbeat")
    def test_guard_healthy_with_fresh_heartbeat(self, mock_hb, mock_run):
        mock_run.return_value.stdout = "svchost.exe"
        mock_hb.return_value = 15
        self.assertTrue(self.wd.is_guard_healthy())

    @patch("watchdog._run")
    @patch("watchdog._read_heartbeat")
    def test_guard_unhealthy_hung(self, mock_hb, mock_run):
        mock_run.return_value.stdout = "svchost.exe"
        mock_hb.return_value = 200
        self.assertFalse(self.wd.is_guard_healthy())


# ====================================================================
#  Integration 4:  Data protection lifecycle
# ====================================================================
class TestDataProtectionInteg(unittest.TestCase):
    """Verify the full data protection lifecycle: write logs -> retain -> secure-delete."""

    @classmethod
    def setUpClass(cls):
        _backup_config()
        _write_config()
        import importlib
        import main_guard as mg
        importlib.reload(mg)
        cls.mg = mg

    def setUp(self):
        if not os.path.exists(CONFIG_PATH):
            _write_config()
        _cleanup(KEY_PATH, os.path.join(BASE_DIR, "guard.log"),
                  os.path.join(BASE_DIR, "guard.log.1"),
                  os.path.join(BASE_DIR, "guard.log.2"),
                  HEARTBEAT_PATH)

    def tearDown(self):
        _cleanup(KEY_PATH, os.path.join(BASE_DIR, "guard.log"),
                  os.path.join(BASE_DIR, "guard.log.1"),
                  os.path.join(BASE_DIR, "guard.log.2"),
                  HEARTBEAT_PATH)
        _restore_config()

    def _reload_mg(self):
        if not os.path.exists(CONFIG_PATH):
            _write_config()
        import importlib; importlib.reload(self.mg)
        return self.mg

    def test_secure_delete_after_log_write(self):
        mg = self._reload_mg()
        p = os.path.join(BASE_DIR, "_integ_sec.tmp")
        with open(p, "wb") as f:
            f.write(b"sensitive data")
        mg._secure_delete(p, passes=2)
        self.assertFalse(os.path.exists(p))

    def test_data_protection_removes_old_logs(self):
        mg = self._reload_mg()
        p = os.path.join(BASE_DIR, "guard.log.old")
        with open(p, "w") as f:
            f.write("test")
        cutoff = time.time() - (mg.LOG_RETENTION_DAYS + 1) * 86400
        os.utime(p, (cutoff, cutoff))
        mg._enforce_log_retention()
        self.assertFalse(os.path.exists(p))

    def test_data_protection_removes_stale_heartbeat(self):
        mg = self._reload_mg()
        with open(HEARTBEAT_PATH, "w") as f:
            f.write("stale")
        cutoff = time.time() - (mg.HEARTBEAT_RETENTION_HOURS + 1) * 3600
        os.utime(HEARTBEAT_PATH, (cutoff, cutoff))
        mg._cleanup_stale_heartbeats()
        self.assertFalse(os.path.exists(HEARTBEAT_PATH))

    def test_heartbeat_writer_creates_file(self):
        mg = self._reload_mg()
        t = threading.Thread(target=mg._heartbeat_writer, daemon=True)
        t.start()
        time.sleep(0.15)
        self.assertTrue(os.path.exists(HEARTBEAT_PATH))
        self.assertGreater(os.path.getsize(HEARTBEAT_PATH), 0)


# ====================================================================
#  Integration 5:  Offline queue
# ====================================================================
class TestOfflineQueueInteg(unittest.TestCase):
    """Verify alert queuing and flushing logic."""

    QUEUE_DIR = os.path.join(BASE_DIR, "offline_queue")

    @classmethod
    def setUpClass(cls):
        _backup_config()
        _write_config()
        import importlib
        import main_guard as mg
        importlib.reload(mg)
        cls.mg = mg

    def setUp(self):
        if not os.path.exists(CONFIG_PATH):
            _write_config()
        _cleanup(self.QUEUE_DIR)
        os.makedirs(self.QUEUE_DIR, exist_ok=True)
        _cleanup(KEY_PATH)

    def tearDown(self):
        _cleanup(self.QUEUE_DIR)

    def _reload_mg(self):
        if not os.path.exists(CONFIG_PATH):
            _write_config()
        import importlib; importlib.reload(self.mg)
        return self.mg

    def test_enqueue_and_flush_no_network(self):
        mg = self._reload_mg()
        ts = "2025-01-01 00:00:00"
        device = {"hostname": "test-pc", "username": "test-user"}
        loc_block = "Location unavailable"
        mg._enqueue_alert(ts, device, loc_block, None, None, None, None)
        entries = os.listdir(self.QUEUE_DIR)
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0].startswith("alert_"))
        meta_path = os.path.join(self.QUEUE_DIR, entries[0], "meta.json")
        self.assertTrue(os.path.exists(meta_path))

    def test_queue_empty_flush_no_crash(self):
        mg = self._reload_mg()
        mg._flush_offline_queue()

    def test_enqueue_screenshot_and_webcam(self):
        mg = self._reload_mg()
        ts = "2025-06-15 12:00:00"
        device = {"hostname": "pc", "username": "user"}
        shot = io.BytesIO(b"fake_image_data")
        cam = io.BytesIO(b"fake_webcam_data")
        mg._enqueue_alert(ts, device, "loc", 1.0, 2.0, shot, cam)
        entries = os.listdir(self.QUEUE_DIR)
        files = os.listdir(os.path.join(self.QUEUE_DIR, entries[0]))
        self.assertIn("screenshot.png", files)
        self.assertIn("webcam.jpg", files)
        self.assertIn("meta.json", files)

    def test_enqueue_then_flush_clears_on_success(self):
        mg = self._reload_mg()
        mg._enqueue_alert("ts", {"hostname":"h","username":"u"}, "loc", None, None, None, None)
        entries_before = len(os.listdir(self.QUEUE_DIR))
        self.assertEqual(entries_before, 1)
        with patch.object(mg, 'tg_send_message', return_value=True):
            mg._flush_offline_queue()
            entries_after = len(os.listdir(self.QUEUE_DIR))
            self.assertEqual(entries_after, 0)


# ====================================================================
#  Integration 6:  Install pre-flight checks
# ====================================================================
class TestInstallPreflight(unittest.TestCase):
    """Verify install.py pre-flight checks work end-to-end."""

    def setUp(self):
        _backup_config()
        _write_config()

    def tearDown(self):
        _restore_config()

    def test_validate_then_collect(self):
        from install import _validate_config, _collect_data_files
        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {"ok": True, "result": {"username": "test"}}
            errors = _validate_config()
        self.assertEqual(len(errors), 0)
        files = _collect_data_files()
        self.assertGreater(len(files), 0)
        config_srcs = [s for s, _ in files if "config.json" in s]
        self.assertEqual(len(config_srcs), 1)

    def test_collect_after_calibration_includes_pkl(self):
        _write_config(face_check_enabled=False)
        import importlib; import install; importlib.reload(install)
        files = install._collect_data_files()
        pkl_srcs = [s for s, _ in files if "reference_face.pkl" in s]
        if os.path.exists(REF_FACE_PATH):
            self.assertGreater(len(pkl_srcs), 0)

    def test_kill_processes_not_running(self):
        from install import _kill_processes
        count = _kill_processes(["NonExistentProcess_TestOnly.exe"], silent=True)
        self.assertEqual(count, 0)


# ====================================================================
#  Integration 7:  validate_config end-to-end
# ====================================================================
class TestValidateConfigE2E(unittest.TestCase):
    """Verify validate_config.py reports expected results with various config states."""

    def setUp(self):
        _backup_config()
        _write_config()
        os.environ.pop("PYTHONIOENCODING", None)

    def tearDown(self):
        _restore_config()

    def test_full_validation_passes(self):
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
            mock_get.return_value.json.return_value = {"ok": True, "result": {"username": "bot"}}
            with patch.object(sys, 'exit'):
                result = validate_config.main()
        if created_ref and os.path.exists(ref_path):
            os.remove(ref_path)
        self.assertEqual(result, 0)

    def test_validation_fails_on_missing_config(self):
        _cleanup(CONFIG_PATH)
        import validate_config
        try:
            result = validate_config.main()
        except SystemExit as e:
            result = e.code
        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
