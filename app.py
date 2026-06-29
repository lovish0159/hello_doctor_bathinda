import os
import logging
import google.generativeai as genai
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import psycopg2

app = Flask(__name__)

# Production logging setup for better debugging without exposing errors to users
logging.basicConfig(level=logging.INFO)

# Security check: Ensuring environment variables are present before starting up
DATABASE_URL = os.environ.get("DATABASE_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not DATABASE_URL or not GEMINI_API_KEY:
    logging.critical("CRITICAL ERROR: Environment variables configuration missing!")

# Gemini AI configuration
genai.configure(api_key=GEMINI_API_KEY)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def get_doctor_suggestion(problem):
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = (
            f"Patient ki problem hai: '{problem}'. Civil Hospital ke standard protocols ke hisab se "
            f"kis department/doctor ko dikhana chahiye? Sirf specialization ka naam do (Jaise: Cardiologist, Orthopedic, General Physician)."
        )
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logging.error(f"Gemini API Triage Error: {e}")
        return "General Physician"

@app.route("/", methods=['GET'])
def home():
    # Production Dashboard First Page / Status Check Page
    return "✅ Hello Doctor Bathinda Production Server is 100% Online & Secure!", 200

@app.route("/whatsapp", methods=['POST'])
def whatsapp_bot():
    incoming_msg = request.values.get('Body', '').strip()
    incoming_msg_lower = incoming_msg.lower()
    sender_number = request.values.get('From', '').replace('whatsapp:', '')
    
    resp = MessagingResponse()
    msg = resp.message()
    
    conn = None
    cursor = None
    
    # Standard keywords to reset conversation loops safely
    is_reset_trigger = incoming_msg_lower in ['hi', 'hello', 'menu', 'help', 'sat sri akal', 'restart', 'start']

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Checking if user profile exists securely
        cursor.execute("SELECT full_name, session_step, temp_data FROM patients WHERE phone_number = %s", (sender_number,))
        patient = cursor.fetchone()

        if patient:
            name, step, temp_data = patient[0], patient[1], patient[2]

            # Global fallback: Reset state to IDLE if reset word is typed mid-way
            if is_reset_trigger and name != "Naya Mareez":
                cursor.execute("UPDATE patients SET session_step = 'IDLE', temp_data = NULL WHERE phone_number = %s", (sender_number,))
                conn.commit()
                step = 'IDLE'

            # Step 1: Handle User Registration Flow
            if name == "Naya Mareez":
                real_name = incoming_msg.title()
                cursor.execute("UPDATE patients SET full_name = %s, session_step = 'IDLE' WHERE phone_number = %s", (real_name, sender_number))
                conn.commit()
                msg.body(
                    f"✅ Swagat {real_name} ji!\n\n"
                    "Main Ram, Civil Hospital Bathinda ka AI assistant hoon. Aap kya karna chahte hain?\n\n"
                    "1️⃣ Apni bimari batayein (AI Doctor Suggestion) 🤖\n"
                    "2️⃣ Direct Appointment Book karein 📅\n"
                    "3️⃣ Test ya Ultrasound Book karein 🧪\n\n"
                    "Kripya 1, 2 ya 3 likh kar reply karein."
                )
            
            # Step 2: Handle Gemini Triage Interaction State
            elif step == 'ASKING_PROBLEM':
                doctor_specialization = get_doctor_suggestion(incoming_msg)
                cursor.execute("UPDATE patients SET session_step = 'IDLE' WHERE phone_number = %s", (sender_number,))
                conn.commit()
                msg.body(
                    f"🏥 AI Suggestion: Aapki pareshani ke hisab se aapko *{doctor_specialization}* ko dikhana chahiye.\n\n"
                    "Agar aap appointment book karna chahte hain to Main Menu par jaane ke liye 'Hi' bhejein ya direct booking ke liye '2' likhein."
                )

            # Step 3: Handle Date/Time Processing State
            elif step == 'WAITING_FOR_DATE':
                booking_type = temp_data if temp_data else "General Booking"
                
                cursor.execute(
                    "INSERT INTO appointments (patient_phone, appointment_type, appointment_date) VALUES (%s, %s, %s)", 
                    (sender_number, booking_type, incoming_msg)
                )
                cursor.execute("UPDATE patients SET session_step = 'IDLE', temp_data = NULL WHERE phone_number = %s", (sender_number,))
                conn.commit()
                msg.body(f"✅ Aapki *{booking_type}* successfully save ho gayi hai! 🏥 Hamara hospital staff aapse jald hi sampark karega.")

            # Step 4: Core Router / Main Menu Routing Logic (IDLE State)
            else:
                if incoming_msg == '1':
                    cursor.execute("UPDATE patients SET session_step = 'ASKING_PROBLEM' WHERE phone_number = %s", (sender_number,))
                    conn.commit()
                    msg.body("Kripya apni bimari ya dikkat detail mein likhein (Jaise: Mujhe 2 din se bukhar aur pet dard hai):")
                
                elif incoming_msg == '2':
                    cursor.execute("UPDATE patients SET session_step = 'WAITING_FOR_DATE', temp_data = 'Doctor Appointment' WHERE phone_number = %s", (sender_number,))
                    conn.commit()
                    msg.body("✅ Direct Appointment ke liye Date aur Time likhein (Jaise: 30 June, 10:00 AM):")
                
                elif incoming_msg == '3':
                    cursor.execute("UPDATE patients SET session_step = 'WAITING_FOR_DATE', temp_data = 'Test/Ultrasound' WHERE phone_number = %s", (sender_number,))
                    conn.commit()
                    msg.body("✅ Test ya Ultrasound ke liye Date aur Time likhein (Jaise: 30 June, 11:30 AM):")
                
                else:
                    msg.body(
                        "Main Ram, Civil Hospital Bathinda ka AI assistant hoon. Kripya ek sahi option chunein:\n\n"
                        "1️⃣ Apni bimari batayein (AI Doctor Suggestion) 🤖\n"
                        "2️⃣ Direct Appointment Book karein 📅\n"
                        "3️⃣ Test ya Ultrasound Book karein 🧪"
                    )

        # Step 5: Handling Unknown/First-time Global Entries
        else:
            cursor.execute("INSERT INTO patients (phone_number, full_name, session_step) VALUES (%s, %s, 'IDLE')", (sender_number, "Naya Mareez"))
            conn.commit()
            msg.body(
                "Sat Sri Akal! 🙏 'Hello Doctor Bathinda' mein aapka swagat hai.\n\n"
                "Kripya apni details register karne ke liye apna poora naam likh kar bhejein:"
            )

    except Exception as e:
        if conn:
            conn.rollback()  # Protection against data pipeline breakage
        logging.error(f"Critical Bot Exception: {e}")
        msg.body("Maaf karein, system mein koi takneeki kharabi aa gayi hai. Kripya thodi der baad koshish karein.")
        
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return str(resp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
