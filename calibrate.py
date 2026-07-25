"""
calibrate.py  –  Keystroke-dynamics baseline profiler
Run this ONCE on your own machine to establish your typing profile.
Results are saved directly into config.json.
"""

import time
import json
import os
import statistics

from pynput import keyboard

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

TARGET = 60          # keystrokes to collect for a reliable baseline
WARMUP = 10          # first N keystrokes discarded (let you settle)

BANNER = """
+====================================================+
|   DEADMAN'S SWITCH  -  Keystroke Dynamics Calibrator |
+====================================================+

 Type naturally in any application for {total} keystrokes.
 The first {warm} are a warm-up and will be discarded.

 Press any key to begin ...
""".format(total=TARGET + WARMUP, warm=WARMUP)


class CalibrationEngine:
    def __init__(self):
        self.key_down_times   = {}
        self.last_key_up_time = None

        self.dwell_samples  = []
        self.flight_samples = []
        self.total_count    = 0
        self.ready          = False        # True after warm-up is done
        self._done          = False

    # ── pynput callbacks ────────────────────────────────────────────────────

    def on_press(self, key):
        if key not in self.key_down_times:
            self.key_down_times[key] = time.perf_counter()

    def on_release(self, key):
        now = time.perf_counter()

        if key not in self.key_down_times:
            return

        dwell_s = now - self.key_down_times.pop(key)

        if self.last_key_up_time is not None:
            flight_s = now - self.last_key_up_time
            # Ignore pauses longer than 2 seconds — not genuine typing rhythm
            if self.ready and flight_s < 2.0:
                self.flight_samples.append(flight_s * 1000)

        self.last_key_up_time = now
        self.total_count += 1

        if self.total_count == WARMUP:
            self.ready = True
            print(f"\n  Warm-up complete. Now capturing {TARGET} keystrokes …\n")

        if self.ready:
            self.dwell_samples.append(dwell_s * 1000)
            captured = len(self.dwell_samples)
            bar = "#" * captured + "-" * (TARGET - captured)
            print(f"  [{bar}] {captured}/{TARGET}", end="\r", flush=True)

            if captured >= TARGET:
                self._done = True
                return False      # stop listener

    # ── post-collection ─────────────────────────────────────────────────────

    def build_profile(self):
        d = self.dwell_samples
        f = self.flight_samples

        profile = {
            "avg_dwell_ms":  round(statistics.mean(d),   2),
            "avg_flight_ms": round(statistics.mean(f),   2),
            "std_dwell_ms":  round(statistics.stdev(d),  2),
            "std_flight_ms": round(statistics.stdev(f),  2),
        }

        print("\n\n  +==============================+")
        print(  "  |   CALIBRATION COMPLETE       |")
        print(  "  +==============================+")
        print(f"\n  Dwell  - avg: {profile['avg_dwell_ms']:.1f} ms  "
              f"std: {profile['std_dwell_ms']:.1f} ms")
        print(f"  Flight - avg: {profile['avg_flight_ms']:.1f} ms  "
              f"std: {profile['std_flight_ms']:.1f} ms")

        # Merge into config.json
        with open(CONFIG_PATH, "r") as fh:
            cfg = json.load(fh)

        cfg.update(profile)

        with open(CONFIG_PATH, "w") as fh:
            json.dump(cfg, fh, indent=2)

        print(f"\n  [OK] Profile saved to {CONFIG_PATH}")
        print("  You can now run install.py to activate the guard.\n")


# ── entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(BANNER)
    input()           # wait for Enter

    engine = CalibrationEngine()
    with keyboard.Listener(
            on_press=engine.on_press,
            on_release=engine.on_release) as listener:
        listener.join()

    if engine._done:
        engine.build_profile()
    else:
        print("\n  Calibration cancelled.")
