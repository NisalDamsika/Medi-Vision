# SmartCare Hospital No-Show Prediction App

## Final model alignment

This version is aligned with the final Task 03 to Task 07 workflow.

- Final model is Random Forest.
- The model uses 24 input features.
- `long_wait_flag` is not used.
- The class decision uses the fixed threshold of 0.39.
- The displayed risk uses a sigmoid-calibrated probability model fitted on validation data only.
- The local explanation uses one-feature-at-a-time sensitivity against raw training-set medians.
- Explanation values describe model behaviour and do not prove causation.

## Bug fix in this version

**Fixed:** booking a new appointment for an existing patient would fail
("No patient found") if the NIC was typed or pasted with a trailing space,
a leading space, or a lowercase letter (e.g. `v` instead of `V`) --
the lookup was an exact string match against the database, so a NIC that
looked identical on screen could silently fail to match. NIC values are
now normalized (whitespace trimmed, uppercased) everywhere -- on lookup,
creation, update, search, and booking -- so the same patient is always
found regardless of how the NIC was typed.

## What's new in this version

1. **Prediction wording changed** -- now shown as two clear lines:
   `Prediction: Likely to Attend / Likely to No-Show` and `No-Show Risk: XX%`.
2. **Forms auto-clear after successful submission** (Sign Up, Create Patient).
3. **Full dataset loaded into the database** -- all 1000 rows of
   `smartcare_ai_dataset_1000.csv` are bulk-imported as real patients with
   their historical appointment (and admission) records the first time you
   run `database.py`. This is required, not optional -- the app will not
   start meaningfully without it.
4. **Age and Gender are read-only when booking** an appointment -- they're
   pulled from the patient's record. To change them, use
   Patient Search → Edit Details instead.
5. **7 departments x 4 doctors = 28 doctors**, each with a fixed 2-day
   weekly schedule and one time slot (e.g. "Dr. Nimal Perera -- Monday,
   Thursday, 11:00 AM - 2:00 PM"). Booking now requires picking a doctor,
   and the appointment date must fall on one of that doctor's working days.
6. **Booking numbers** -- every confirmed booking gets a queue position
   (how many bookings already exist for that doctor on that date).
7. **Payment step** -- after the AI prediction is shown, staff proceed to a
   payment screen (Card / Cash / Online + amount) before the booking is
   actually saved. Only paid bookings are written to the database.
8. **Booking lifecycle** -- a new appointment is `Pending` until staff
   confirm the patient attended, or it is cancelled. If the appointment
   date passes with no confirmation, it is **automatically marked
   No-Show** the next time any screen loads the appointment list.
9. **No past-dated bookings** -- the date picker will not allow selecting
   a date before today.
10. **Contact number validation** -- Create Patient and Edit Details both
    require exactly 10 digits.

## Patient identity and appointment UI updates

- Every patient has a permanent `patient_id` copied exactly from the source dataset (`P10001` ... `P11000` in the supplied 1000-row data).
- `patient_id` is unique and protected against database updates after creation. New patients receive the next available sequential ID starting at `P11001`.
- NIC remains a database primary key and is normalized before lookup/creation; the bulk importer also checks generated NICs for collisions.
- Patient Details, appointment rows, appointment history navigation, and the prediction result use the same database-backed Patient ID/patient record.
- Appointment List now provides Patient, Doctor, Department, Appointment/time slot, Date, Status, Confirm, Cancel, and History columns plus a Status filter for All/Pending/Confirmed/Cancelled (and the existing No-Show state).
- The Predict & Continue result shows Doctor Name/Details together with Patient Name and Patient ID.

The supplied `smartcare_ai_dataset_1000.csv` is the source data used by the demo; the original Patient IDs are never replaced during import.

## Setup

```bash
python -m pip install -r requirements.txt
python database.py          # creates smartcare.db, seeds 28 doctors,
                             # bulk-imports all 1000 dataset rows (required)
python -m streamlit run frontend.py
```

Use the **Sign Up** tab on first launch to create your own staff login.

## Files

```
frontend.py    -> UI only (Streamlit) -- login/signup, 5 tabs
backend.py     -> DB queries, doctor scheduling, booking lifecycle,
                  payment handling, feature construction, prediction
database.py    -> SQLite schema, 28-doctor seed, full-dataset bulk import
auth.py        -> password hashing + login check
style.css      -> sidebar theme
models/        -> selected_model_pipeline.pkl,
                  calibrated_probability_model.pkl,
                  selected_model_info.json, feature_medians.json
smartcare_ai_dataset_1000.csv -> source data for the bulk import (required
                  the first time database.py runs)
```

## Data note

Synthetic NIC numbers and patient names are generated deterministically
from each row's `patient_id` (the raw dataset has no real names or NIC
numbers) -- re-running `database.py` on a fresh `smartcare.db` always
produces the same 1000 patients, so the demo is reproducible.
