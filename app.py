from flask import Flask, render_template, request, jsonify, session
import random, os
import requests
from datetime import datetime
from collections import deque

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "pesafly-v14-LEGIT-SECURE-2026")

# --- PAYHERO CONFIG - ADD THESE IN RENDER ENV ---
PAYHERO_USERNAME = os.getenv("PAYHERO_USERNAME") # from PayHero dashboard
PAYHERO_PASSWORD = os.getenv("PAYHERO_PASSWORD") # from PayHero dashboard
PAYHERO_CHANNEL_ID = os.getenv("PAYHERO_CHANNEL_ID") # Till channel ID
PAYHERO_LIVE = True

users_db = {}
pending_payments = {} # Track STK pending
all_withdraw_requests = []
history = deque(maxlen=20)
history.extend([round(random.uniform(1.2, 15.0),2) for _ in range(10)])
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "PesaAdmin123")

def get_user():
    phone = session.get('phone')
    return (phone, users_db.get(phone)) if phone else (None, None)

@app.route('/')
def index():
    return render_template('index.html')

# --- NEW LEGIT DEPOSIT WITH PAYHERO ---
@app.route('/api/deposit', methods=['POST'])
def deposit():
    phone, u = get_user()
    if not u: return jsonify({"success": False, "error": "Login first"})
    amt = float(request.json.get('amount',0))

    # LEGIT LIMITS FOR KENYA
    if amt < 50: return jsonify({"success": False, "error": "Min deposit KES 50"})
    if amt > 70000: return jsonify({"success": False, "error": "Max deposit KES 70,000"})

    # Clean phone to 2547...
    raw_phone = phone
    if raw_phone.startswith('0'): raw_phone = '254' + raw_phone[1:]
    if not raw_phone.startswith('254'): raw_phone = '254' + raw_phone[-9:]

    # IF PAYHERO NOT YET CONFIGURED (while waiting KYC) - Use TEST MODE
    if not PAYHERO_USERNAME:
        # TEST MODE - will be replaced when Till approved
        return jsonify({
            "success": True,
            "test_mode": True,
            "msg": f"TEST: Deposit KES {amt} - Waiting for PayHero Till approval. Balance will be real after approval.",
            "pay_to": "PesaFly Company"
        })

    # REAL PAYHERO STK PUSH
    try:
        url = "https://backend.payhero.co.ke/api/v2/payments"
        payload = {
            "amount": int(amt),
            "phone_number": raw_phone,
            "channel_id": int(PAYHERO_CHANNEL_ID),
            "provider": "m-pesa",
            "external_reference": f"PESAFLY-{phone}-{int(datetime.now().timestamp())}",
            "callback_url": f"{request.host_url}api/payhero-callback"
        }
        auth = (PAYHERO_USERNAME, PAYHERO_PASSWORD)
        r = requests.post(url, json=payload, auth=auth, timeout=30)
        data = r.json()

        if r.status_code == 200 and data.get('success'):
            pending_payments[data.get('reference')] = {"phone": phone, "amount": amt, "time": datetime.now().isoformat()}
            u['transactions'].append({"type":"DEPOSIT INITIATED","amount":amt,"time":datetime.now().isoformat(),"status":"STK Sent to M-Pesa - Pay to PesaFly Company"})
            return jsonify({"success": True, "msg": f"STK sent to {phone}! Check M-Pesa - Pay to PesaFly Company KES {amt}", "reference": data.get('reference')})
        else:
            return jsonify({"success": False, "error": f"M-Pesa failed: {data}"})
    except Exception as e:
        return jsonify({"success": False, "error": f"Payment error: {str(e)}"})

# CALLBACK FROM PAYHERO WHEN USER PAYS
@app.route('/api/payhero-callback', methods=['POST'])
def payhero_callback():
    data = request.json
    print("PayHero Callback:", data)
    # PayHero sends success status
    ref = data.get('reference') or data.get('external_reference')
    amount = float(data.get('amount', 0))
    status = data.get('status') == True or data.get('response') == 'Success'

    if status and ref:
        # Find user from reference
        for p in pending_payments.values():
            phone = p['phone']
            if phone in users_db:
                u = users_db[phone]
                amt = p['amount']
                if not u['first_deposit_done']:
                    # LEGIT BONUS - 10% NOT 1000!
                    bonus = min(amt * 0.1, 100) # 10% max 100 - legit
                    u['real'] += amt
                    u['bonus'] += bonus
                    u['first_deposit_done'] = True
                    u['bonus_claimed'] = True
                    u['bonus_locked'] = False
                    u['deposited'] += amt
                    u['transactions'].append({"type":"FIRST DEPOSIT","amount":amt,"time":datetime.now().isoformat(),"status":"Success - PesaFly Company"})
                    if bonus>0:
                        u['transactions'].append({"type":"WELCOME BONUS 10%","amount":bonus,"time":datetime.now().isoformat(),"status":"Unlocked"})
                else:
                    u['real'] += amt
                    u['deposited'] += amt
                    u['transactions'].append({"type":"DEPOSIT","amount":amt,"time":datetime.now().isoformat(),"status":"Success - PesaFly Company"})
                break
    return jsonify({"success": True})

# --- YOUR OTHER ROUTES KEEP SAME BUT WITH LEGIT LIMITS ---
@app.route('/api/bet', methods=['POST'])
def bet():
    phone, u = get_user()
    if not u: return jsonify({"success": False, "error": "Login"})
    amount=float(request.json.get('amount',0))
    if amount<10: return jsonify({"success": False, "error": "Min bet 10"})
    total=u['real']+u['bonus']+u['ref_bonus']
    if total<amount: return jsonify({"success": False, "error": "Low balance - Deposit to PesaFly Company"})
    # deduct logic
    if u['real']>=amount: u['real']-=amount
    elif u['real']+u['bonus']>=amount:
        remain=amount-u['real']; u['real']=0; u['bonus']-=remain
    else:
        remain=amount-u['real']-u['bonus']; u['real']=0; u['bonus']=0; u['ref_bonus']-=remain
    u['bets'].append({"type":"BET","amount":amount,"multi":0,"win":0,"time":datetime.now().isoformat(),"status":"LOST"})
    u['transactions'].append({"type":"BET","amount":-amount,"time":datetime.now().isoformat(),"status":"Success"})
    return jsonify({"success": True})

#... keep rest of your routes: crash, history, cashout, auth, me, etc...

@app.route('/api/admin-data')
def admin_data():
    if not session.get('is_admin'): return jsonify({"error": "Not admin"}), 401
    return jsonify({
        "users": [{"phone":k,"real":v['real'],"bonus":v['bonus'],"deposited":v['deposited']} for k,v in users_db.items()],
        "withdraws": all_withdraw_requests[::-1], "total_users": len(users_db),
        "pending": pending_payments
    })

# [PASTE YOUR OTHER ROUTES HERE FROM OLD FILE - auth, me, logout, crash, history, cashout, withdraw etc]
# For brevity I kept deposit as main change

from flask import Flask, render_template, request, jsonify, session, redirect
#... (your old auth routes - copy them back here)
