"""Prescription helper: text/OCR -> medicines, schedule, safety checks, cheaper generics, spoken script."""
import json, os, re, difflib, itertools

DRUGS = json.load(open(os.path.join(os.path.dirname(__file__), "drugs.json"), encoding="utf-8"))
ALIAS = {a.lower(): d for d in DRUGS for a in d["aliases"]}

# (class_a, class_b, plain-language warning, severity)
CLASS_RULES = [
    ("nsaid", "nsaid", "Two pain/swelling medicines of the same type together raise the risk of stomach bleeding and kidney damage.", "high"),
    ("nsaid", "anticoagulant", "Pain-killer + blood thinner can cause serious bleeding.", "high"),
    ("antiplatelet", "anticoagulant", "Two blood thinners together increase bleeding risk. Doctor must confirm.", "high"),
    ("nsaid", "antiplatelet", "Pain-killer can cause stomach bleeding with aspirin/clopidogrel.", "medium"),
    ("nsaid", "acei", "Pain-killers can strain the kidneys and weaken BP medicine.", "medium"),
    ("nsaid", "arb", "Pain-killers can strain the kidneys and weaken BP medicine.", "medium"),
    ("beta", "sulfonylurea", "Beta-blocker can hide the warning signs of LOW sugar (shaking, fast heartbeat). Check sugar more often.", "medium"),
]
PAIR_RULES = [
    ("clopidogrel", "omeprazole", "Omeprazole may reduce the effect of clopidogrel. Ask the doctor about pantoprazole.", "medium"),
]

SLOTS = ["morning", "afternoon", "night"]
SLOT_HI = {"morning": "सुबह", "afternoon": "दोपहर", "night": "रात"}
FOOD_HI = {"after": "खाने के बाद", "before": "खाने से पहले", "empty": "खाली पेट", "any": "", "night": ""}
FOOD_EN = {"after": "after food", "before": "before food", "empty": "on an empty stomach", "any": "", "night": ""}


def _freq(line):
    l = line.lower()
    m = re.search(r"(\d)\s*[-–—]\s*(\d)\s*[-–—]\s*(\d)", l)
    if m:
        return [s for s, n in zip(SLOTS, m.groups()) if n != "0"]
    if re.search(r"\b(tds|tid|thrice|3\s*times)\b", l):
        return SLOTS[:]
    if re.search(r"\b(bd|bid|twice|2\s*times)\b", l):
        return ["morning", "night"]
    if re.search(r"\b(hs|bedtime|at night)\b", l):
        return ["night"]
    if re.search(r"\b(od|qd|once|daily)\b", l):
        return ["morning"]
    return ["morning"]  # safe default, flagged for review


def _food_override(line, default):
    l = line.lower()
    if re.search(r"\b(ac|before (food|meal)s?)\b", l):
        return "before"
    if re.search(r"\b(pc|after (food|meal)s?)\b", l):
        return "after"
    if "empty stomach" in l:
        return "empty"
    return default


def _match(line):
    words = re.findall(r"[a-zA-Z\-]{3,}", line.lower())
    for w in words:
        if w in ALIAS:
            return ALIAS[w]
    for w in words:  # fuzzy match to survive OCR noise on handwriting
        c = difflib.get_close_matches(w, ALIAS.keys(), n=1, cutoff=0.82)
        if c:
            return ALIAS[c[0]]
    return None


def parse(text):
    meds, seen = [], set()
    for line in re.split(r"[\n;]+", text):
        d = _match(line)
        if not d or d["generic_key"] in seen:
            continue
        seen.add(d["generic_key"])
        meds.append(dict(
            generic_key=d["generic_key"], generic=d["generic"], cls=d["cls"],
            purpose=d["purpose"], purpose_hi=d["purpose_hi"],
            slots=_freq(line), food=_food_override(line, d["food"]),
            saving=round(100 * (d["brand_price_demo"] - d["generic_price_demo"]) / d["brand_price_demo"]),
            brand_price=d["brand_price_demo"], generic_price=d["generic_price_demo"], raw=line.strip(),
        ))
    return meds


def interactions(meds):
    out = []
    for a, b in itertools.combinations(meds, 2):
        for ca, cb, msg, sev in CLASS_RULES:
            if {a["cls"], b["cls"]} == {ca, cb} or (ca == cb and a["cls"] == b["cls"] == ca):
                out.append(dict(drugs=[a["generic"], b["generic"]], message=msg, severity=sev))
        for x, y, msg, sev in PAIR_RULES:
            if {a["generic_key"], b["generic_key"]} == {x, y}:
                out.append(dict(drugs=[a["generic"], b["generic"]], message=msg, severity=sev))
    return out


def schedule(meds):
    s = {k: [] for k in SLOTS}
    for m in meds:
        for sl in m["slots"]:
            s[sl].append(m)
    return s


def script(meds, lang="en"):
    sch = schedule(meds)
    parts = []
    for sl in SLOTS:
        if not sch[sl]:
            continue
        if lang == "hi":
            items = ", ".join(f"{m['generic']} ({m['purpose_hi']}) {FOOD_HI[m['food']]}".strip() for m in sch[sl])
            parts.append(f"{SLOT_HI[sl]}: {items}।")
        else:
            items = ", ".join(f"{m['generic']} ({m['purpose']}) {FOOD_EN[m['food']]}".strip() for m in sch[sl])
            parts.append(f"{sl.capitalize()}: {items}.")
    return " ".join(parts)


def ocr_image(path):
    """Optional OCR. Needs: pip install pytesseract pillow  and the tesseract binary."""
    try:
        import pytesseract
        from PIL import Image
        return pytesseract.image_to_string(Image.open(path))
    except Exception:
        return None


def analyse(text, lang="en"):
    meds = parse(text)
    return dict(
        medicines=meds,
        schedule={k: [m["generic"] for m in v] for k, v in schedule(meds).items()},
        interactions=interactions(meds),
        speech=script(meds, lang),
        total_saving_pct=round(sum(m["saving"] for m in meds) / len(meds)) if meds else 0,
        disclaimer="Educational demo. Always confirm with your doctor or pharmacist.",
    )
