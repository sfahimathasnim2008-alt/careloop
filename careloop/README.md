# CareLoop: Health Safety Loop + Prescription Helper
VibeX Codes, Track 2: Easy, Safe & Smart Healthcare for Everyone.

## Problem
1. Patients with diabetes or blood pressure have no smart watcher between doctor visits.
2. Prescriptions are confusing, risky to combine, and branded medicines cost far more than generics.

## What it does
- **Health Safety Loop**: log sugar/BP by typing or by voice (Hindi or English), get instant risk level and safe steps, a trend-based early warning (linear regression over recent readings), and automatic family alerts (in-app log + optional Telegram bot).
- **Prescription Helper**: photo (OCR) or pasted text, finds medicines even with spelling noise, builds a morning/afternoon/night schedule, flags dangerous combinations and duplicates, shows cheaper generics, and reads the plan aloud in simple Hindi or English.

## Tech
Python, Flask, SQLite, rule-based safety engine, least-squares trend prediction, fuzzy matching (difflib), optional Tesseract OCR, browser Web Speech API for voice in and out, Telegram Bot API for alerts.

## Run
    pip install -r requirements.txt
    python app.py          # open http://localhost:5000
    python -c "import test_app as T; [getattr(T,n)() for n in dir(T) if n.startswith('test_')]"

Optional alerts: set `TELEGRAM_BOT_TOKEN`, then add the chat id in the Family tab.
Optional OCR: `pip install pytesseract pillow` and install the Tesseract program.

## Demo script (2 to 3 min)
1. Family tab: set names. Readings tab: tap **Load demo data** (sugar falling 190 to 96).
2. Save sugar **84**: early warning says it may drop below 70, family alerted, spoken instructions play.
3. Say "sugar 58": severe low flow. Check the Alerts tab.
4. Prescription tab: paste the sample text below, press Explain: schedule, aspirin + ibuprofen + warfarin warnings, generic savings, play Hindi audio.

Sample prescription:

    Tab Glycomet 500 1-0-1 after food
    Tab Ecosprin 75 0-0-1
    Tab Brufen 400 TDS
    Tab Warf 5 OD

## Limits (say this to judges)
Educational prototype, not a medical device. Thresholds are general adult values; drug rules and prices in `drugs.json`/`rx.py` are a small demo set (prices are illustrative). Next steps: full CDSCO/Jan Aushadhi data, doctor-set personal thresholds, WhatsApp alerts.

## Easiest way to open it
- Windows: double-click `run.bat`
- Mac/Linux: run `bash run.sh`
The dashboard opens automatically at http://127.0.0.1:5000 (use Chrome). Keep the black window open while using the app.

## Troubleshooting
- "python is not recognized": install Python from python.org and tick "Add python.exe to PATH". Or use `py app.py`.
- "No such file or directory": the terminal is not inside the folder that contains app.py. Use run.bat instead, or `cd` into that folder.
- "Address already in use": another copy is running. Close it, or run `set PORT=5001` (Windows) / `PORT=5001 python app.py` (Mac/Linux) and open port 5001.
- Page will not load: make sure the black window still shows "CareLoop is running" and you typed http://127.0.0.1:5000 (not https).

## Use it like a phone app
Open the dashboard in Chrome on your phone (same Wi-Fi: use `http://YOUR-PC-IP:5000` after running with host 0.0.0.0, or deploy it), then Chrome menu > **Add to Home screen**. It opens full screen with its own icon, bottom tabs, medicine reminders and an SOS button.
