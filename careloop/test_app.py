import os, tempfile
os.environ["DB_PATH"] = tempfile.mktemp(suffix=".db")
import app as A
c = A.app.test_client()

def test_classify():
    import risk
    assert risk.classify_glucose(50)["level"] == "critical"
    assert risk.classify_glucose(65)["level"] == "danger"
    assert risk.classify_glucose(110)["level"] == "normal"
    assert risk.classify_bp(185, 100)["level"] == "critical"
    assert risk.classify_bp(120, 80)["level"] == "normal"

def test_seed_and_predictive_alert():
    assert c.post("/api/seed", json={}).status_code == 200
    r = c.post("/api/reading", json={"kind": "glucose", "value": 84}).get_json()
    assert r["prediction"]["warning"], r
    assert r["alerted"]
    assert len(c.get("/api/alerts").get_json()) >= 1

def test_low_sugar_alerts_family():
    r = c.post("/api/reading", json={"kind": "glucose", "value": 58}).get_json()
    assert r["level"] == "danger" and r["alerted"]

def test_validation():
    assert c.post("/api/reading", json={"kind": "glucose", "value": 5}).status_code == 400
    assert c.post("/api/reading", json={"kind": "bp", "value": 130}).status_code == 400

def test_voice():
    assert c.post("/api/voice-parse", json={"text": "sugar 180"}).get_json()["value"] == 180
    p = c.post("/api/voice-parse", json={"text": "bp 150 by 95"}).get_json()
    assert p["kind"] == "bp" and p["value2"] == 95

def test_prescription():
    txt = "Tab Glycomet 500 1-0-1 after food\nTab Ecosprin 75 0-0-1\nTab Brufen 400 TDS\nTab Warf 5 OD"
    r = c.post("/api/prescription", json={"text": txt, "lang": "hi"}).get_json()
    assert len(r["medicines"]) == 4
    pairs = [tuple(sorted(i["drugs"])) for i in r["interactions"]]
    assert ("Aspirin", "Ibuprofen") in pairs and ("Ibuprofen", "Warfarin") in pairs
    assert "सुबह" in r["speech"]

def test_ocr_noise():
    r = c.post("/api/prescription", json={"text": "Tab Glycomat 500 BD", "lang": "en"}).get_json()
    assert r["medicines"][0]["generic"] == "Metformin"

def test_meds_and_sos():
    assert c.post("/api/meds", json={"name": "Metformin", "time": "08:00"}).status_code == 200
    assert c.post("/api/meds", json={"name": "x", "time": "8am"}).status_code == 400
    assert len(c.get("/api/meds").get_json()) == 1
    assert c.post("/api/sos").get_json()["sent_via"]
    assert c.get("/manifest.json").status_code == 200 and c.get("/sw.js").status_code == 200
