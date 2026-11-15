import os, re, json, sqlite3, tempfile, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, render_template

import risk, rx

DB = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "health.db"))
app = Flask(__name__)


def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS patient(id INTEGER PRIMARY KEY, name TEXT, language TEXT DEFAULT 'en',
            family_name TEXT, telegram_chat_id TEXT);
        CREATE TABLE IF NOT EXISTS reading(id INTEGER PRIMARY KEY, kind TEXT, value REAL, value2 REAL,
            context TEXT, ts TEXT, level TEXT);
        CREATE TABLE IF NOT EXISTS med(id INTEGER PRIMARY KEY, name TEXT, time TEXT);
        CREATE TABLE IF NOT EXISTS alert(id INTEGER PRIMARY KEY, ts TEXT, level TEXT, message TEXT, sent_via TEXT);
        """)
        if not c.execute("SELECT 1 FROM patient").fetchone():
            c.execute("INSERT INTO patient(name,language,family_name) VALUES('Ramesh','hi','Family')")


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def send_alert(level, message):
    """Logs every alert; also pushes to Telegram if TELEGRAM_BOT_TOKEN and a chat id are configured."""
    via = "app"
    with db() as c:
        p = c.execute("SELECT * FROM patient LIMIT 1").fetchone()
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if token and p["telegram_chat_id"]:
            try:
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                data = urllib.parse.urlencode({"chat_id": p["telegram_chat_id"],
                                               "text": f"HEALTH ALERT for {p['name']}: {message}"}).encode()
                urllib.request.urlopen(url, data, timeout=5)
                via = "app+telegram"
            except Exception:
                via = "app (telegram failed)"
        c.execute("INSERT INTO alert(ts,level,message,sent_via) VALUES(?,?,?,?)",
                  (now().isoformat(timespec="seconds"), level, message, via))
    return via


def add_reading(kind, value, value2=None, context="random", ts=None, alerts=True):
    ts = ts or now().isoformat(timespec="seconds")
    res = risk.classify_glucose(value, context) if kind == "glucose" else risk.classify_bp(value, value2)
    with db() as c:
        c.execute("INSERT INTO reading(kind,value,value2,context,ts,level) VALUES(?,?,?,?,?,?)",
                  (kind, value, value2, context, ts, res["level"]))
        hist = [(r["ts"], r["value"]) for r in c.execute(
            "SELECT ts,value FROM reading WHERE kind=? ORDER BY ts DESC LIMIT 6", (kind,))][::-1]
    pred = risk.predict(kind, hist)
    out = dict(res, kind=kind, value=value, value2=value2, ts=ts, prediction=pred, alerted=None)
    if alerts:
        label = f"{value:.0f}" if kind == "glucose" else f"{value:.0f}/{value2:.0f}"
        if res["level"] in ("danger", "critical"):
            out["alerted"] = send_alert(res["level"], f"{res['title']} ({label}).")
        elif pred and pred["warning"]:
            out["alerted"] = send_alert("watch", pred["warning"])
    return out


def parse_voice(text):
    """Understands things like 'sugar 180', 'bp 150 by 95', 'शुगर 120', 'ब्लड प्रेशर 130/85'."""
    t = text.lower().replace("बाय", "by")
    m = re.search(r"(\d{2,3})\s*(?:/|by|over|-)\s*(\d{2,3})", t)
    if m or re.search(r"\bbp\b|pressure|प्रेशर|बीपी", t):
        if m:
            return dict(kind="bp", value=float(m.group(1)), value2=float(m.group(2)))
        return None
    n = re.search(r"(\d{2,3})", t)
    if n:
        ctx = "fasting" if re.search(r"fasting|empty|खाली|सुबह", t) else "random"
        return dict(kind="glucose", value=float(n.group(1)), context=ctx)
    return None


@app.route("/")
def index():
    return render_template("index.html")


@app.get("/api/patient")
def get_patient():
    with db() as c:
        return jsonify(dict(c.execute("SELECT * FROM patient LIMIT 1").fetchone()))


@app.post("/api/patient")
def set_patient():
    d = request.get_json(force=True)
    with db() as c:
        c.execute("UPDATE patient SET name=COALESCE(?,name), language=COALESCE(?,language), "
                  "family_name=COALESCE(?,family_name), telegram_chat_id=COALESCE(?,telegram_chat_id)",
                  (d.get("name"), d.get("language"), d.get("family_name"), d.get("telegram_chat_id")))
    return get_patient()


@app.post("/api/reading")
def post_reading():
    d = request.get_json(force=True)
    try:
        kind = d["kind"]
        v = float(d["value"])
        v2 = float(d["value2"]) if d.get("value2") not in (None, "") else None
    except (KeyError, ValueError, TypeError):
        return jsonify(error="Send kind, value (and value2 for bp)."), 400
    if kind not in ("glucose", "bp") or (kind == "bp" and v2 is None):
        return jsonify(error="kind must be glucose or bp; bp needs value2."), 400
    if not (20 <= v <= 700 if kind == "glucose" else 40 <= v <= 300):
        return jsonify(error="That value looks impossible. Please re-check the reading."), 400
    return jsonify(add_reading(kind, v, v2, d.get("context", "random")))


@app.post("/api/voice-parse")
def voice_parse():
    r = parse_voice(request.get_json(force=True).get("text", ""))
    return (jsonify(r), 200) if r else (jsonify(error="Could not understand. Say e.g. 'sugar 180' or 'bp 140 by 90'."), 422)


@app.get("/api/readings")
def readings():
    kind = request.args.get("kind", "glucose")
    with db() as c:
        rows = c.execute("SELECT * FROM reading WHERE kind=? ORDER BY ts DESC LIMIT 30", (kind,)).fetchall()
    return jsonify([dict(r) for r in rows][::-1])


@app.get("/api/alerts")
def alerts():
    with db() as c:
        return jsonify([dict(r) for r in c.execute("SELECT * FROM alert ORDER BY id DESC LIMIT 20")])


@app.post("/api/prescription")
def prescription():
    lang = request.form.get("lang") or (request.get_json(silent=True) or {}).get("lang", "en")
    text = request.form.get("text") or (request.get_json(silent=True) or {}).get("text", "")
    f = request.files.get("image")
    ocr_used = False
    if f and not text.strip():
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            f.save(tmp.name)
        text = rx.ocr_image(tmp.name) or ""
        os.unlink(tmp.name)
        ocr_used = True
        if not text.strip():
            return jsonify(error="OCR is not available or could not read the photo. Type or paste the prescription text instead."), 422
    if not text.strip():
        return jsonify(error="Send a photo or paste the prescription text."), 400
    out = rx.analyse(text, lang)
    out["ocr_used"] = ocr_used
    if not out["medicines"]:
        return jsonify(error="No known medicines found. Try clearer text."), 422
    return jsonify(out)


@app.route("/sw.js")
def sw():
    return app.send_static_file("sw.js"), 200, {"Content-Type": "application/javascript"}


@app.route("/manifest.json")
def manifest():
    return app.send_static_file("manifest.json")


@app.get("/api/meds")
def meds():
    with db() as c:
        return jsonify([dict(r) for r in c.execute("SELECT * FROM med ORDER BY time")])


@app.post("/api/meds")
def add_med():
    d = request.get_json(force=True)
    if not d.get("name") or not re.fullmatch(r"\d{2}:\d{2}", d.get("time", "")):
        return jsonify(error="Need name and time HH:MM"), 400
    with db() as c:
        c.execute("INSERT INTO med(name,time) VALUES(?,?)", (d["name"], d["time"]))
    return meds()


@app.delete("/api/meds/<int:i>")
def del_med(i):
    with db() as c:
        c.execute("DELETE FROM med WHERE id=?", (i,))
    return meds()


@app.post("/api/sos")
def sos():
    return jsonify(sent_via=send_alert("critical", "SOS pressed. The patient needs help now."))


@app.post("/api/seed")
def seed():
    """Loads a demo story: sugar steadily falling toward a low at night (for the video demo)."""
    with db() as c:
        c.execute("DELETE FROM reading"); c.execute("DELETE FROM alert")
    base = now() - timedelta(hours=10)
    series = [190, 172, 150, 131, 112, 96]
    for i, v in enumerate(series):
        add_reading("glucose", v, ts=(base + timedelta(hours=2 * i)).isoformat(timespec="seconds"), alerts=False)
    for i, (s, d) in enumerate([(128, 82), (134, 86), (142, 90), (150, 94)]):
        add_reading("bp", s, d, ts=(base + timedelta(hours=3 * i)).isoformat(timespec="seconds"), alerts=False)
    return jsonify(ok=True, note="Now add a glucose reading like 84 to trigger the predictive alert.")


init_db()
if __name__ == "__main__":
    import threading, webbrowser
    port = int(os.environ.get("PORT", 5000))
    url = f"http://127.0.0.1:{port}"
    print(f"\nCareLoop is running. Open this in Chrome: {url}\nPress Ctrl+C to stop.\n")
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=port, debug=False)
