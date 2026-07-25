# Installation Guide

Detailed installation instructions for Deadman's Switch.

## System Requirements

### Minimum Requirements
- **Operating System**: Windows 10 or later
- **Python**: 3.8 or higher (3.10+ recommended)
- **RAM**: 2GB minimum, 4GB recommended
- **Disk Space**: 500MB for installation
- **Internet**: Required for alerts and some features
- **Webcam**: Optional, for face recognition

### Recommended Requirements
- **Operating System**: Windows 11
- **Python**: 3.10 or 3.11
- **RAM**: 8GB
- **Disk Space**: 1GB
- **Webcam**: HD webcam for face recognition
- **Administrator Access**: For full functionality

## Prerequisites Installation

### 1. Install Python

#### Windows
1. Download Python from [python.org](https://www.python.org/downloads/)
2. Run the installer
3. **Important**: Check "Add Python to PATH"
4. Verify installation:
```bash
python --version
pip --version
```

#### Verify Python Version
```bash
python --version
# Should show Python 3.8.0 or higher
```

### 2. Install Git (Optional)

For cloning from GitHub:
1. Download from [git-scm.com](https://git-scm.com/downloads)
2. Run installer with default settings
3. Verify:
```bash
git --version
```

## Installation Methods

### Method 1: Clone from GitHub (Recommended)

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/guard_pro.git
cd guard_pro

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Method 2: Download ZIP File

1. Go to [GitHub repository](https://github.com/YOUR_USERNAME/guard_pro)
2. Click "Code" → "Download ZIP"
3. Extract to desired location
4. Open command prompt in extracted folder
5. Follow steps from Method 1 (starting from virtual environment)

### Method 3: Manual Installation

```bash
# Create project directory
mkdir guard_pro
cd guard_pro

# Create virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies manually
pip install pynput>=1.7.6
pip install requests>=2.31.0
pip install pyautogui>=0.9.54
pip install Pillow>=10.0.0
pip install pywin32>=306
pip install opencv-python>=4.8.0
pip install dlib-bin
pip install face_recognition>=1.3.0
pip install face_recognition_models>=0.3.0
pip install click
pip install colorama
pip install cryptography>=41.0.0
pip install pyinstaller>=6.0.0
```

## Configuration Setup

### 1. Telegram Bot Setup

#### Create Telegram Bot
1. Open Telegram and search for `@BotFather`
2. Send `/newbot` command
3. Follow the instructions to create your bot
4. Copy the bot token (format: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

#### Get Chat ID
1. Send a message to your new bot
2. Open this URL in your browser:
   ```
   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   ```
3. Find `"chat":{"id":XXXXXXX}` in the response
4. Copy the chat ID

### 2. Email Setup (Optional)

#### Generate Gmail App Password
1. Go to [Google Account Security](https://myaccount.google.com/security)
2. Enable 2-Factor Authentication if not already enabled
3. Search for "App Passwords"
4. Click "App Passwords"
5. Select "Mail" and your device (e.g., "Windows Computer")
6. Click "Generate"
7. Copy the 16-character password

### 3. Configure Application

#### Option A: Use Configuration UI (Recommended)
```bash
python config_ui.py
```
This provides a graphical interface for all configuration.

#### Option B: Manual Configuration
Edit `config.json`:
```json
{
  "telegram_bot_token": "YOUR_BOT_TOKEN",
  "telegram_chat_id": "YOUR_CHAT_ID",
  "email_sender": "your_email@gmail.com",
  "email_app_password": "YOUR_APP_PASSWORD",
  "email_recipient": "recipient@example.com"
}
```

## Calibration

### 1. Keystroke Calibration

```bash
python calibrate.py
```
- Type naturally for ~70 keystrokes
- The first 10 keystrokes are warm-up (discarded)
- Your typing rhythm is saved to config.json

### 2. Face Recognition Calibration (Optional)

```bash
python calibrate_face.py
```
- Press SPACE to capture your face from different angles
- Move your head between captures for better coverage
- Press ENTER when done to save

## Pre-Installation Validation

Run the configuration validator:
```bash
python validate_config.py
```

This checks:
- All required configuration values
- Telegram token validity
- Email authentication (if configured)
- Calibration data
- Webcam access
- Dependencies

## Installation

### Standard Installation

```bash
python install.py
```

### Administrator Installation (Recommended)

1. Right-click on Command Prompt
2. Select "Run as Administrator"
3. Navigate to project directory
4. Run:
```bash
python install.py
```

### What Installation Does

1. **Compiles to EXE** (if PyInstaller available)
   - Creates `dist/svchost.exe` (main guard)
   - Creates `dist/sihost.exe` (watchdog)

2. **Registers Startup Entries**
   - Adds guard to Windows startup
   - Adds watchdog to Windows startup
   - Uses innocuous process names

3. **Copies Runtime Files**
   - config.json
   - reference_face.pkl
   - guard.key

4. **Sets Permissions**
   - Configures file permissions
   - Sets up directory structure

## Verification

### 1. Check Running Processes

```bash
tasklist | findstr "svchost"
tasklist | findstr "sihost"
```

You should see both processes running.

### 2. Check Startup Entries

1. Open Task Manager (Ctrl+Shift+Esc)
2. Go to "Startup" tab
3. Look for "WindowsUpdateSvc" and "ShellInfraSvc"

### 3. Test Alert System

Send a test message to your Telegram bot to verify connectivity.

## Uninstallation

### Standard Uninstallation

```bash
python install.py --remove
```

### Manual Uninstallation

1. **Remove Startup Entries**
   ```bash
   # Open Registry Editor
   regedit
   # Navigate to: HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run
   # Delete: WindowsUpdateSvc and ShellInfraSvc
   ```

2. **Kill Processes**
   ```bash
   taskkill /F /IM svchost.exe
   taskkill /F /IM sihost.exe
   ```

3. **Remove Files**
   ```bash
   rmdir /s /q dist
   rmdir /s /q build
   del *.spec
   rmdir /s /q __pycache__
   del guard.log
   del guard.key
   del guard.heartbeat
   rmdir /s /q offline_queue
   ```

## Troubleshooting

### Installation Issues

#### Python Not Found
```bash
# Ensure Python is in PATH
where python
# If not found, reinstall Python with "Add to PATH" checked
```

#### Permission Denied
```bash
# Run Command Prompt as Administrator
# Right-click Command Prompt → Run as Administrator
```

#### Dependencies Fail to Install
```bash
# Update pip
python -m pip install --upgrade pip

# Install each dependency individually
pip install pynput
pip install requests
# ... etc
```

### Configuration Issues

#### Telegram Token Invalid
1. Verify token format: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`
2. Test token: `https://api.telegram.org/bot<TOKEN>/getMe`
3. Generate new token from @BotFather if needed

#### Email Authentication Failed
1. Ensure 2-Factor Authentication is enabled
2. Generate new App Password
3. Verify email and password are correct

### Runtime Issues

#### Guard Not Starting
1. Check crash_log.txt for errors
2. Verify all dependencies are installed
3. Run `python validate_config.py`
4. Check antivirus software isn't blocking execution

#### Webcam Not Working
1. Ensure webcam is connected
2. Close other applications using webcam
3. Check Windows privacy settings
4. Test with other applications

#### Location Not Working
1. Enable Windows Location Service
2. Check privacy settings
3. Ensure internet connection for IP geolocation

## Advanced Installation

### Custom Installation Directory

```bash
# Install to custom location
python install.py --custom-path "C:\Custom\Path"
```

### Development Installation

```bash
# Install in development mode
pip install -e .

# This allows you to edit code without reinstalling
```

### Docker Installation (Future)

```bash
# Docker support planned for future release
# Linux/macOS containers
```

## Post-Installation Steps

### 1. Test Basic Functionality

```bash
# Run basic tests
python test_guard.py
```

### 2. Configure Sensitivity

Edit `config.json` to adjust detection sensitivity:
```json
{
  "tolerance_percent": 60,
  "mismatch_threshold": 4,
  "mismatch_window": 10
}
```

### 3. Enable Additional Features

Gradually enable features as needed:
```json
{
  "face_check_enabled": true,
  "usb_monitor_enabled": true,
  "offline_alarm_enabled": true
}
```

### 4. Set Up Monitoring

Configure log monitoring and alert testing.

## Security Considerations

### Protect Configuration Files

```bash
# Set restrictive permissions on config files
icacls config.json /inheritance:r
icacls config.json /grant:r "%USERNAME%:F"
```

### Regular Updates

```bash
# Update dependencies regularly
pip install --upgrade -r requirements.txt

# Check for security updates
pip install --upgrade pip
pip check
```

### Backup Configuration

```bash
# Backup your configuration
copy config.json config.json.backup
copy reference_face.pkl reference_face.pkl.backup
```

## Support

If you encounter issues:

1. Check [Troubleshooting Guide](https://github.com/YOUR_USERNAME/guard_pro/wiki/Troubleshooting)
2. Search [GitHub Issues](https://github.com/YOUR_USERNAME/guard_pro/issues)
3. Create a new issue with:
   - Detailed description of the problem
   - Steps to reproduce
   - Error messages and logs
   - System information

---

**Installation complete! Your Deadman's Switch is now protecting your system.** 🎉
