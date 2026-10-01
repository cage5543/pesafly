import os
import uuid
import requests
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import logging

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

# --- PAYHERO CONFIG FROM RENDER ENV ---
PAYHERO_BASE_URL = "https://backend.payhero.co.ke/api/v2"
PAYHERO_API_USERNAME = os.environ.get("PAYHERO_API_USERNAME")
PAYHERO_API_PASSWORD = os.environ.get("PAYHERO_API_PASSWORD")
PAYHERO_CHANNEL_ID = os.environ.get("PAYHERO_CHANNEL_ID", "13363")
PAYHERO_CALLBACK_URL = os.environ.get("PAYHERO_CALLBACK_URL", "https://pesafly.onrender.com/payhero/callback")

def normalize_phone(phone):
    """ 07xx / 2547xx / +254 -> 2547... format for PayHero """
    phone = phone.strip().replace(" ", "")
    if phone.startswith("+"):
        phone = phone[1:]
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    if not phone.startswith("254"):
        phone = "254" + phone
    return phone

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/pay", methods=["POST"])
def pay():
    try:
        data = request.get_json() or request.form
        amount = int(data.get("amount", 1))
        phone_raw = data.get("phone_number") or data.get("phone")
        customer_name = data.get("customer_name", "PesaFly Customer")
        
        if not phone_raw:
            return jsonify({"success": False, "message": "Phone number required"}), 400
        
        phone = normalize_phone(phone_raw)
        
        # Validate Kenya number
        if not (phone.startswith("2547") or phone.startswith("2541")):
            return jsonify({"success": False, "message": "Use Safaricom 07.. or Airtel 01.. number"}), 400

        external_reference = f"PESAF-{uuid.uuid4().hex[:8].upper()}"
        
        payload = {
            "amount": amount,
            "phone_number": phone,
            "channel_id": int(PAYHERO_CHANNEL_ID),
            "provider": "m-pesa",
            "external_reference": external_reference,
            "customer_name": customer_name,
            "callback_url": PAYHERO_CALLBACK_URL
        }
        
        app.logger.info(f"STK Push -> {phone} KES {amount} Ref {external_reference}")
        
        # Real PayHero API Call
        response = requests.post(
            f"{PAYHERO_BASE_URL}/payments",
            json=payload,
            auth=(PAYHERO_API_USERNAME, PAYHERO_API_PASSWORD),
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        result = response.json() if response.content else {}
        app.logger.info(f"PayHero response: {result}")
        
        if response.status_code in [200, 201] and result.get("success", True):
            return jsonify({
                "success": True,
                "message": f"STK Push sent to {phone_raw}. Check your phone and enter M-Pesa PIN!",
                "reference": external_reference,
                "payhero_data": result
            })
        else:
            return jsonify({
                "success": False,
                "message": result.get("message", "Failed to send STK Push"),
                "details": result
            }), 400
            
    except Exception as e:
        app.logger.error(f"STK Error: {str(e)}")
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500

@app.route("/payhero/callback", methods=["POST", "GET"])
def payhero_callback():
    """ PayHero will call this after customer pays """
    data = request.get_json(silent=True) or {}
    app.logger.info(f"CALLBACK RECEIVED: {data}")
    
    # Log to file for debugging
    try:
        with open("callback_logs.json", "a") as f:
            f.write(str(data) + "\n")
    except:
        pass
    
    # TODO: Update your database here
    # Example: if data.get("status") == "SUCCESS"
    
    return jsonify({"status": "received"}), 200

@app.route("/health")
def health():
    return jsonify({"status": "live", "channel_id": PAYHERO_CHANNEL_ID})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
