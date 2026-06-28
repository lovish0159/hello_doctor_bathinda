import os
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import psycopg2

app = Flask(__name__)

@app.route("/", methods=['GET'])
def home():
    return "✅ Hello Doctor Bathinda da Server Cloud te bilkul sahi chal reha hai!"

def get_db_connection():
    DATABASE_URL = os.environ.get("DATABASE_URL")
    if not DATABASE_URL:
        raise ValueError("❌ DATABASE_URL set nahi hai! Kripya environment variables check karein.")
    return psycopg2.connect(DATABASE_URL)

@app.route("/whatsapp", methods=['POST'])
def whatsapp_bot():
    incoming_msg = request.values.get('Body', '').strip()
    sender_number = request.values.get('From', '').replace('whatsapp:', '') 

    resp = MessagingResponse()
    msg = resp.message()

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT full_name FROM patients WHERE phone_number = %s", (sender_number,))
        patient = cursor.fetchone()

        if patient:
            patient_name = patient[0]
            
            if patient_name == "Naya Mareez":
                real_name = incoming_msg.title()
                cursor.execute("UPDATE patients SET full_name = %s WHERE phone_number = %s", (real_name, sender_number))
                conn.commit()
                
                success_text = (
                    f"✅ Tuhadi profile '{real_name}' de naam te complete ho gayi hai!\n\n"
                    "Main menu:\n"
                    "1️⃣ Appointment Book Karo 📅\n"
                    "2️⃣ Test ya Ultrasound Book Karo 🧪\n\n"
                    "(Kripya 1 ya 2 likh ke bhejo)"
                )
                msg.body(success_text)
                
            else:
                # NAYA LOGIC ITHE HAI (1 ya 2 da jawab)
                if incoming_msg == '1':
                    cursor.execute(
                        "INSERT INTO appointments (patient_phone, appointment_type) VALUES (%s, %s)",
                        (sender_number, "Doctor Appointment")
                    )
                    conn.commit()
                    msg.body("✅ Tuhadi *Doctor Appointment* successfully book ho gayi hai! 🏥\nSada staff tuhanu jaldi hi time confirm karega.")
                
                elif incoming_msg == '2':
                    cursor.execute(
                        "INSERT INTO appointments (patient_phone, appointment_type) VALUES (%s, %s)",
                        (sender_number, "Test/Ultrasound")
                    )
                    conn.commit()
                    msg.body("✅ Tuhada *Test/Ultrasound* successfully book ho gaya hai! 🧪\nSada staff tuhanu jaldi hi time confirm karega.")
                
                else:
                    # Agar user ne 1 ya 2 ton ilawa kujh hor likheya hai
                    welcome_back_text = (
                        f"Sat Sri Akal *{patient_name}* ji! 🙏 \n\n"
                        "Ajj tusi ki book karna chaunde ho?\n"
                        "1️⃣ Appointment Book Karo 📅\n"
                        "2️⃣ Test ya Ultrasound Book Karo 🧪\n\n"
                        "(Kripya 1 ya 2 likh ke bhejo)"
                    )
                    msg.body(welcome_back_text)
        
        else:
            cursor.execute(
                "INSERT INTO patients (phone_number, full_name) VALUES (%s, %s)",
                (sender_number, "Naya Mareez")
            )
            conn.commit() 

            new_user_text = (
                "*Sat Sri Akal! 'Hello Doctor Bathinda' vich tuhada swagat hai.* 🏥\n\n"
                "Kripya registration layi apna poora naam likh ke bhejo:"
            )
            msg.body(new_user_text)

    except Exception as e:
        print(f"Error: {e}")
        msg.body("Maaf karna, system vich koi takneeki kharabi aa gayi hai. Kripya baad vich koshish karo.")
    
    finally:
        cursor.close()
        conn.close()

    return str(resp)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
