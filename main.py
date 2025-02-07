import os
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from fpdf import FPDF
import jwt
import datetime
import requests
from passlib.context import CryptContext
import stripe
import speech_recognition as sr
import uuid
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)

# Load .env file
load_dotenv()

# Get environment variables
SECRET_KEY = os.getenv("SECRET_KEY")
STRIPE_API_KEY = os.getenv("STRIPE_SECRET_KEY")  # Corrected variable name for consistency
ANAF_API_URL = os.getenv("ANAF_API_URL")
EMAIL_API_URL = os.getenv("EMAIL_API_URL")
SMS_API_URL = os.getenv("SMS_API_URL")
WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL")

app = FastAPI()

# Configure authentication
password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

stripe.api_key = STRIPE_API_KEY

# User model
class User(BaseModel):
    username: str
    password: str
    role: str

# Tax calculation model
class TaxRequest(BaseModel):
    suma: float
    cota_tva: float

# PDF generation model
class PDFRequest(BaseModel):
    denumire_firma: str
    cnp_cui: str
    suma_tva: float

# Subscription payment model
class PaymentRequest(BaseModel):
    user_id: str
    plan: str

# Simulated database
fake_users_db = {}

@app.post("/register")
def register(user: User):
    hashed_password = password_context.hash(user.password)
    fake_users_db[user.username] = {"password": hashed_password, "role": user.role, "2fa_enabled": False}
    return {"msg": "User successfully registered"}

@app.post("/login")
def login(user: User):
    if user.username not in fake_users_db or not password_context.verify(user.password, fake_users_db[user.username]["password"]):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    token = jwt.encode({"sub": user.username, "role": fake_users_db[user.username]["role"], "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)}, SECRET_KEY, algorithm="HS256")
    return {"access_token": token}

@app.post("/calculate_tva")
def calculate_tva(request: TaxRequest):
    tva = request.suma * (request.cota_tva / 100)
    total = request.suma + tva
    return {"TVA": round(tva, 2), "Total": round(total, 2)}

@app.post("/generate_pdf")
def generate_pdf(request: PDFRequest):
    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt=f"TVA Declaration - {request.denumire_firma}", ln=True, align='C')
        pdf.cell(200, 10, txt=f"CUI: {request.cnp_cui}", ln=True, align='C')
        pdf.cell(200, 10, txt=f"Calculated VAT: {request.suma_tva} RON", ln=True, align='C')
        filename = f"tax_declaration_{uuid.uuid4()}.pdf"
        pdf.output(filename)
        return {"msg": "PDF successfully generated", "filename": filename}
    except Exception as e:
        logging.error(f"Failed to generate PDF: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate PDF")

@app.post("/submit_anaf")
def submit_anaf(data: dict):
    try:
        response = requests.post(ANAF_API_URL, json=data)
        return response.json()
    except Exception as e:
        logging.error(f"Error connecting to ANAF: {e}")
        return {"error": f"Error connecting to ANAF: {str(e)}"}

@app.post("/subscribe")
def subscribe(request: PaymentRequest):
    try:
        plan_prices = {"basic": 100, "pro": 200, "enterprise": 500}
        amount = plan_prices.get(request.plan, 100) * 100
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "ron",
                    "product_data": {"name": request.plan},
                    "unit_amount": amount,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"https://{os.getenv('APP_DOMAIN')}/success",
            cancel_url=f"https://{os.getenv('APP_DOMAIN')}/cancel",
        )
        return {"session_id": session.id}
    except Exception as e:
        logging.error(f"Error processing subscription: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/send_notification")
def send_notification(email: str, phone: str, message: str):
    try:
        requests.post(EMAIL_API_URL, json={"email": email, "message": message})
        requests.post(SMS_API_URL, json={"phone": phone, "message": message})
        requests.post(WHATSAPP_API_URL, json={"phone": phone, "message": message})
        return {"msg": "Notification sent successfully"}
    except Exception as e:
        logging.error(f"Error sending notification: {e}")
        return {"error": f"Error sending notification: {str(e)}"}

# Additional functions would continue here...