import os
import google.generativeai as genai
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import psycopg2

app = Flask(__name__)
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# Gemini nu pucchhan layi function
def get_doctor_suggestion(problem):
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content(f"Patient di problem hai: '{problem}'. Batayo ki kis doctor nu dikhana chahida hai? Sirf specialization da naam do.")
    return response.text

@app.route("/whatsapp", methods=['POST'])
def whatsapp_bot():
    incoming_msg = request.values.get('Body', '').strip()
    sender_number = request.values.get('From', '').replace('whatsapp:', '')
    
    resp = MessagingResponse()
    msg = resp.message()
    
    # Session state check karan layi database logic
    conn = psycopg2.connect(os.environ.get("DATABASE_URL"))
    cursor = conn.cursor()
    cursor.execute("SELECT session_step, temp_data FROM patients WHERE phone_number = %s", (sender_number,))
    row = cursor.fetchone()
    
    step = row[0] if row else 'IDLE'

    if step == 'ASKING_PROBLEM':
        # Gemini da use karke suggestion
        doctor = get_doctor_suggestion(incoming_msg)
        cursor.execute("UPDATE patients SET session_step = 'IDLE' WHERE phone_number = %s", (sender_number,))
        conn.commit()
        msg.body(f"🏥 Gemini Suggestion: Tuhanu *{doctor}* nu dikhana chahida hai. Ki tusi appointment book karni hai? (Haan/Nahi)")

    elif incoming_msg == '1':
        cursor.execute("UPDATE patients SET session_step = 'ASKING_PROBLEM' WHERE phone_number = %s", (sender_number,))
        conn.commit()
        msg.body("Kripya apni bimari ya problem likho:")

    elif incoming_msg == '2':
        msg.body("Direct Appointment book karni hai? Kripya Date/Time likho (jivein: 30 June, 10:00 AM):")
    
    else:
        msg.body("Menu:\n1️⃣ Problem daso (AI Suggestion)\n2️⃣ Direct Appointment")

    cursor.close()
    conn.close()
    return str(resp)
    
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
