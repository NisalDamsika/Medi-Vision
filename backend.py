"""
Medi Vision -- No-Show Prediction Prototype
"""

import re
from pathlib import Path
from datetime import date, datetime
import json
import joblib
import pandas as pd

import database

MODEL_DIR = Path("models")
MODEL_PATH = MODEL_DIR / "selected_model_pipeline.pkl"
CALIBRATED_MODEL_PATH = MODEL_DIR / "calibrated_probability_model.pkl"
METADATA_PATH = MODEL_DIR / "selected_model_info.json"
MEDIANS_PATH = MODEL_DIR / "feature_medians.json"

_model = joblib.load(MODEL_PATH)
_calibrated_model = joblib.load(CALIBRATED_MODEL_PATH)
_metadata = json.loads(METADATA_PATH.read_text())
_feature_medians = json.loads(MEDIANS_PATH.read_text())  # raw training-set medians

RAW_FEATURES = _metadata["feature_columns"]
DECISION_THRESHOLD = float(_metadata["decision_threshold"])

_DEPT_DUMMIES = [c.replace("department_", "") for c in RAW_FEATURES if c.startswith("department_")]
_DIAG_DUMMIES = [c.replace("diagnosis_", "") for c in RAW_FEATURES if c.startswith("diagnosis_")]

DEPARTMENT_OPTIONS = ["Cardiology"] + _DEPT_DUMMIES
DIAGNOSIS_OPTIONS = ["General Checkup"] + _DIAG_DUMMIES
PAYMENT_TYPES = ["Card", "Cash", "Online"]

_FEATURE_LABELS = {
    "age": "Age",
    "waiting_days": "Waiting days (booking to appointment)",
    "previous_appointments": "Number of previous appointments",
    "missed_previous_appointments": "Previously missed appointments",
    "previous_admissions": "Previous hospital admissions",
    "appointment_month": "Appointment month",
    "appointment_dayofweek": "Appointment day of week",
    "missed_ratio": "Missed-appointment ratio",
    "has_missed_before": "Has missed an appointment before",
}


def get_model_accuracy() -> float:
    return _metadata.get("cv_mean_accuracy", 0.0)


def get_model_name() -> str:
    return _metadata.get("selected_model", "Unknown")


# Validation helpers
def is_valid_contact_number(number: str) -> bool:
    """Exactly 10 digits, nothing else (matches the Sri Lankan mobile/landline length)."""
    return bool(re.fullmatch(r"\d{10}", (number or "").strip()))


def normalize_nic(nic: str) -> str:

    return (nic or "").strip().upper()


# Patient lookups (from the database, not the UI)

def get_patient_by_nic(nic: str):
    nic = normalize_nic(nic)
    conn = database.get_connection()
    row = conn.execute("SELECT * FROM patients WHERE nic = ?", (nic,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_next_patient_id() -> str:
    """Return the next available P11001, P11002, ... ID."""
    conn = database.get_connection()
    rows = conn.execute(
        "SELECT patient_id FROM patients WHERE patient_id LIKE 'P%'"
    ).fetchall()
    conn.close()
    nums = []
    for row in rows:
        m = re.fullmatch(r"P(\d+)", row["patient_id"] or "")
        if m:
            nums.append(int(m.group(1)))
    next_num = max([11000, *nums]) + 1
    while True:
        candidate = f"P{next_num}"
        conn = database.get_connection()
        exists = conn.execute("SELECT 1 FROM patients WHERE patient_id = ?", (candidate,)).fetchone()
        conn.close()
        if not exists:
            return candidate
        next_num += 1


def create_patient(nic, full_name, age, gender, contact_number, blood_group, address) -> dict:
    nic = normalize_nic(nic)
    patient_id = get_next_patient_id()
    conn = database.get_connection()
    try:
        conn.execute(
            "INSERT INTO patients (patient_id, nic, full_name, age, gender, contact_number, blood_group, address) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (patient_id, nic, full_name, age, gender, contact_number, blood_group, address),
        )
        conn.commit()
    finally:
        conn.close()
    return {"patient_id": patient_id, "nic": nic}


def update_patient(nic, full_name, age, gender, contact_number, blood_group, address) -> None:
    nic = normalize_nic(nic)
    conn = database.get_connection()
    conn.execute(
        "UPDATE patients SET full_name = ?, age = ?, gender = ?, contact_number = ?, "
        "blood_group = ?, address = ? WHERE nic = ?",
        (full_name, age, gender, contact_number, blood_group, address, nic),
    )
    conn.commit()
    conn.close()


def search_patients(query: str) -> list:
    if not query or not query.strip():
        return []
    conn = database.get_connection()
    like_query = f"%{query.strip().upper()}%"
    rows = conn.execute(
        "SELECT * FROM patients WHERE nic LIKE ? OR full_name LIKE ? ORDER BY full_name LIMIT 25",
        (like_query, like_query),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_patient_admissions(nic: str) -> list:
    nic = normalize_nic(nic)
    conn = database.get_connection()
    rows = conn.execute(
        "SELECT * FROM admissions WHERE patient_nic = ? ORDER BY admission_date DESC", (nic,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _get_patient_history_counts(nic: str) -> dict:
  
    nic = normalize_nic(nic)
    conn = database.get_connection()
    total = conn.execute(
        "SELECT COUNT(*) AS n FROM appointments WHERE patient_nic = ?", (nic,)
    ).fetchone()["n"]
    missed = conn.execute(
        "SELECT COUNT(*) AS n FROM appointments WHERE patient_nic = ? AND status = 'No-Show'", (nic,)
    ).fetchone()["n"]
    admissions = conn.execute(
        "SELECT COUNT(*) AS n FROM admissions WHERE patient_nic = ?", (nic,)
    ).fetchone()["n"]
    conn.close()
    return {
        "previous_appointments": total,
        "missed_previous_appointments": missed,
        "previous_admissions": admissions,
    }


def get_patient_appointment_history(nic: str) -> list:
    nic = normalize_nic(nic)
    conn = database.get_connection()
    rows = conn.execute("""
        SELECT a.*, d.name AS doctor_name FROM appointments a
        LEFT JOIN doctors d ON a.doctor_id = d.doctor_id
        WHERE a.patient_nic = ? ORDER BY a.appointment_date DESC
    """, (nic,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# Doctors & scheduling
def get_doctors_by_department(department: str) -> list:
    conn = database.get_connection()
    rows = conn.execute(
        "SELECT * FROM doctors WHERE department = ? ORDER BY name", (department,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_doctor(doctor_id: int):
    conn = database.get_connection()
    row = conn.execute("SELECT * FROM doctors WHERE doctor_id = ?", (doctor_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def is_doctor_available_on(doctor: dict, appt_date: date) -> bool:
    weekday_name = appt_date.strftime("%A")
    return weekday_name in (doctor["day1"], doctor["day2"])


def get_next_booking_number(doctor_id: int, appt_date: date) -> int:
    conn = database.get_connection()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM appointments WHERE doctor_id = ? AND appointment_date = ? "
        "AND status IN ('Pending', 'Confirmed')",
        (doctor_id, str(appt_date)),
    ).fetchone()
    conn.close()
    return row["n"] + 1


# Feature construction + prediction
def _build_feature_row(inputs: dict) -> pd.DataFrame:
    appt_date = inputs["appointment_date"]
    if isinstance(appt_date, date):
        appointment_month = appt_date.month
        appointment_dayofweek = appt_date.weekday()
    else:
        appointment_month = datetime.now().month
        appointment_dayofweek = datetime.now().weekday()

    booking_date = date.today()
    waiting_days = max((appt_date - booking_date).days, 0) if isinstance(appt_date, date) else 0

    previous_appointments = inputs["previous_appointments"]
    missed_previous_appointments = inputs["missed_previous_appointments"]

    missed_ratio = (
        missed_previous_appointments / previous_appointments
        if previous_appointments > 0 else 0
    )
    has_missed_before = 1 if missed_previous_appointments > 0 else 0

    row = {
        "age": inputs["age"],
        "waiting_days": waiting_days,
        "previous_appointments": previous_appointments,
        "missed_previous_appointments": missed_previous_appointments,
        "previous_admissions": inputs["previous_admissions"],
        "appointment_month": appointment_month,
        "appointment_dayofweek": appointment_dayofweek,
        "missed_ratio": missed_ratio,
        "has_missed_before": has_missed_before,
    }
    for dept in _DEPT_DUMMIES:
        row[f"department_{dept}"] = 1 if inputs["department"] == dept else 0
    for diag in _DIAG_DUMMIES:
        row[f"diagnosis_{diag}"] = 1 if inputs["diagnosis"] == diag else 0

    df_raw_row = pd.DataFrame([row])[RAW_FEATURES]
    return df_raw_row, waiting_days


def predict_no_show_for_patient(nic: str, age: int, gender: str, department: str,
                                diagnosis: str, appointment_date: date) -> dict:

    nic = normalize_nic(nic)
    history = _get_patient_history_counts(nic)
    inputs = {"age": age, "department": department, "diagnosis": diagnosis,
              "appointment_date": appointment_date, **history}

    feature_row, waiting_days = _build_feature_row(inputs)
    raw_probability = float(_model.predict_proba(feature_row)[0][1])
    prediction = int(raw_probability >= DECISION_THRESHOLD)
    probability = float(_calibrated_model.predict_proba(feature_row)[0][1])

    return {
        "prediction": prediction,
        "probability": probability,
        "raw_probability": raw_probability,
        "decision_threshold": DECISION_THRESHOLD,
        "label": "High Risk" if prediction == 1 else "Low Risk",
        # Final, patient-facing wording: "Prediction: Likely to Attend / Likely to No-Show"
        # plus a separate "No-Show Risk: X%" line.
        "prediction_text": "Likely to No-Show" if prediction == 1 else "Likely to Attend",
        "waiting_days": waiting_days,
        "history_used": history,
        "_inputs": inputs,
    }


def _friendly_label(feature: str) -> str:
    if feature in _FEATURE_LABELS:
        return _FEATURE_LABELS[feature]
    if feature.startswith("department_"):
        return f"Department: {feature.replace('department_', '')}"
    if feature.startswith("diagnosis_"):
        return f"Diagnosis: {feature.replace('diagnosis_', '')}"
    return feature


def explain_prediction(inputs: dict, top_n: int = 5) -> list:
    feature_row, _ = _build_feature_row(inputs)
    baseline_probability = float(_model.predict_proba(feature_row)[0][1])

    rows = []
    for feature in RAW_FEATURES:
        altered = feature_row.copy()
        patient_value = feature_row.iloc[0][feature]
        reference_value = _feature_medians.get(feature, altered.iloc[0][feature])
        altered.loc[:, feature] = reference_value
        changed_probability = float(_model.predict_proba(altered)[0][1])
        impact = baseline_probability - changed_probability
        rows.append({
            "feature": feature, "label": _friendly_label(feature),
            "patient_value": patient_value, "reference_value": reference_value, "impact": impact,
        })
    rows.sort(key=lambda r: abs(r["impact"]), reverse=True)
    return rows[:top_n]


# Appointment lifecycle: book (with prediction) -> pay -> confirm
def finalize_booking(patient_nic, doctor_id, department, diagnosis, appointment_date,
                      risk_label, risk_probability, payment_type, payment_amount,
                      entered_by_staff_id) -> dict:

    patient_nic = normalize_nic(patient_nic)
    booking_number = get_next_booking_number(doctor_id, appointment_date)

    conn = database.get_connection()
    cur = conn.execute(
        "INSERT INTO appointments (patient_nic, doctor_id, department, diagnosis, booking_date, "
        "appointment_date, booking_number, status, risk_label, risk_probability, payment_type, "
        "payment_amount, payment_confirmed, entered_by_staff_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'Pending', ?, ?, ?, ?, 1, ?)",
        (patient_nic, doctor_id, department, diagnosis, str(date.today()), str(appointment_date),
         booking_number, risk_label, risk_probability, payment_type, payment_amount,
         entered_by_staff_id),
    )
    conn.commit()
    appointment_id = cur.lastrowid
    conn.close()
    return {"appointment_id": appointment_id, "booking_number": booking_number}


def apply_auto_no_show() -> int:

    conn = database.get_connection()
    cur = conn.execute(
        "UPDATE appointments SET status = 'No-Show' WHERE status = 'Pending' AND appointment_date < ?",
        (str(date.today()),),
    )
    conn.commit()
    updated = cur.rowcount
    conn.close()
    return updated


def get_all_appointments(department=None, sort_order="Newest first", high_risk_only=False, status=None) -> list:
    apply_auto_no_show()
    conn = database.get_connection()
    query = """
        SELECT a.*, c.patient_id, c.full_name, d.name AS doctor_name, s.full_name AS entered_by_name
        FROM appointments a
        JOIN patients c ON a.patient_nic = c.nic
        LEFT JOIN doctors d ON a.doctor_id = d.doctor_id
        LEFT JOIN staff s ON a.entered_by_staff_id = s.staff_id
    """
    conditions, params = [], []
    if department:
        conditions.append("a.department = ?")
        params.append(department)
    if high_risk_only:
        conditions.append("a.risk_label = 'High Risk'")
    if status and status != "All":
        conditions.append("a.status = ?")
        params.append(status)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY a.appointment_date " + ("DESC" if sort_order == "Newest first" else "ASC")

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_appointment_status(appointment_id: int, new_status: str) -> None:
    """Move a pending appointment to a valid lifecycle status."""
    if new_status not in {"Pending", "Confirmed", "Cancelled"}:
        raise ValueError("Invalid appointment status.")
    conn = database.get_connection()
    cur = conn.execute(
        "UPDATE appointments SET status = ? WHERE appointment_id = ? AND status = 'Pending'",
        (new_status, appointment_id),
    )
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise ValueError("Only pending appointments can be confirmed or cancelled.")
