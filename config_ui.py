"""
config_ui.py  —  Deadman's Switch Configuration Wizard
Provides a Tkinter GUI for setting up Telegram, email, calibration, and testing.

Usage:
  python config_ui.py
"""

import json, os, sys, threading, time, io

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, scrolledtext
except ImportError:
    print("Tkinter not available. Install python-tk or use a system with GUI support.")
    sys.exit(1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


class ConfigUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Deadman's Switch — Configuration")
        self.root.geometry("720x620")
        self.root.resizable(True, True)

        self.cfg = self._load_config()

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        self._build_telegram_tab(nb)
        self._build_email_tab(nb)
        self._build_calibration_tab(nb)
        self._build_testing_tab(nb)
        self._build_about_tab(nb)

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        bar = ttk.Label(self.root, textvariable=self.status_var,
                        relief="sunken", anchor="w")
        bar.pack(fill="x", padx=8, pady=(0, 8))

    def _load_config(self):
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH) as f:
                return json.load(f)
        return {}

    def _save_config(self):
        with open(CONFIG_PATH, "w") as f:
            json.dump(self.cfg, f, indent=2)
        self.status_var.set("Configuration saved.")

    def _set_status(self, msg):
        self.status_var.set(msg)
        self.root.update_idletasks()

    # ── Telegram Tab ──────────────────────────────────────────────
    def _build_telegram_tab(self, nb):
        frame = ttk.Frame(nb, padding=12)
        nb.add(frame, text="Telegram")

        ttk.Label(frame, text="Telegram Bot Token",
                  font=("", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 2))
        self.tg_token = tk.StringVar(value=self.cfg.get("telegram_bot_token", ""))
        ttk.Entry(frame, textvariable=self.tg_token, width=50).grid(row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(frame, text="Validate", command=self._validate_token).grid(row=1, column=1)

        ttk.Label(frame, text="Chat ID",
                  font=("", 10, "bold")).grid(row=2, column=0, sticky="w", pady=(10, 2))
        self.tg_chat = tk.StringVar(value=str(self.cfg.get("telegram_chat_id", "")))
        ttk.Entry(frame, textvariable=self.tg_chat, width=50).grid(row=3, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(frame, text="Get ID", command=self._get_chat_id).grid(row=3, column=1)

        ttk.Label(frame, text="How to get a bot token:",
                  foreground="gray").grid(row=4, column=0, sticky="w", pady=(12, 0))
        ttk.Label(frame, text="1. Open Telegram → search @BotFather → send /newbot",
                  foreground="gray").grid(row=5, column=0, sticky="w")
        ttk.Label(frame, text="2. Copy the token (123456:ABC-DEF...) into the field above",
                  foreground="gray").grid(row=6, column=0, sticky="w")
        ttk.Label(frame, text="3. Message your bot once, then click 'Get ID'",
                  foreground="gray").grid(row=7, column=0, sticky="w")

        self.tg_result = ttk.Label(frame, text="", foreground="blue")
        self.tg_result.grid(row=8, column=0, sticky="w", pady=(8, 0))

        frame.columnconfigure(0, weight=1)

    def _validate_token(self):
        token = self.tg_token.get().strip()
        if not token or token.startswith("YOUR"):
            self.tg_result.config(text="Placeholder token — get a real one from @BotFather", foreground="red")
            return
        self._set_status("Validating Telegram token...")
        def check():
            try:
                import requests
                r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
                if r.status_code == 200 and r.json().get("ok"):
                    bot = r.json()["result"].get("username", "?")
                    self.cfg["telegram_bot_token"] = token
                    self._save_config()
                    self.tg_result.config(text=f"Valid — bot: @{bot}", foreground="green")
                else:
                    self.tg_result.config(text=f"Invalid — check your token", foreground="red")
            except Exception as exc:
                self.tg_result.config(text=f"Error: {exc}", foreground="red")
            self._set_status("Ready")
        threading.Thread(target=check, daemon=True).start()

    def _get_chat_id(self):
        token = self.tg_token.get().strip()
        if not token or token.startswith("YOUR"):
            self.tg_result.config(text="Set a valid token first", foreground="red")
            return
        self._set_status("Fetching latest chat ID...")
        def fetch():
            try:
                import requests
                r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=15)
                if r.status_code == 200:
                    updates = r.json().get("result", [])
                    if updates:
                        chat_id = updates[-1]["message"]["chat"]["id"]
                        self.tg_chat.set(str(chat_id))
                        self.cfg["telegram_chat_id"] = chat_id
                        self._save_config()
                        self.tg_result.config(text=f"Chat ID set: {chat_id}", foreground="green")
                    else:
                        self.tg_result.config(text="No messages yet — message your bot first, then retry",
                                              foreground="orange")
                else:
                    self.tg_result.config(text=f"HTTP {r.status_code}", foreground="red")
            except Exception as exc:
                self.tg_result.config(text=f"Error: {exc}", foreground="red")
            self._set_status("Ready")
        threading.Thread(target=fetch, daemon=True).start()

    # ── Email Tab ─────────────────────────────────────────────────
    def _build_email_tab(self, nb):
        frame = ttk.Frame(nb, padding=12)
        nb.add(frame, text="Email")

        ttk.Label(frame, text="Gmail SMTP Backup",
                  font=("", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 4))

        ttk.Label(frame, text="Sender email:").grid(row=1, column=0, sticky="w")
        self.email_sender = tk.StringVar(value=self.cfg.get("email_sender", ""))
        ttk.Entry(frame, textvariable=self.email_sender, width=50).grid(row=2, column=0, sticky="ew", pady=(0, 6))

        ttk.Label(frame, text="App Password:").grid(row=3, column=0, sticky="w")
        self.email_pass = tk.StringVar(value=self.cfg.get("email_app_password", ""))
        ttk.Entry(frame, textvariable=self.email_pass, width=50, show="*").grid(row=4, column=0, sticky="ew", pady=(0, 6))

        ttk.Label(frame, text="Recipient email:").grid(row=5, column=0, sticky="w")
        self.email_recip = tk.StringVar(value=self.cfg.get("email_recipient", ""))
        ttk.Entry(frame, textvariable=self.email_recip, width=50).grid(row=6, column=0, sticky="ew", pady=(0, 6))

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=7, column=0, sticky="w", pady=4)
        ttk.Button(btn_frame, text="Save & Test", command=self._test_email).pack(side="left")
        ttk.Label(btn_frame, text="  ").pack(side="left")

        ttk.Label(frame, text="How to get an App Password:",
                  foreground="gray").grid(row=8, column=0, sticky="w", pady=(12, 0))
        ttk.Label(frame, text="1. Enable 2-Factor Auth on your Google account",
                  foreground="gray").grid(row=9, column=0, sticky="w")
        ttk.Label(frame, text="2. Google Account → Security → App Passwords",
                  foreground="gray").grid(row=10, column=0, sticky="w")
        ttk.Label(frame, text="3. Select 'Mail' + 'Windows Computer' → generate",
                  foreground="gray").grid(row=11, column=0, sticky="w")

        self.email_result = ttk.Label(frame, text="", foreground="blue")
        self.email_result.grid(row=12, column=0, sticky="w", pady=(8, 0))

        frame.columnconfigure(0, weight=1)

    def _test_email(self):
        sender = self.email_sender.get().strip()
        password = self.email_pass.get().strip()
        recip = self.email_recip.get().strip()
        if not sender or not password or not recip:
            self.email_result.config(text="Fill in all fields first", foreground="red")
            return
        self._set_status("Testing email...")
        def check():
            try:
                import smtplib
                with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
                    server.login(sender, password)
                self.cfg["email_sender"] = sender
                self.cfg["email_app_password"] = password
                self.cfg["email_recipient"] = recip
                self._save_config()
                self.email_result.config(text="SMTP login successful — credentials saved", foreground="green")
            except smtplib.SMTPAuthenticationError:
                self.email_result.config(text="Auth failed — use a Gmail App Password, not your regular password",
                                         foreground="red")
            except Exception as exc:
                self.email_result.config(text=f"Error: {exc}", foreground="red")
            self._set_status("Ready")
        threading.Thread(target=check, daemon=True).start()

    # ── Calibration Tab ───────────────────────────────────────────
    def _build_calibration_tab(self, nb):
        frame = ttk.Frame(nb, padding=12)
        nb.add(frame, text="Calibration")

        ttk.Label(frame, text="Keystroke Baseline",
                  font=("", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text="Current baseline:").grid(row=1, column=0, sticky="w", pady=(6, 0))

        dwell = self.cfg.get("avg_dwell_ms", 0)
        flight = self.cfg.get("avg_flight_ms", 0)
        self.baseline_label = ttk.Label(
            frame,
            text=f"  Dwell: {dwell:.1f} ms   |   Flight: {flight:.1f} ms"
                 if dwell else "  Not calibrated — run calibrate.py")
        self.baseline_label.grid(row=2, column=0, sticky="w", pady=(0, 8))

        ttk.Button(frame, text="Run calibrate.py",
                   command=self._run_calibration).grid(row=3, column=0, sticky="w")
        self.calib_result = ttk.Label(frame, text="", foreground="blue")
        self.calib_result.grid(row=4, column=0, sticky="w", pady=(8, 0))

        ttk.Label(frame, text="Face Recognition",
                  font=("", 10, "bold")).grid(row=5, column=0, sticky="w", pady=(16, 0))
        has_face = os.path.exists(os.path.join(BASE_DIR, "reference_face.pkl"))
        self.face_label = ttk.Label(
            frame,
            text="  Reference face: present" if has_face else "  Reference face: not set")
        self.face_label.grid(row=6, column=0, sticky="w", pady=(4, 8))

        ttk.Button(frame, text="Run calibrate_face.py",
                   command=self._run_face_calibration).grid(row=7, column=0, sticky="w")
        self.face_result = ttk.Label(frame, text="", foreground="blue")
        self.face_result.grid(row=8, column=0, sticky="w", pady=(8, 0))

        # Progress bar (for calibration running)
        self.calib_progress = ttk.Progressbar(frame, mode="indeterminate", length=400)
        self.calib_progress.grid(row=9, column=0, sticky="ew", pady=(12, 0))
        self.calib_progress.grid_remove()

    def _run_calibration(self):
        self.calib_progress.grid()
        self.calib_progress.start()
        self._set_status("Running calibrate.py...")
        def run():
            try:
                import subprocess
                r = subprocess.run(
                    [sys.executable, os.path.join(BASE_DIR, "calibrate.py")],
                    capture_output=True, text=True, timeout=120, cwd=BASE_DIR)
                self.calib_progress.stop()
                self.calib_progress.grid_remove()
                if r.returncode == 0:
                    self.cfg = self._load_config()
                    dwell = self.cfg.get("avg_dwell_ms", 0)
                    flight = self.cfg.get("avg_flight_ms", 0)
                    self.baseline_label.config(
                        text=f"  Dwell: {dwell:.1f} ms   |   Flight: {flight:.1f} ms")
                    self.calib_result.config(text="Calibration complete", foreground="green")
                else:
                    self.calib_result.config(text=f"Error: {r.stderr[:200]}", foreground="red")
            except subprocess.TimeoutExpired:
                self.calib_progress.stop()
                self.calib_progress.grid_remove()
                self.calib_result.config(text="Calibration timed out", foreground="red")
            self._set_status("Ready")
        threading.Thread(target=run, daemon=True).start()

    def _run_face_calibration(self):
        self._set_status("Running calibrate_face.py...")
        def run():
            try:
                import subprocess
                r = subprocess.run(
                    [sys.executable, os.path.join(BASE_DIR, "calibrate_face.py")],
                    capture_output=True, text=True, timeout=120, cwd=BASE_DIR)
                if r.returncode == 0:
                    self.face_label.config(text="  Reference face: present")
                    self.face_result.config(text="Face calibration complete", foreground="green")
                else:
                    self.face_result.config(text=f"Error: {r.stderr[:200]}", foreground="red")
            except subprocess.TimeoutExpired:
                self.face_result.config(text="Face calibration timed out", foreground="red")
            self._set_status("Ready")
        threading.Thread(target=run, daemon=True).start()

    # ── Testing Tab ───────────────────────────────────────────────
    def _build_testing_tab(self, nb):
        frame = ttk.Frame(nb, padding=12)
        nb.add(frame, text="Testing")

        ttk.Label(frame, text="Feature Testing",
                  font=("", 10, "bold")).grid(row=0, column=0, sticky="w")

        self.test_log = scrolledtext.ScrolledText(frame, height=18, width=80, state="disabled")
        self.test_log.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(8, 8))

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=2, column=0, columnspan=3, sticky="w")
        ttk.Button(btn_frame, text="Test Telegram", command=self._test_tg).pack(side="left", padx=(0, 4))
        ttk.Button(btn_frame, text="Test Email", command=self._test_email_alert).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Test Webcam", command=self._test_webcam).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Test Location", command=self._test_location).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Clear Log", command=self._clear_log).pack(side="left", padx=4)

        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

    def _log_test(self, msg):
        self.test_log.config(state="normal")
        self.test_log.insert("end", f"{msg}\n")
        self.test_log.see("end")
        self.test_log.config(state="disabled")
        self.root.update_idletasks()

    def _clear_log(self):
        self.test_log.config(state="normal")
        self.test_log.delete("1.0", "end")
        self.test_log.config(state="disabled")

    def _test_tg(self):
        self._set_status("Testing Telegram...")
        def run():
            try:
                import requests
                cfg = self._load_config()
                token = cfg.get("telegram_bot_token", "")
                chat_id = cfg.get("telegram_chat_id", "")
                if not token or not chat_id:
                    self._log_test("FAIL: Telegram token or chat_id not configured")
                    return
                r = requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": str(chat_id), "text": "Test message from Config UI"},
                    timeout=15)
                if r.status_code == 200:
                    self._log_test("PASS: Telegram message sent successfully")
                else:
                    self._log_test(f"FAIL: HTTP {r.status_code} — {r.text[:100]}")
            except Exception as exc:
                self._log_test(f"FAIL: {exc}")
            self._set_status("Ready")
        threading.Thread(target=run, daemon=True).start()

    def _test_email_alert(self):
        self._set_status("Testing email...")
        def run():
            try:
                import smtplib
                from email.mime.text import MIMEText
                cfg = self._load_config()
                sender = cfg.get("email_sender", "")
                password = cfg.get("email_app_password", "")
                recip = cfg.get("email_recipient", "")
                if not sender or not password or not recip:
                    self._log_test("FAIL: Email not fully configured")
                    return
                msg = MIMEText("Test email from Deadman's Switch Config UI")
                msg["From"] = sender
                msg["To"] = recip
                msg["Subject"] = "Deadman's Switch — Test Email"
                with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
                    server.login(sender, password)
                    server.send_message(msg)
                self._log_test("PASS: Email sent successfully")
            except smtplib.SMTPAuthenticationError:
                self._log_test("FAIL: SMTP auth failed")
            except Exception as exc:
                self._log_test(f"FAIL: {exc}")
            self._set_status("Ready")
        threading.Thread(target=run, daemon=True).start()

    def _test_webcam(self):
        self._set_status("Testing webcam...")
        def run():
            try:
                import cv2
                cap = cv2.VideoCapture(0)
                if not cap.isOpened():
                    self._log_test("FAIL: No webcam detected")
                    return
                for _ in range(5):
                    cap.read()
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None:
                    self._log_test(f"PASS: Webcam captured {frame.shape[1]}x{frame.shape[0]}")
                else:
                    self._log_test("FAIL: Webcam opened but no frame captured")
            except Exception as exc:
                self._log_test(f"FAIL: {exc}")
            self._set_status("Ready")
        threading.Thread(target=run, daemon=True).start()

    def _test_location(self):
        self._set_status("Testing location...")
        def run():
            try:
                import requests
                providers = [
                    ("ip-api.com", "http://ip-api.com/json?fields=status,lat,lon,city,country"),
                    ("ipinfo.io", "https://ipinfo.io/json"),
                    ("ipwhois.app", "https://ipwhois.app/json/"),
                ]
                for name, url in providers:
                    try:
                        r = requests.get(url, timeout=10)
                        if r.status_code == 200:
                            self._log_test(f"PASS: {name} responded")
                        else:
                            self._log_test(f"WARN: {name} HTTP {r.status_code}")
                    except Exception as exc:
                        self._log_test(f"FAIL: {name} — {exc}")
            except Exception as exc:
                self._log_test(f"FAIL: {exc}")
            self._set_status("Ready")
        threading.Thread(target=run, daemon=True).start()

    # ── About Tab ─────────────────────────────────────────────────
    def _build_about_tab(self, nb):
        frame = ttk.Frame(nb, padding=12)
        nb.add(frame, text="About")

        text = (
            "Deadman's Switch — Keystroke Dynamics Anti-Theft System\n\n"
            "Purpose:\n"
            "  Monitors typing rhythm to detect unauthorised access.\n"
            "  Sends alerts (location, screenshot, webcam) via Telegram.\n\n"
            "Data collected:\n"
            "  • Keystroke timing only (dwell + flight times)\n"
            "  • Screenshots (on alert only)\n"
            "  • Webcam photos (on alert only)\n"
            "  • Device location (on alert only)\n"
            "  • USB drive insertion events\n\n"
            "What is NOT collected:\n"
            "  • Key content (passwords, messages) — never stored or transmitted\n"
            "  • Browser history, files, or personal documents\n\n"
            "Privacy:\n"
            "  All logs are AES-256 encrypted (Fernet).\n"
            "  Data is stored locally on your device.\n"
            "  No third-party access unless you configure Telegram/email.\n\n"
            "Uninstall:\n"
            "  python install.py --remove\n\n"
            "More info:\n"
            "  See README.md for full documentation."
        )
        ttk.Label(frame, text=text, justify="left",
                  font=("", 9)).pack(anchor="w")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    ConfigUI().run()
