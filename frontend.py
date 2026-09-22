"""
Medi Vision -- No-Show Prediction Prototype

"""

import streamlit as st
from datetime import date

import auth
import backend
import database

st.set_page_config(page_title="Medi Vision", page_icon="🏥", layout="wide")

database.initialize_database()
database.seed_doctors()
database.import_bulk_dataset()


def load_css():
    with open("style.css") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


load_css()

# Session state
defaults = {
    "logged_in_staff": None,
    "active_tab": "New Appointment",
    "selected_client_nic": None,
    "booking_stage": "input",     
    "booking_result": None,
    "booking_context": None,
    "signup_reset": 0,
    "create_client_reset": 0,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ---------------------------------------------------------------------------
# LOGIN / SIGN UP SCREEN
# ---------------------------------------------------------------------------
if st.session_state.logged_in_staff is None:
    st.title("🏥 Medi Vision")
    login_tab, signup_tab = st.tabs(["Log In", "Sign Up"])

    with login_tab:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in", use_container_width=True)
        if submitted:
            staff = auth.login(username, password)
            if staff:
                st.session_state.logged_in_staff = staff
                st.rerun()
            else:
                st.error("Invalid username or password.")

    with signup_tab:
        st.caption("Create a staff account to use the system.")
        rk = st.session_state.signup_reset  # reset key -- bumped after success to clear the form
        with st.form(f"signup_form_{rk}"):
            su_full_name = st.text_input("Full Name", key=f"su_name_{rk}")
            su_role = st.selectbox("Role", ["Front Desk Staff", "Nurse", "Administrator"], key=f"su_role_{rk}")
            su_username = st.text_input("Choose a Username", key=f"su_user_{rk}")
            su_password = st.text_input("Choose a Password", type="password", key=f"su_pass_{rk}")
            su_password_confirm = st.text_input("Confirm Password", type="password", key=f"su_pass2_{rk}")
            su_submitted = st.form_submit_button("Create Account", use_container_width=True)

        if su_submitted:
            if su_password != su_password_confirm:
                st.error("Passwords do not match.")
            else:
                success, message = auth.signup(su_username, su_password, su_full_name, su_role)
                if success:
                    st.success(message + " Switch to the 'Log In' tab to continue.")
                    st.session_state.signup_reset += 1
                    st.rerun()
                else:
                    st.error(message)

    st.stop()

staff = st.session_state.logged_in_staff

# SIDEBAR NAVIGATION
with st.sidebar:
    st.markdown("### 🏥 Medi Vision")
    st.divider()
    tabs = ["New Appointment", "Appointment List", "Create Client", "Client Search", "Profile"]
    icons = {"New Appointment": "📝", "Appointment List": "📋", "Create Client": "👤➕",
              "Client Search": "🔍", "Profile": "👤"}
    for tab_name in tabs:
        if st.button(f"{icons[tab_name]}  {tab_name}", key=f"nav_{tab_name}", use_container_width=True):
            st.session_state.active_tab = tab_name
            if tab_name == "New Appointment":
                st.session_state.booking_stage = "input"
            st.rerun()
    st.divider()
    st.caption(f"Logged in as **{staff['full_name']}**")
    if st.button("Log out", use_container_width=True):
        st.session_state.logged_in_staff = None
        st.rerun()

active_tab = st.session_state.active_tab

# TAB: New Appointment (multi-step: input -> result -> payment -> done)
if active_tab == "New Appointment":
    st.title("Book New Appointment")
    stage = st.session_state.booking_stage

    # ---- STAGE 1: patient / doctor / date details ----
    if stage == "input":
        nic = st.text_input("NIC Number", placeholder="e.g. 991234567V", key="new_appt_nic")
        found_client = backend.get_client_by_nic(nic) if nic else None

        if nic:
            if found_client:
                st.success(f"Found: {found_client['full_name']}, Age {found_client['age']}, {found_client['gender']}")
                st.markdown("#### Client Details")
                col_a, col_b, col_c = st.columns(3)
                col_a.metric("Patient ID", found_client["patient_id"])
                col_b.metric("Age", found_client["age"])
                col_c.metric("Gender", found_client["gender"])
                st.caption("Age and Gender come from the client's record and cannot be changed here "
                           "-- update them from Client Search \u2192 Edit Details instead.")
            else:
                st.warning("No client found with this NIC. Register them in 'Create Client' first.")

        department = st.selectbox("Department", backend.DEPARTMENT_OPTIONS, key="new_appt_dept")
        doctors = backend.get_doctors_by_department(department)
        doctor_labels = {f"{d['name']} \u2014 {d['day1']}/{d['day2']}, {d['time_slot']}": d for d in doctors}
        doctor_choice = st.selectbox("Doctor", list(doctor_labels.keys()), key="new_appt_doctor") if doctor_labels else None
        selected_doctor = doctor_labels.get(doctor_choice) if doctor_choice else None

        diagnosis = st.selectbox("Diagnosis", backend.DIAGNOSIS_OPTIONS, key="new_appt_diag")
        appointment_date = st.date_input("Appointment date", value=date.today(), min_value=date.today(),
                                          key="new_appt_date")

        date_ok = True
        if selected_doctor and appointment_date:
            date_ok = backend.is_doctor_available_on(selected_doctor, appointment_date)
            if not date_ok:
                st.error(f"{selected_doctor['name']} only sees patients on "
                         f"**{selected_doctor['day1']}** and **{selected_doctor['day2']}** "
                         f"({selected_doctor['time_slot']}). Please pick a matching date.")
            else:
                st.info(f"Time slot: **{selected_doctor['time_slot']}** on {appointment_date.strftime('%A, %d %b %Y')}")

        st.caption("📊 Waiting days, previous appointments, missed appointments, and previous "
                   "admissions are fetched automatically from this patient's history.")

        can_predict = bool(nic and found_client and selected_doctor and date_ok)
        if st.button("🔮 Predict & Continue", use_container_width=True, disabled=not can_predict):
            result = backend.predict_no_show_for_client(
                nic=nic, age=found_client["age"], gender=found_client["gender"],
                department=department, diagnosis=diagnosis, appointment_date=appointment_date,
            )
            st.session_state.booking_result = result
            st.session_state.booking_context = {
                "nic": nic, "doctor_id": selected_doctor["doctor_id"], "doctor_name": selected_doctor["name"],
                "department": department, "diagnosis": diagnosis, "appointment_date": appointment_date,
            }
            st.session_state.booking_stage = "result"
            st.rerun()

    # ---- STAGE 2: show prediction + explanation, then proceed to payment ----
    elif stage == "result":
        result = st.session_state.booking_result
        ctx = st.session_state.booking_context

        st.subheader(f"{ctx['doctor_name']} \u2014 {ctx['department']}")
        st.caption(f"{ctx['appointment_date'].strftime('%A, %d %b %Y')}")

        if result["prediction"] == 1:
            st.error(f"⚠️ **Prediction: {result['prediction_text']}** \u2014 No-Show Risk: **{result['probability']:.0%}**")
        else:
            st.success(f"✅ **Prediction: {result['prediction_text']}** \u2014 No-Show Risk: **{result['probability']:.0%}**")
        st.caption(
            "The class decision uses the fixed 0.39 threshold selected from training data. "
            "The displayed risk is the validation-calibrated probability."
        )

        h = result["history_used"]
        st.caption(f"Auto-fetched history: {h['previous_appointments']} previous appointments, "
                   f"{h['missed_previous_appointments']} missed, {h['previous_admissions']} admissions, "
                   f"{result['waiting_days']} waiting days.")

        with st.expander("🔍 Why this prediction? (Explainable AI)", expanded=True):
            st.caption(
                "Each factor is compared with its training-set median while other values remain fixed. "
                "These values describe model behaviour and do not prove causation."
            )
            explanation = backend.explain_prediction(result["_inputs"])
            for factor in explanation:
                impact = factor["impact"]
                if abs(impact) < 0.005:
                    continue
                icon = "🔴" if impact > 0 else "🟢"
                direction = "increased" if impact > 0 else "decreased"
                st.write(f"{icon} **{factor['label']}** — {direction} risk by **{abs(impact):.1%}**")
                st.progress(min(abs(impact) * 4, 1.0))

        col1, col2 = st.columns(2)
        if col1.button("💳 Proceed to Payment", use_container_width=True):
            st.session_state.booking_stage = "payment"
            st.rerun()
        if col2.button("⬅️ Start Over", use_container_width=True):
            st.session_state.booking_stage = "input"
            st.rerun()

    # ---- STAGE 3: payment ----
    elif stage == "payment":
        ctx = st.session_state.booking_context
        st.subheader("Payment")
        st.caption(f"{ctx['doctor_name']} \u2014 {ctx['department']} \u2014 {ctx['appointment_date'].strftime('%d %b %Y')}")

        with st.form("payment_form"):
            payment_type = st.selectbox("Payment Type", backend.PAYMENT_TYPES)
            amount = st.number_input("Amount (LKR)", min_value=0.0, value=2000.0, step=100.0)
            pay_submitted = st.form_submit_button("✅ Confirm Payment", use_container_width=True)

        if pay_submitted:
            result = st.session_state.booking_result
            booking = backend.finalize_booking(
                client_nic=ctx["nic"], doctor_id=ctx["doctor_id"], department=ctx["department"],
                diagnosis=ctx["diagnosis"], appointment_date=ctx["appointment_date"],
                risk_label=result["label"], risk_probability=result["probability"],
                payment_type=payment_type, payment_amount=amount, entered_by_staff_id=staff["staff_id"],
            )
            st.session_state.booking_confirmation = booking
            st.session_state.booking_stage = "done"
            st.rerun()

    # ---- STAGE 4: done -- show booking number, ready for the next booking ----
    elif stage == "done":
        booking = st.session_state.booking_confirmation
        ctx = st.session_state.booking_context
        st.success("✅ Appointment successfully booked!")
        st.metric("Your Booking Number", booking["booking_number"])
        st.caption(f"{ctx['doctor_name']} \u2014 {ctx['appointment_date'].strftime('%A, %d %b %Y')}. "
                   "The appointment is Pending until confirmed on the day, or it will automatically "
                   "be marked No-Show once the date passes unconfirmed.")

        if st.button("📝 Book Another Appointment", use_container_width=True):
            st.session_state.booking_stage = "input"
            st.session_state.booking_result = None
            st.session_state.booking_context = None
            st.rerun()


# TAB: Appointment List
elif active_tab == "Appointment List":
    st.title("Appointment List")
    updated = backend.apply_auto_no_show()
    if updated:
        st.caption(f"{updated} past-due pending appointment(s) automatically marked No-Show.")

    col_a, col_b, col_c, col_d = st.columns([2, 1, 1, 1])
    with col_a:
        dept_filter = st.selectbox("Department", ["All"] + backend.DEPARTMENT_OPTIONS)
    with col_b:
        status_filter = st.selectbox("Status", ["All", "Pending", "Confirmed", "Cancelled", "No-Show"])
    with col_c:
        sort_order = st.selectbox("Sort by date", ["Newest first", "Oldest first"])
    with col_d:
        high_risk_only = st.checkbox("High risk only")

    appointments = backend.get_all_appointments(
        department=None if dept_filter == "All" else dept_filter,
        sort_order=sort_order,
        high_risk_only=high_risk_only,
        status=status_filter,
    )

    st.caption(f"{len(appointments)} appointment(s)")
    if appointments:
        header = st.columns([2.3, 1.8, 1.6, 1.5, 1.5, 1.4, 1, 1, 1])
        for c, label in zip(header, ["Patient", "Doctor", "Department", "Appointment", "Date",
                                     "Status", "Confirm", "Cancel", "History"]):
            c.markdown(f"**{label}**")

        for appt in appointments:
            cols = st.columns([2.3, 1.8, 1.6, 1.5, 1.5, 1.4, 1, 1, 1])
            cols[0].markdown(f"**{appt['full_name']}**\n\n`{appt['patient_id']}`")
            cols[1].write(appt["doctor_name"] or "—")
            cols[2].write(appt["department"] or "—")
            cols[3].write(f"#{appt['booking_number'] or '—'}")
            # The existing model stores the doctor's fixed time slot rather than
            # a separate appointment-time field.
            doctor = backend.get_doctor(appt["doctor_id"]) if appt["doctor_id"] else None
            cols[3].caption(doctor["time_slot"] if doctor else "Time not assigned")
            cols[4].write(appt["appointment_date"])

            status = appt["status"]
            status_icon = {"Pending": "🕓", "Confirmed": "✅", "Cancelled": "❌", "No-Show": "⛔"}.get(status, "")
            risk_icon = " 🔺" if appt["risk_label"] == "High Risk" else ""
            cols[5].write(f"{status_icon} {status}{risk_icon}")

            if cols[6].button("Confirm", key=f"conf_{appt['appointment_id']}",
                              disabled=status != "Pending"):
                backend.update_appointment_status(appt["appointment_id"], "Confirmed")
                st.rerun()
            if cols[7].button("Cancel", key=f"canc_{appt['appointment_id']}",
                              disabled=status != "Pending"):
                backend.update_appointment_status(appt["appointment_id"], "Cancelled")
                st.rerun()
            if cols[8].button("History", key=f"hist_{appt['appointment_id']}"):
                st.session_state.selected_client_nic = appt["client_nic"]
                st.session_state.active_tab = "Client Search"
                st.rerun()
    else:
        st.info("No appointments match the selected filters.")

# TAB: Create Client
elif active_tab == "Create Client":
    st.title("Register New Client")
    rk = st.session_state.create_client_reset

    with st.form(f"create_client_form_{rk}"):
        col1, col2 = st.columns(2)
        with col1:
            nic = st.text_input("NIC Number", key=f"cc_nic_{rk}")
            full_name = st.text_input("Full Name", key=f"cc_name_{rk}")
            age = st.number_input("Age", min_value=0, max_value=120, value=30, key=f"cc_age_{rk}")
        with col2:
            gender = st.selectbox("Gender", ["Male", "Female"], key=f"cc_gender_{rk}")
            contact_number = st.text_input("Contact Number (10 digits)", key=f"cc_contact_{rk}")
            blood_group = st.selectbox("Blood Group", ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"],
                                        key=f"cc_blood_{rk}")
        address = st.text_area("Address", key=f"cc_address_{rk}")
        submitted = st.form_submit_button("✅ Save Client Record", use_container_width=True)

    if submitted:
        if not nic.strip() or not full_name.strip():
            st.error("NIC and Full Name are required.")
        elif not backend.is_valid_contact_number(contact_number):
            st.error("Contact Number must be exactly 10 digits.")
        elif backend.get_client_by_nic(nic):
            st.error("A client with this NIC already exists.")
        else:
            try:
                created = backend.create_client(nic, full_name, age, gender, contact_number, blood_group, address)
                st.success(f"Client '{full_name}' registered successfully with Patient ID {created['patient_id']}.")
            except Exception as exc:
                if "UNIQUE" in str(exc).upper():
                    st.error("That NIC or Patient ID already exists. Please use a different NIC.")
                else:
                    st.error(f"Could not create the client: {exc}")
                    st.stop()
            st.session_state.create_client_reset += 1
            st.rerun()

# TAB: Client Search
elif active_tab == "Client Search":
    st.title("Client Search")
    search_query = st.text_input("Search by NIC or Name", placeholder="e.g. 991234567V or Randika")

    if search_query:
        results = backend.search_clients(search_query)
        if not results:
            st.warning("No matching clients found.")
        else:
            st.caption(f"{len(results)} match(es) found")
            for r in results:
                if st.button(f"{r['full_name']}  ·  NIC: {r['nic']}", key=f"select_{r['nic']}"):
                    st.session_state.selected_client_nic = r["nic"]
                    st.rerun()

    st.divider()
    selected_nic = st.session_state.selected_client_nic
    if not selected_nic:
        st.info("Search and select a client above, or click the 🕘 icon from the Appointment List.")
    else:
        client = backend.get_client_by_nic(selected_nic)
        if not client:
            st.warning("Selected client no longer exists.")
        else:
            st.subheader(client["full_name"])
            d1, d2, d3 = st.columns(3)
            d1.text_input("Patient ID", value=client["patient_id"], disabled=True)
            d2.text_input("NIC", value=client["nic"], disabled=True)
            d3.text_input("Age", value=str(client["age"]), disabled=True)
            st.caption(f"Gender: {client['gender']} · Patient ID is a permanent identifier and cannot be edited.")

            history_tab, admissions_tab, edit_tab = st.tabs(
                ["📅 Appointment History", "🏥 Admission Records", "✏️ Edit Details"]
            )

            with history_tab:
                history = backend.get_client_appointment_history(selected_nic)
                total = len(history)
                no_shows = sum(1 for h in history if h["status"] == "No-Show")
                attendance_rate = ((total - no_shows) / total * 100) if total else 0

                c1, c2, c3 = st.columns(3)
                c1.metric("Total Visits", total)
                c2.metric("No-Shows", no_shows)
                c3.metric("Attendance Rate", f"{attendance_rate:.0f}%")

                st.divider()
                if not history:
                    st.caption("No appointment history yet.")
                for h in history:
                    status_icon = {"Pending": "🕓", "Confirmed": "✅", "Cancelled": "❌", "No-Show": "⛔"}.get(h["status"], "")
                    st.write(f"**{h['appointment_date']}** · {h['department']} "
                             f"({h.get('doctor_name') or 'unassigned'}) — {status_icon} {h['status']}")

            with admissions_tab:
                admissions = backend.get_client_admissions(selected_nic)
                if not admissions:
                    st.caption("No admission records yet.")
                for a in admissions:
                    st.write(f"**{a['admission_date']}** · {a['department'] or '—'}")
                    if a["notes"]:
                        st.caption(a["notes"])

            with edit_tab:
                with st.form("edit_client_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        e_full_name = st.text_input("Full Name", value=client["full_name"])
                        e_age = st.number_input("Age", min_value=0, max_value=120, value=client["age"])
                    with col2:
                        e_gender = st.selectbox("Gender", ["Male", "Female"],
                                                 index=0 if client["gender"] == "Male" else 1)
                        e_contact = st.text_input("Contact Number (10 digits)", value=client["contact_number"] or "")
                    blood_group_options = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
                    e_blood_group = st.selectbox(
                        "Blood Group", blood_group_options,
                        index=blood_group_options.index(client["blood_group"])
                        if client["blood_group"] in blood_group_options else 0
                    )
                    e_address = st.text_area("Address", value=client["address"] or "")
                    e_submitted = st.form_submit_button("💾 Save Changes", use_container_width=True)

                if e_submitted:
                    if e_contact and not backend.is_valid_contact_number(e_contact):
                        st.error("Contact Number must be exactly 10 digits.")
                    else:
                        backend.update_client(selected_nic, e_full_name, e_age, e_gender, e_contact,
                                               e_blood_group, e_address)
                        st.success("Client details updated.")
                        st.rerun()

# TAB: Profile
elif active_tab == "Profile":
    st.title("Profile")
    initials = "".join([p[0] for p in staff["full_name"].split()[:2]]).upper()
    st.markdown(f"### {initials}")
    st.subheader(staff["full_name"])
    st.caption(f"{staff['role']} · Staff ID: {staff['staff_id']}")
    st.info("📁 All appointments you create or cancel are logged under this profile.")
    if st.button("Log Out"):
        st.session_state.logged_in_staff = None
        st.rerun()
