import os
import uuid
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# PayHero Config from Render Environment
PAYHERO_BASE_URL = "https://backend.payhero.co.ke/api/v2"
PAYHERO_USERNAME = os.environ.get("PAYHERO_API_USERNAME")
PAYHERO_PASSWORD = os.environ.get("PAYHERO_API_PASSWORD")
PAYHERO_CHANNEL_ID = os.environ.get("PAYHERO_CHANNEL_ID", "13363")
PAYHERO_CALLBACK = os.environ.get("PAYHERO_CALLBACK_URL", "https://pesafly.onrender.com/payhero/callback")

def format_phone(phone):
    p = phone.strip().replace(" ", "").replace("+", "")
    if p.startswith("0"):
        p = "254" + p[1:]
    if not p.startswith("254"):
        p = "254" + p
    return p

@app.route("/")
def home():
    return """
    <!DOCTYPE html>
    <html>
    <head><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>PesaFly - Real M-Pesa</title>
    <style>
    body{font-family:sans-serif;background:#f5f5f5;padding:20px;text-align:center}
    .box{background:white;padding:25px;border-radius:15px;max-width:400px;margin:30px auto;box-shadow:0 4px 15px rgba(0,0,0,.1)}
    input{width:90%;padding:12px;margin:10px 0;border:1px solid #ddd;border-radius:8px;font-size:16px}
    button{background:#00c853;color:white;border:none;padding:14px 25px;border-radius:8px;width:95%;font-size:18px;font-weight:bold;cursor:pointer}
    #status{margin-top:15px;font-weight:bold}
    </style></head>
    <body>
    <h2>✈️ PesaFly - REAL M-Pesa STK</h2>
    <div class="box">
      <input id="phone" placeholder="Phone 07xxxxxxxx">
      <input id="amount" type="number" placeholder="Amount e.g 1" value="1">
      <input id="name" placeholder="Your Name">
      <button onclick="pay()">LIPA NA M-PESA NOW</button>
      <div id="status"></div>
    </div>
    <script>
    async function pay(){
      const phone=document.getElementById('phone').value;
      const amount=document.getElementById('amount').value;
      const name=document.getElementById('name').value || 'PesaFly Customer';
      const status=document.getElementById('status');
      if(!phone){alert('Enter phone');return}
      status.innerHTML='⏳ Sending STK Push... Check phone!';
      status.style.color='blue';
      try{
        const res=await fetch('/pay',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phone_number:phone,amount:amount,customer_name:name})});
        const data=await res.json();
        if(data.success){status.innerHTML='✅ '+data.message; status.style.color='green';}
        else{status.innerHTML='❌ '+data.message; status.style.color='red';}
      }catch(e){status.innerHTML='❌ Network error'; status.style.color='red';}
    }
    </script>
    </body></html>
    """

@app.route("/pay", methods=["POST"])
def pay():
    try:
        data = request.get_json()
        phone_raw = data.get("phone_number")
        amount = int(data.get("amount", 1))
        customer = data.get("customer_name", "PesaFly Customer")

        if not phone_raw:
            return jsonify({"success": False, "message": "Phone required"}), 400

        phone = format_phone(phone_raw)
        ref = f"PESAF-{uuid.uuid4().hex[:8].upper()}"

        payload = {
            "amount": amount,
            "phone_number": phone,
            "channel_id": int(PAYHERO_CHANNEL_ID),
            "provider": "m-pesa",
            "external_reference": ref,
            "customer_name": customer,
            "callback_url": PAYHERO_CALLBACK
        }

        print(f"STK PUSH {phone} KES {amount} Ref {ref}")

        resp = requests.post(
            f"{PAYHERO_BASE_URL}/payments",
            json=payload,
            auth=(PAYHERO_USERNAME, PAYHERO_PASSWORD),
            timeout=30
        )

        result = resp.json()
        print(f"PayHero: {result}")

        if resp.status_code in [200, 201]:
            return jsonify({"success": True, "message": f"STK sent to {phone_raw}. Enter M-Pesa PIN on phone!", "reference": ref, "data": result})
        else:
            return jsonify({"success": False, "message": result.get("message", "Failed"), "data": result}), 400

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/payhero/callback", methods=["POST", "GET"])
def callback():
    data = request.get_json(silent=True) or {}
    print(f"CALLBACK: {data}")
    # Here you would save to DB if payment success
    return jsonify({"status": "ok"}), 200

@app.route("/health")
def health():
    return jsonify({"status": "live", "has_keys": bool(PAYHERO_USERNAME and PAYHERO_PASSWORD), "channel": PAYHERO_CHANNEL_ID})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
