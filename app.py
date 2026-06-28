import os
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import psycopg2

app = Flask(__name__)

# Cloud Server test karan layi Home Page
@app.route("/", methods=['GET'])
def home():
    return "✅ Hello Doctor Bathinda da Server Cloud te bilkul sahi chal reha hai!"

# Neon.tech Database Connection
def get_db_connection():
    # Asli link ki jagah hum os.environ ka use kar rahe hain
    # Yeh password ko code mein nahi, balki server ki settings se uthayega
    DATABASE_URL = os.environ.get("DATABASE_URL")
    
    if not DATABASE_URL:
        raise ValueError("❌ DATABASE_URL set nahi hai! Kripya environment variables check karein.")
        
    return psycopg2.connect(DATABASE_URL)

@app.route("/whatsapp", methods=['POST'])
def whatsapp_bot():
    incoming_msg = request.values.get('Body', '').strip()
    # 'whatsapp:' prefix nu hatana
    sender_number = request.values.get('From', '').replace('whatsapp:', '') 

    resp = MessagingResponse()
    msg = resp.message()

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Step 1: Check patient status
        cursor.execute("SELECT full_name FROM patients WHERE phone_number = %s", (sender_number,))
        patient = cursor.fetchone()

        if patient:
            patient_name = patient[0]
            
            # Step 2: Name update logic
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
                # Normal menu
                welcome_back_text = (
                    f"Sat Sri Akal *{patient_name}* ji! 🙏 \n\n"
                    "Ajj tusi ki book karna chaunde ho?\n"
                    "1️⃣ Appointment Book Karo 📅\n"
                    "2️⃣ Test ya Ultrasound Book Karo 🧪"
                )
                msg.body(welcome_back_text)
        
        else:
            # Step 3: New user registration
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

# Cloud server (Render) layi Port settings
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
