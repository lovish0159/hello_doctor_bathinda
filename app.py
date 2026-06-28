import os
import google.generativeai as genai
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import psycopg2

app = Flask(__name__)

# Gemini API Setup
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

def get_db_connection():
    return psycopg2.connect(os.environ.get("DATABASE_URL"))

def get_doctor_suggestion(problem):
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"Patient di problem hai: '{problem}'. Civil Hospital de hisaab naal kis doctor nu dikhana chahida hai? Sirf specialization da naam do (e.g., Cardiologist, Orthopedic, General Physician)."
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini Error: {e}")
        return "General Physician"

@app.route("/", methods=['GET'])
def home():
    return "✅ Civil Hospital Bathinda Bot Server Cloud te Live hai!"

@app.route("/whatsapp", methods=['POST'])
def whatsapp_bot():
    incoming_msg = request.values.get('Body', '').strip().lower()
    sender_number = request.values.get('From', '').replace('whatsapp:', '')
    
    resp = MessagingResponse()
    msg = resp.message()
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Check if patient exists
        cursor.execute("SELECT full_name, session_step, temp_data FROM patients WHERE phone_number = %s", (sender_number,))
        patient = cursor.fetchone()

        if patient:
            name, step, temp_data = patient[0], patient[1], patient[2]

            # Agar mareez apna naam register kar reha hai
            if name == "Naya Mareez":
                cursor.execute("UPDATE patients SET full_name = %s, session_step = 'IDLE' WHERE phone_number = %s", (incoming_msg.title(), sender_number))
                conn.commit()
                msg.body(
                    f"✅ Swagat {incoming_msg.title()} ji!\n\n"
                    "Main Ram, Civil Hospital Bathinda da AI assistant haan. Tusi ki karna chaunde ho?\n\n"
                    "1️⃣ Apni problem daso (AI Doctor Suggestion) 🤖\n"
                    "2️⃣ Direct Appointment Book Karo 📅\n"
                    "3️⃣ Test ya Ultrasound Book Karo 🧪"
                )
            
            # Agar mareez ne '1' dabaya aur bot problem puchh reha hai
            elif step == 'ASKING_PROBLEM':
                doctor_specialization = get_doctor_suggestion(incoming_msg)
                cursor.execute("UPDATE patients SET session_step = 'IDLE' WHERE phone_number = %s", (sender_number,))
                conn.commit()
                msg.body(
                    f"🏥 AI Suggestion: Tuhadi problem de hisaab naal tuhanu *{doctor_specialization}* nu dikhana chahida hai.\n\n"
                    "Ki tusi is doctor naal direct appointment book karni hai?\n"
                    "Kripya Main Menu layi 'Hi' bhejo, ya appointment layi '2' likho."
                )

            # Agar mareez ne '2' ya '3' dabaya aur bot date/time wait kar reha hai
            elif step == 'WAITING_FOR_DATE':
                # temp_data vich save hovega ki 'Doctor Appointment' hai ya 'Test/Ultrasound'
                booking_type = temp_data if temp_data else "General Booking"
                
                cursor.execute(
                    "INSERT INTO appointments (patient_phone, appointment_type, appointment_date) VALUES (%s, %s, %s)", 
                    (sender_number, booking_type, incoming_msg)
                )
                # Booking de baad state nu wapas IDLE aur temp_data nu NULL kar do
                cursor.execute("UPDATE patients SET session_step = 'IDLE', temp_data = NULL WHERE phone_number = %s", (sender_number,))
                conn.commit()
                msg.body(f"✅ Tuhadi *{booking_type}* successfully save ho gayi hai! 🏥 Sada staff tuhanu jaldi hi confirm karega.")

            # Main Menu Logic (IDLE State)
            else:
                if incoming_msg == '1':
                    cursor.execute("UPDATE patients SET session_step = 'ASKING_PROBLEM' WHERE phone_number = %s", (sender_number,))
                    conn.commit()
                    msg.body("Kripya apni bimari ya problem detail vich likho (jivein: Menu 2 din ton bukhar aur pet dard hai):")
                
                elif incoming_msg == '2':
                    cursor.execute("UPDATE patients SET session_step = 'WAITING_FOR_DATE', temp_data = 'Doctor Appointment' WHERE phone_number = %s", (sender_number,))
                    conn.commit()
                    msg.body("✅ Direct Appointment layi Date aur Time likho (jivein: 30 June, 10:00 AM):")
                
                elif incoming_msg == '3':
                    cursor.execute("UPDATE patients SET session_step = 'WAITING_FOR_DATE', temp_data = 'Test/Ultrasound' WHERE phone_number = %s", (sender_number,))
                    conn.commit()
                    msg.body("✅ Test ya Ultrasound layi Date aur Time likho (jivein: 30 June, 10:00 AM):")
                
                else:
                    msg.body(
                        "Main Ram, Civil Hospital Bathinda da AI assistant haan. Kripya ek option chuno:\n\n"
                        "1️⃣ Apni problem daso (AI Doctor Suggestion) 🤖\n"
                        "2️⃣ Direct Appointment Book Karo 📅\n"
                        "3️⃣ Test ya Ultrasound Book Karo 🧪"
                    )

        # Agar mareez pehli vaar message bhej reha hai
        else:
            cursor.execute("INSERT INTO patients (phone_number, full_name, session_step) VALUES (%s, %s, 'IDLE')", (sender_number, "Naya Mareez"))
            conn.commit()
            msg.body(
                "Sat Sri Akal! 🙏 'Hello Doctor Bathinda' vich tuhada swagat hai.\n\n"
                "Kripya aage vadan layi apna poora naam likh ke bhejo:"
            )

    except Exception as e:
        print(f"Server Error: {e}")
        msg.body("Maaf karna, system vich koi takneeki kharabi aa gayi hai.")
    finally:
        cursor.close()
        conn.close()

    return str(resp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
