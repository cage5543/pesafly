from flask import Flask, render_template, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
import random, os, requests, string
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "pesafly-v16-final-2026")

# --- CONFIG ---
ADMIN_PASS = "PesaAdmin123"
WELCOME_BONUS = 1000
MIN_DEPOSIT_TO_UNLOCK = 350
MIN_WITHDRAW_NOBONUS = 500
MIN_WITHDRAW_BONUS = 3000 # Any bonus needs 3K to withdraw = HOUSE PROFIT
WITHDRAW_FEE = 0.10
REFERRAL_BONUS = 150

# --- DB ---
users = {}
referral_codes = {}
transactions = []
crash_history = [round(random.uniform(1.2, 15), 2) for _ in range(25)]
house_stats = {"total_deposited": 0.0, "total_withdrawn": 0.0, "total_fees": 0.0, "total_bets": 0.0, "total_won": 0.0}
FAKE_NAMES = [f"{n}{random.randint(10,999)}" for n in ["Brian","Kevin","Faith","Sharon","Moses","Wanjiku","Otieno","Kamau","Njeri","Grace","Mutiso","John","Akinyi","Chebet","Njoroge"] for _ in range(50)]

# PayHero
PAYHERO_URL = "https://backend.payhero.co.ke/api/v2/payments"
PAYHERO_USER = os.environ.get("PAYHERO_API_USERNAME")
PAYHERO_PASS = os.environ.get("PAYHERO_API_PASSWORD")
PAYHERO_CHANNEL = os.environ.get("PAYHERO_CHANNEL_ID", "13363")

def gen_code():
    return ''.join(random.choices(string.ascii_uppercase+string.digits, k=6))

def get_user():
    email = session.get('email')
    return (email, users.get(email)) if email else (None, None)

def get_house_profit():
    return house_stats["total_deposited"] - house_stats["total_withdrawn"] + house_stats["total_fees"] + (house_stats["total_bets"] - house_stats["total_won"])

def generate_crash():
    total_bets = sum(u.get('current_bet',0) for u in users.values())
    if total_bets > 5000 and random.random() < 0.6:
        return round(random.uniform(1.0, 1.8),2)
    r = random.random()
    if r < 0.45: return round(random.uniform(1.0, 1.95),2)
    elif r < 0.80: return round(random.uniform(2.0, 5.0),2)
    elif r < 0.95: return round(random.uniform(5.0, 15.0),2)
    else: return round(random.uniform(15.0, 80.0),2)

# --- PAGES ---
@app.route('/')
def home():
    ref = request.args.get('ref', '').upper()
    return render_template('index.html', ref_code=ref)

@app.route('/r/<code>')
def ref_redirect(code):
    return render_template('index.html', ref_code=code.upper())

@app.route('/login')
def login_page(): return render_template('index.html', ref_code='', open_login=True)

@app.route('/register')
def register_page(): return render_template('index.html', ref_code='', open_register=True)

@app.route('/busted')
def busted_page(): return render_template('index.html')
@app.route('/promotion')
def promo_page(): return render_template('index.html')
@app.route('/basics')
def basics_page(): return render_template('index.html')
@app.route('/forgot-password')
def forgot_page(): return render_template('index.html')
@app.route('/admin')
def admin_page(): return render_template('admin.html')

@app.route('/sitemap.xml')
def sitemap():
    pages = ['/', '/login', '/register', '/busted', '/promotion', '/basics', '/forgot-password']
    xml = '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    for p in pages:
        xml += f"<url><loc>https://pesafly.onrender.com{p}</loc><priority>0.8</priority></url>"
    xml += "</urlset>"
    return app.response_class(xml, mimetype='application/xml')

@app.route('/robots.txt')
def robots():
    return "User-agent: *\nAllow: /\nSitemap: https://pesafly.onrender.com/sitemap.xml"

@app.route('/health')
def health():
    return jsonify({"status":"live","v":"V16","house_profit":get_house_profit(),"users":len(users),"has_keys": bool(PAYHERO_USER)})

# --- API ---
@app.route('/api/me')
def me():
    email, u = get_user()
    if not u: return jsonify({"logged": False})
    can_claim = u['total_deposited'] >= MIN_DEPOSIT_TO_UNLOCK and not u['bonus_claimed']
    return jsonify({"logged": True, "email": email, "real": u['real_balance'], "bonus": u['bonus_balance'], "total": u['real_balance']+u['bonus_balance'], "deposited": u['total_deposited'], "bonus_locked": u['bonus_locked'], "bonus_claimed": u['bonus_claimed'], "can_claim": can_claim, "my_code": u.get('my_ref_code','')})

@app.route('/api/auth', methods=['POST'])
def auth():
    data = request.json
    email = data.get('email','').lower().strip()
    pwd = data.get('password','')
    act = data.get('action','login')
    ref_code = data.get('referral','').strip().upper()
    if act == 'register':
        if email in users: return jsonify({"success": False, "error": "Account exists, login"})
        my_code = gen_code()
        while my_code in referral_codes: my_code = gen_code()
        users[email] = {"pass_hash": generate_password_hash(pwd), "real_balance": 0.0, "bonus_balance": 0.0, "bonus_locked": True, "bonus_claimed": False, "total_deposited": 0.0, "total_withdrawn": 0.0, "total_bet": 0.0, "total_won": 0.0, "current_bet": 0.0, "my_ref_code": my_code, "referred_by": ref_code if ref_code else None, "referrals": [], "ref_bonus_earned": 0.0, "ref_bonus_paid": False, "created": str(datetime.now())}
        referral_codes[my_code] = email
        session['email'] = email
        return jsonify({"success": True, "my_code": my_code})
    else:
        u = users.get(email)
        if not u or not check_password_hash(u['pass_hash'], pwd):
            return jsonify({"success": False, "error": "Wrong phone/password"})
        session['email'] = email
        return jsonify({"success": True})

@app.route('/api/logout', methods=['POST'])
def logout(): session.clear(); return jsonify({"success": True})

@app.route('/api/deposit', methods=['POST'])
def deposit():
    email, u = get_user()
    if not u: return jsonify({"success": False, "error": "Login first"})
    data = request.json
    amount = float(data.get('amount', 350))
    phone = data.get('phone','').strip()
    if not PAYHERO_USER or not PAYHERO_PASS:
        u['real_balance'] += amount; u['total_deposited'] += amount; house_stats["total_deposited"] += amount
        if u['total_deposited'] >= MIN_DEPOSIT_TO_UNLOCK: u['bonus_locked'] = False
        # referral
        if u['referred_by'] and not u['ref_bonus_paid'] and u['total_deposited'] >= 350:
            owner_code = u['referred_by']
            if owner_code in referral_codes:
                owner_email = referral_codes[owner_code]
                if owner_email in users:
                    users[owner_email]['bonus_balance'] += REFERRAL_BONUS
                    users[owner_email]['ref_bonus_earned'] += REFERRAL_BONUS
                    users[owner_email]['referrals'].append(email)
                    u['ref_bonus_paid'] = True
        return jsonify({"success": True, "msg": f"TEST Added KES {amount}. Now CLAIM bonus!", "real": u['real_balance']})
    if not phone: return jsonify({"success": False, "error": "Phone required"})
    if phone.startswith("0"): phone = "254"+phone[1:]
    if phone.startswith("7"): phone = "254"+phone
    payload = {"amount": amount, "phone_number": phone, "channel_id": int(PAYHERO_CHANNEL), "provider": "m-pesa", "external_reference": f"PESAF-{random.randint(1000,9999)}", "callback_url": os.environ.get("PAYHERO_CALLBACK_URL","https://pesafly.onrender.com/payhero/callback")}
    try:
        r = requests.post(PAYHERO_URL, json=payload, auth=(PAYHERO_USER, PAYHERO_PASS), timeout=20)
        res = r.json()
        if r.status_code in [200,201] or res.get("success"):
            u['real_balance'] += amount; u['total_deposited'] += amount; house_stats["total_deposited"] += amount
            if u['total_deposited'] >= MIN_DEPOSIT_TO_UNLOCK: u['bonus_locked'] = False
            if u['referred_by'] and not u['ref_bonus_paid'] and u['total_deposited'] >= 350:
                owner_code = u['referred_by']
                if owner_code in referral_codes:
                    owner_email = referral_codes[owner_code]
                    if owner_email in users:
                        users[owner_email]['bonus_balance'] += REFERRAL_BONUS
                        users[owner_email]['ref_bonus_earned'] += REFERRAL_BONUS
                        users[owner_email]['referrals'].append(email)
                        u['ref_bonus_paid'] = True
            return jsonify({"success": True, "msg": f"STK sent to {phone}! Enter PIN. Then CLAIM"})
        else:
            return jsonify({"success": False, "error": str(res)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/claim-bonus', methods=['POST'])
def claim_bonus():
    email, u = get_user()
    if not u: return jsonify({"success": False})
    if u['bonus_claimed']: return jsonify({"success": False, "error": "Already claimed"})
    if u['total_deposited'] < MIN_DEPOSIT_TO_UNLOCK: return jsonify({"success": False, "error": f"Deposit {MIN_DEPOSIT_TO_UNLOCK} first"})
    u['bonus_balance'] += WELCOME_BONUS; u['bonus_claimed'] = True; u['bonus_locked'] = False
    return jsonify({"success": True, "msg": f"CLAIMED {WELCOME_BONUS}! Total KES {u['real_balance']+u['bonus_balance']}", "real": u['real_balance'], "bonus": u['bonus_balance']})

@app.route('/api/crash')
def get_crash():
    cp = generate_crash(); crash_history.insert(0, cp)
    if len(crash_history)>30: crash_history.pop()
    return jsonify({"crash": cp})

@app.route('/api/bet', methods=['POST'])
def place_bet():
    email, u = get_user()
    if not u: return jsonify({"success": False})
    amt = float(request.json.get('amount',0))
    if amt > u['real_balance']+u['bonus_balance']: return jsonify({"success": False, "error": "Insufficient"})
    if u['real_balance'] >= amt: u['real_balance'] -= amt
    else:
        rem = amt - u['real_balance']; u['real_balance']=0; u['bonus_balance']-=rem
    u['current_bet']=amt; u['total_bet']+=amt; house_stats["total_bets"]+=amt
    return jsonify({"success": True, "real": u['real_balance'], "bonus": u['bonus_balance']})

@app.route('/api/cashout', methods=['POST'])
def do_cashout():
    email, u = get_user()
    if not u: return jsonify({"success": False})
    bet=float(request.json.get('bet',0)); mult=float(request.json.get('multiplier',0)); win=round(bet*mult,2)
    if u['bonus_balance']>0: u['bonus_balance']+=win*0.3; u['real_balance']+=win*0.7
    else: u['real_balance']+=win
    u['total_won']+=win; u['current_bet']=0; house_stats["total_won"]+=win
    return jsonify({"success": True, "win": win, "real": u['real_balance'], "bonus": u['bonus_balance']})

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    email, u = get_user()
    if not u: return jsonify({"success": False})
    amt=float(request.json.get('amount',0)); total=u['real_balance']+u['bonus_balance']
    if u['bonus_balance']>0 and total < MIN_WITHDRAW_BONUS: return jsonify({"success": False, "error": f"BONUS ACTIVE: Need KES {MIN_WITHDRAW_BONUS} to withdraw bonus. You have {total:.0f}. Need {MIN_WITHDRAW_BONUS-total:.0f} more"})
    if u['bonus_balance']==0 and total < MIN_WITHDRAW_NOBONUS: return jsonify({"success": False, "error": f"Min withdraw KES {MIN_WITHDRAW_NOBONUS}. You have {total:.0f}"})
    if amt>total: return jsonify({"success": False, "error": "Insufficient"})
    fee=amt*WITHDRAW_FEE; pay=amt-fee
    if u['real_balance']>=amt: u['real_balance']-=amt
    else: rem=amt-u['real_balance']; u['real_balance']=0; u['bonus_balance']-=rem
    u['total_withdrawn']+=pay; house_stats["total_withdrawn"]+=pay; house_stats["total_fees"]+=fee
    return jsonify({"success": True, "msg": f"Withdraw KES {pay:.0f} (fee {fee:.0f}) sent! TEST", "total": u['real_balance']+u['bonus_balance']})

@app.route('/api/history')
def history(): return jsonify(crash_history)

@app.route('/api/live-bets')
def live_bets():
    bets=[]
    for _ in range(200):
        bets.append({"name": random.choice(FAKE_NAMES), "bet": random.choice([50,100,200,350,500,1000]), "cash": round(random.uniform(1.2,8),2)})
    return jsonify(bets[:40])

@app.route('/api/my-referral')
def my_ref():
    email,u = get_user()
    if not u: return jsonify({"success":False})
    link = f"https://pesafly.onrender.com/r/{u['my_ref_code']}"
    return jsonify({"code": u['my_ref_code'], "link": link, "count": len(u.get('referrals',[])), "earned": u.get('ref_bonus_earned',0)})

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    if request.json.get('password','') == ADMIN_PASS:
        session['is_admin']=True; return jsonify({"success": True})
    return jsonify({"success": False})

@app.route('/api/admin/stats')
def admin_stats():
    if not session.get('is_admin'): return jsonify({"success": False})
    return jsonify({"users": len(users), "house_profit": get_house_profit(), "total_dep": house_stats["total_deposited"], "total_with": house_stats["total_withdrawn"], "total_fees": house_stats["total_fees"], "total_bets": house_stats["total_bets"], "total_won": house_stats["total_won"]})

@app.route('/api/admin/users')
def admin_users():
    if not session.get('is_admin'): return jsonify({"success": False})
    data=[]
    for email,u in users.items():
        data.append({"email": email, "real": u['real_balance'], "bonus": u['bonus_balance'], "total": u['real_balance']+u['bonus_balance'], "deposited": u['total_deposited'], "code": u.get('my_ref_code',''), "refs": len(u.get('referrals',[])), "ref_earn": u.get('ref_bonus_earned',0), "claimed": u['bonus_claimed']})
    return jsonify(data)

if __name__ == '__main__':
    port=int(os.environ.get("PORT",5000))
    app.run(host='0.0.0.0', port=port)
