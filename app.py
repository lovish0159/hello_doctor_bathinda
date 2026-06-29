import os
import logging
import google.generativeai as genai
from flask import Flask, request, render_template_string
from twilio.twiml.messaging_response import MessagingResponse
import psycopg2

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

DATABASE_URL = os.environ.get("DATABASE_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not DATABASE_URL or not GEMINI_API_KEY:
    logging.critical("CRITICAL ERROR: Environment variables missing!")

genai.configure(api_key=GEMINI_API_KEY)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def get_doctor_suggestion(problem):
    try:
        model = genai.GenerativeModel('gemini-3.1-flash-lite')
        prompt = (
            f"You are a smart hospital assistant. The patient says: '{problem}'. "
            f"Which specialist doctor should they consult? "
            f"Give ONLY the main English specialization word (e.g., Cardiologist, Ophthalmologist, Orthopedic). No other text."
        )
        response = model.generate_content(prompt)
        return response.text.strip() if response.text else "General Physician"
    except Exception as e:
        logging.error(f"Gemini API Error: {e}")
        return "General Physician"

def get_main_menu(user_name):
    return (
        f"Sat Sri Akal {user_name} ji! 🙏\n\n"
        "Aap kya karna chahte hain?\n"
        "1️⃣ Apni bimari batayein 🤖\n"
        "2️⃣ Direct Appointment Book karein 📅\n"
        "3️⃣ Test ya Ultrasound Book karein 🧪\n"
        "4️⃣ Help / Naam badlein ⚙️\n\n"
        "Kripya 1, 2, 3 ya 4 likh kar reply karein."
    )

# ----------------- WEB DASHBOARD (FRONTEND PAGE) -----------------
HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Hospital Admin - Doctors</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="container mt-5">
    <h2 class="mb-4">🏥 Hospital Dashboard - Add Doctors</h2>
    
    <div class="card mb-4 p-4 shadow-sm">
        <form method="POST" action="/">
            <div class="row">
                <div class="col-md-6 mb-3"><label>Doctor Name</label><input type="text" name="name" class="form-control" required></div>
                <div class="col-md-6 mb-3"><label>Specialization (e.g., Cardiologist)</label><input type="text" name="specialization" class="form-control" required></div>
                <div class="col-md-6 mb-3"><label>Hospital Name</label><input type="text" name="hospital_name" class="form-control" required></div>
                <div class="col-md-6 mb-3"><label>Mobile Number</label><input type="text" name="mobile_number" class="form-control" required></div>
                <div class="col-md-6 mb-3"><label>Address</label><input type="text" name="address" class="form-control" required></div>
                <div class="col-md-6 mb-3"><label>Timing (e.g., 10 AM - 2 PM)</label><input type="text" name="timing" class="form-control" required></div>
            </div>
            <button type="submit" class="btn btn-primary w-100">Add Doctor to System</button>
        </form>
    </div>

    <h3>👨‍⚕️ Available Doctors List</h3>
    <table class="table table-bordered table-striped mt-3">
        <thead class="table-dark">
            <tr>
                <th>ID</th><th>Name</th><th>Specialization</th><th>Hospital</th><th>Mobile</th><th>Timing</th>
            </tr>
        </thead>
        <tbody>
            {% for doc in doctors %}
            <tr>
                <td>{{ doc[0] }}</td><td>{{ doc[1] }}</td><td>{{ doc[2] }}</td><td>{{ doc[3] }}</td><td>{{ doc[4] }}</td><td>{{ doc[6] }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</body>
</html>
"""

@app.route("/", methods=['GET', 'POST'])
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Jab admin naya doctor add kare
    if request.method == 'POST':
        cursor.execute("""
            INSERT INTO doctors (name, specialization, hospital_name, mobile_number, address, timing)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (request.form['name'], request.form['specialization'], request.form['hospital_name'], 
              request.form['mobile_number'], request.form['address'], request.form['timing']))
        conn.commit()

    # Doctors ki list show karne ke liye
    cursor.execute("SELECT * FROM doctors ORDER BY id DESC")
    doctors_list = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return render_template_string(HTML_PAGE, doctors=doctors_list)

# ----------------- WHATSAPP BOT LOGIC -----------------
@app.route("/whatsapp", methods=['POST'])
def whatsapp_bot():
    incoming_msg = request.values.get('Body', '').strip()
    incoming_msg_lower = incoming_msg.lower()
    sender_number = request.values.get('From', '').replace('whatsapp:', '')
    
    resp = MessagingResponse()
    msg = resp.message()
    
    conn = None
    cursor = None
    
    is_reset_trigger = incoming_msg_lower in ['0', 'hi', 'hello', 'menu', 'help', 'sat sri akal', 'restart', 'start']

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT full_name, session_step, temp_data FROM patients WHERE phone_number = %s", (sender_number,))
        patient = cursor.fetchone()

        if patient:
            name, step, temp_data = patient[0], patient[1], patient[2]

            if is_reset_trigger and name != "Naya Mareez":
                cursor.execute("UPDATE patients SET session_step = 'IDLE', temp_data = NULL WHERE phone_number = %s", (sender_number,))
                conn.commit()
                step = 'IDLE'
                msg.body(get_main_menu(name))
                return str(resp)

            # 1. Registration
            if name == "Naya Mareez":
                real_name = incoming_msg.title()
                cursor.execute("UPDATE patients SET full_name = %s, session_step = 'IDLE' WHERE phone_number = %s", (real_name, sender_number))
                conn.commit()
                msg.body(f"✅ Aapki profile successfully ban gayi hai.\n\n{get_main_menu(real_name)}")
            
            # 2. AI Doctor Suggestion + Specific Filtering
            elif step == 'ASKING_PROBLEM':
                spec_suggestion = get_doctor_suggestion(incoming_msg)
                
                # Check if we have this specialist in our database
                cursor.execute("SELECT id, name, specialization, timing FROM doctors WHERE specialization ILIKE %s", (f"%{spec_suggestion}%",))
                matching_doctors = cursor.fetchall()
                
                if matching_doctors:
                    doc_list = "\n".join([f"{d[0]}️⃣ {d[1]} ({d[3]})" for d in matching_doctors])
                    cursor.execute("UPDATE patients SET session_step = 'CHOOSING_DOCTOR' WHERE phone_number = %s", (sender_number,))
                    conn.commit()
                    msg.body(
                        f"🏥 AI Suggestion: Aapko *{spec_suggestion}* ko dikhana chahiye.\n\n"
                        f"Hamare paas is bimari ke yeh experts hain:\n{doc_list}\n\n"
                        "Appointment book karne ke liye Doctor ka Number (jaise '1') bhejein. Ya '0' bhej kar Menu par jayein."
                    )
                else:
                    cursor.execute("UPDATE patients SET session_step = 'IDLE' WHERE phone_number = %s", (sender_number,))
                    conn.commit()
                    msg.body(
                        f"🏥 AI Suggestion: Aapko *{spec_suggestion}* ko dikhana chahiye.\n\n"
                        "Maaf karein, is specialization ke doctor filhal system mein nahi hain. Kripya OPD aakar sampark karein. '0' daba kar menu par jayein."
                    )

            # 3. Choosing a specific Doctor from List
            elif step == 'CHOOSING_DOCTOR':
                cursor.execute("SELECT name, timing FROM doctors WHERE id::text = %s", (incoming_msg,))
                selected_doc = cursor.fetchone()
                
                if selected_doc:
                    doc_name = f"{selected_doc[0]}"
                    cursor.execute("UPDATE patients SET session_step = 'WAITING_FOR_DATE', temp_data = %s WHERE phone_number = %s", (doc_name, sender_number))
                    conn.commit()
                    msg.body(f"✅ Aapne {doc_name} ko chuna hai (Time: {selected_doc[1]}).\n\nKripya kis Date aur Time par aana hai woh likhein (Jaise: 30 June, 10:00 AM):")
                else:
                    msg.body("❌ Kripya list mein se ek sahi number chunein, ya Menu ke liye '0' bhejein.")

            # 4. Appointment/Test Booking Final
            elif step == 'WAITING_FOR_DATE':
                booking_type = temp_data if temp_data else "Test/Ultrasound"
                cursor.execute(
                    "INSERT INTO appointments (patient_phone, appointment_type, appointment_date) VALUES (%s, %s, %s)", 
                    (sender_number, booking_type, incoming_msg)
                )
                cursor.execute("UPDATE patients SET session_step = 'IDLE', temp_data = NULL WHERE phone_number = %s", (sender_number,))
                conn.commit()
                msg.body(f"✅ Aapki booking '{booking_type}' ke liye successfully save ho gayi hai! 🏥 Hamara staff aapse jald hi sampark karega.")

            # 5. Help Menu / Name Change
            elif step == 'HELP_MENU':
                if incoming_msg == '1':
                    cursor.execute("UPDATE patients SET session_step = 'CHANGING_NAME' WHERE phone_number = %s", (sender_number,))
                    conn.commit()
                    msg.body("Kripya apna naya naam likh kar bhejein:")
                else:
                    msg.body("Kripya sahi option chunein:\n1️⃣ Naam Badlein\n0️⃣ Main Menu")

            elif step == 'CHANGING_NAME':
                new_name = incoming_msg.title()
                cursor.execute("UPDATE patients SET full_name = %s, session_step = 'IDLE' WHERE phone_number = %s", (new_name, sender_number))
                conn.commit()
                msg.body(f"✅ Aapka naam update hokar '{new_name}' ho gaya hai.\n\n{get_main_menu(new_name)}")

            # Main Menu Logic (IDLE State)
            else:
                if incoming_msg == '1':
                    cursor.execute("UPDATE patients SET session_step = 'ASKING_PROBLEM' WHERE phone_number = %s", (sender_number,))
                    conn.commit()
                    msg.body("Kripya apni bimari ya dikkat detail mein likhein (Jaise: Mujhe aankhon mein dard aur jalan hai):")
                
                elif incoming_msg == '2':
                    # SHOW ALL DOCTORS LIST
                    cursor.execute("SELECT id, name, specialization FROM doctors")
                    all_docs = cursor.fetchall()
                    if all_docs:
                        doc_list = "\n".join([f"{d[0]}️⃣ {d[1]} ({d[2]})" for d in all_docs])
                        cursor.execute("UPDATE patients SET session_step = 'CHOOSING_DOCTOR' WHERE phone_number = %s", (sender_number,))
                        conn.commit()
                        msg.body(f"🏥 Hamare Doctors ki List:\n\n{doc_list}\n\nAppointment ke liye Doctor ka Number (jaise '1') bhejein:")
                    else:
                        msg.body("Maaf karein, abhi system mein doctors add nahi hue hain. Kripya OPD mein sampark karein.")
                        
                elif incoming_msg == '3':
                    cursor.execute("UPDATE patients SET session_step = 'WAITING_FOR_DATE', temp_data = 'Test/Ultrasound' WHERE phone_number = %s", (sender_number,))
                    conn.commit()
                    msg.body("✅ Test ya Ultrasound ke liye Date aur Time likhein (Jaise: 30 June, 11:30 AM):")
                
                elif incoming_msg == '4':
                    cursor.execute("UPDATE patients SET session_step = 'HELP_MENU' WHERE phone_number = %s", (sender_number,))
                    conn.commit()
                    msg.body("⚙️ Help Menu:\n1️⃣ Apna Naam Badlein\n0️⃣ Main Menu par wapas jayein")
                
                else:
                    msg.body(get_main_menu(name))

        # First-time user
        else:
            cursor.execute("INSERT INTO patients (phone_number, full_name, session_step) VALUES (%s, %s, 'IDLE')", (sender_number, "Naya Mareez"))
            conn.commit()
            msg.body(
                "Sat Sri Akal! 🙏 'Hello Doctor Bathinda' mein aapka swagat hai.\n\n"
                "Kripya apni details register karne ke liye apna poora naam likh kar bhejein:"
            )

    except Exception as e:
        if conn:
            conn.rollback() 
        logging.error(f"Critical Bot Exception: {e}")
        msg.body("Maaf karein, system mein koi takneeki kharabi aa gayi hai. Kripya thodi der baad koshish karein ya '0' bhejein.")
        
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return str(resp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
