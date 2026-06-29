import os
import logging
import google.generativeai as genai
from flask import Flask, request
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
        # Gemini ka naya Flash Lite 3.1 version yahan update kiya gaya hai
        model = genai.GenerativeModel('gemini-3.1-flash-lite')
        prompt = (
            f"You are a smart hospital assistant. The patient says: '{problem}'. "
            f"Based on this medical issue, which specialist doctor should they consult? "
            f"Give ONLY the doctor's specialization name in English and Hindi bracket. "
            f"Example: Ophthalmologist (Aankhon ke doctor)"
        )
        response = model.generate_content(prompt)
        if response.text:
            return response.text.strip()
        else:
            return "General Physician"
    except Exception as e:
        logging.error(f"Gemini API Error: {e}")
        # Agar API key kaam nahi kar rahi, toh yeh fallback error dega
        return "General Physician (Ya OPD mein sampark karein)"

def get_main_menu(user_name):
    # "(AI Doctor)" yahan se hata diya gaya hai
    return (
        f"Sat Sri Akal {user_name} ji! 🙏\n\n"
        "Aap kya karna chahte hain?\n"
        "1️⃣ Apni bimari batayein 🤖\n"
        "2️⃣ Direct Appointment Book karein 📅\n"
        "3️⃣ Test ya Ultrasound Book karein 🧪\n"
        "4️⃣ Help / Naam badlein ⚙️\n\n"
        "Kripya 1, 2, 3 ya 4 likh kar reply karein."
    )

@app.route("/", methods=['GET'])
def home():
    return "✅ Civil Hospital Bathinda Production Server is Online!", 200

@app.route("/whatsapp", methods=['POST'])
def whatsapp_bot():
    incoming_msg = request.values.get('Body', '').strip()
    incoming_msg_lower = incoming_msg.lower()
    sender_number = request.values.get('From', '').replace('whatsapp:', '')
    
    resp = MessagingResponse()
    msg = resp.message()
    
    conn = None
    cursor = None
    
    is_reset_trigger = incoming_msg_lower in ['hi', 'hello', 'menu', 'help', 'sat sri akal', 'restart', 'start']

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT full_name, session_step, temp_data FROM patients WHERE phone_number = %s", (sender_number,))
        patient = cursor.fetchone()

        if patient:
            name, step, temp_data = patient[0], patient[1], patient[2]

            # Global Reset
            if is_reset_trigger and name != "Naya Mareez" and step != 'IDLE':
                cursor.execute("UPDATE patients SET session_step = 'IDLE', temp_data = NULL WHERE phone_number = %s", (sender_number,))
                conn.commit()
                step = 'IDLE'

            # 1. Registration
            if name == "Naya Mareez":
                real_name = incoming_msg.title()
                cursor.execute("UPDATE patients SET full_name = %s, session_step = 'IDLE' WHERE phone_number = %s", (real_name, sender_number))
                conn.commit()
                msg.body(f"✅ Aapki profile successfully ban gayi hai.\n\n{get_main_menu(real_name)}")
            
            # 2. AI Doctor Suggestion
            elif step == 'ASKING_PROBLEM':
                doctor_specialization = get_doctor_suggestion(incoming_msg)
                cursor.execute("UPDATE patients SET session_step = 'IDLE' WHERE phone_number = %s", (sender_number,))
                conn.commit()
                msg.body(
                    f"🏥 AI Suggestion: Aapki pareshani ke hisab se aapko *{doctor_specialization}* ko dikhana chahiye.\n\n"
                    "Agar aap appointment book karna chahte hain toh '2' likhein, ya Main Menu ke liye 'Hi' bhejein."
                )

            # 3. Appointment/Test Booking
            elif step == 'WAITING_FOR_DATE':
                booking_type = temp_data if temp_data else "General Booking"
                
                cursor.execute(
                    "INSERT INTO appointments (patient_phone, appointment_type, appointment_date) VALUES (%s, %s, %s)", 
                    (sender_number, booking_type, incoming_msg)
                )
                cursor.execute("UPDATE patients SET session_step = 'IDLE', temp_data = NULL WHERE phone_number = %s", (sender_number,))
                conn.commit()
                msg.body(f"✅ Aapki *{booking_type}* successfully save ho gayi hai! 🏥 Hamara staff aapse jald hi sampark karega.")

            # 4. Help Menu Sub-logic
            elif step == 'HELP_MENU':
                if incoming_msg == '1':
                    cursor.execute("UPDATE patients SET session_step = 'CHANGING_NAME' WHERE phone_number = %s", (sender_number,))
                    conn.commit()
                    msg.body("Kripya apna naya naam likh kar bhejein:")
                elif incoming_msg == '0':
                    cursor.execute("UPDATE patients SET session_step = 'IDLE' WHERE phone_number = %s", (sender_number,))
                    conn.commit()
                    msg.body(get_main_menu(name))
                else:
                    msg.body("Kripya sahi option chunein:\n1️⃣ Naam Badlein\n0️⃣ Main Menu")

            # 5. Name Change Logic
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
                    cursor.execute("UPDATE patients SET session_step = 'WAITING_FOR_DATE', temp_data = 'Doctor Appointment' WHERE phone_number = %s", (sender_number,))
                    conn.commit()
                    msg.body("✅ Direct Appointment ke liye Date aur Time likhein (Jaise: 30 June, 10:00 AM):")
                
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
        msg.body("Maaf karein, system mein koi takneeki kharabi aa gayi hai. Kripya thodi der baad koshish karein.")
        
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return str(resp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
