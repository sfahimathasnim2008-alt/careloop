"""Risk engine: classifies readings and predicts where they are heading.
Thresholds are general adult guidance values for a student demo, not a diagnosis.
"""
from datetime import datetime

LEVELS = ["normal", "watch", "danger", "critical"]


def classify_glucose(v, context="random"):
    high_watch = 130 if context == "fasting" else 180
    if v < 54:
        return dict(level="critical", title="Severe LOW sugar", steps=[
            "Give 15 g fast sugar NOW: 3 glucose tablets, or 3 tsp sugar in water, or half a cup of juice.",
            "If the person is confused, drowsy or unconscious, give nothing by mouth and call 108 immediately.",
            "Recheck in 15 minutes; repeat if still below 70.",
        ])
    if v < 70:
        return dict(level="danger", title="LOW sugar", steps=[
            "Take 15 g fast sugar now (3 glucose tablets or 3 tsp sugar in water).",
            "Recheck in 15 minutes. Repeat if still below 70, then eat a small snack.",
            "Tell family. Do not drive or stay alone.",
        ])
    if v > 350:
        return dict(level="critical", title="Dangerously HIGH sugar", steps=[
            "Drink water and contact the doctor immediately.",
            "If there is vomiting, fast breathing, drowsiness or stomach pain, go to the hospital or call 108.",
        ])
    if v > 250:
        return dict(level="danger", title="Very HIGH sugar", steps=[
            "Drink water, take medicines exactly as prescribed, avoid sweets.",
            "Recheck in 2 hours. If still above 250, call the doctor today.",
        ])
    if v > high_watch:
        return dict(level="watch", title="Sugar above target", steps=[
            "Drink water, take a 10-15 minute walk if you feel well.",
            "Note what you ate. Discuss repeated high readings with the doctor.",
        ])
    return dict(level="normal", title="Sugar in safe range", steps=["Keep following your diet and medicines."])


def classify_bp(sys_, dia):
    if sys_ >= 180 or dia >= 120:
        return dict(level="critical", title="Hypertensive crisis range", steps=[
            "Sit down, rest quietly and recheck after 5 minutes.",
            "If chest pain, breathlessness, severe headache, weakness or trouble speaking: call 108 now.",
            "Otherwise contact the doctor immediately.",
        ])
    if sys_ < 90 or dia < 60:
        return dict(level="danger", title="LOW blood pressure", steps=[
            "Sit or lie down, raise the legs, drink water or ORS.",
            "If dizzy, fainting or confused, call the doctor or 108.",
        ])
    if sys_ >= 160 or dia >= 100:
        return dict(level="danger", title="HIGH blood pressure", steps=[
            "Rest 5 minutes and recheck. Take medicines as prescribed; avoid salt today.",
            "If it stays high, call the doctor today.",
        ])
    if sys_ >= 140 or dia >= 90:
        return dict(level="watch", title="BP above target", steps=[
            "Rest, reduce salt, and keep logging. Mention repeated readings to the doctor.",
        ])
    return dict(level="normal", title="BP in safe range", steps=["Keep following your diet and medicines."])


def _slope_per_hour(points):
    """Least squares slope over [(datetime, value)]. Returns None if not enough data."""
    if len(points) < 3:
        return None
    t0 = points[0][0]
    xs = [(p[0] - t0).total_seconds() / 3600 for p in points]
    ys = [p[1] for p in points]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den


def predict(kind, history, horizon_hours=3):
    """history: list of (iso_ts, value) oldest->newest (latest 6 used).
    Returns dict(predicted_value, warning) or None."""
    pts = [(datetime.fromisoformat(t), v) for t, v in history][-6:]
    slope = _slope_per_hour(pts)
    if slope is None:
        return None
    proj = pts[-1][1] + slope * horizon_hours
    warning = None
    if kind == "glucose":
        if proj < 70 and pts[-1][1] >= 70:
            warning = f"Sugar is falling about {abs(slope):.0f} mg/dL per hour and may drop below 70 within {horizon_hours} hours."
        elif proj > 250 and pts[-1][1] <= 250:
            warning = f"Sugar is rising about {slope:.0f} mg/dL per hour and may cross 250 within {horizon_hours} hours."
    elif kind == "bp":
        if proj >= 160 and pts[-1][1] < 160:
            warning = f"Systolic BP is rising about {slope:.0f} mmHg per hour and may reach 160 within {horizon_hours} hours."
    return dict(predicted_value=round(proj), warning=warning)
