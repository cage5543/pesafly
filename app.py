from flask import Flask, render_template, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import random, os, requests, string, json
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "pesafly-v21-strong-pass-2026")
db_url = os.environ.get("DATABASE_URL", "sqlite:///pesafly.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

ADMIN_PASS = os.environ.get("ADMIN_PASS", "PesaAdmin123")
WELCOME_BONUS = 1000
MIN_DEPOSIT_TO_UNLOCK = 350
MIN_WITHDRAW_NOBONUS = 500
MIN_WITHDRAW_BONUS = 3000
WITHDRAW_FEE = 0.10
REFERRAL_BONUS = 150
MANUAL_TILL = os.environ.get("MANUAL_TILL", "1242837")

PAYHERO_URL = "https://backend.payhero.co.ke/api/v2/payments"
PAYHERO_USER = os.environ.get("PAYHERO_API_USERNAME")
PAYHERO_PASS = os.environ.get("PAYHERO_API_PASSWORD")
PAYHERO_CHANNEL = os.environ.get("PAYHERO_CHANNEL_ID", "13363")
CALLBACK_URL = os.environ.get("PAYHERO_CALLBACK_URL", "https://pesafly.onrender.com/api/payhero/callback")

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    real_balance = db.Column(db.Float, default=0.0)
    bonus_balance = db.Column(db.Float, default=0.0)
    bonus_locked = db.Column(db.Boolean, default=True)
    bonus_claimed = db.Column(db.Boolean, default=False)
    total_deposited = db.Column(db.Float, default=0.0)
    total_withdrawn = db.Column(db.Float, default=0.0)
    total_bet = db.Column(db.Float, default=0.0)
    total_won = db.Column(db.Float, default=0.0)
    current_bet = db.Column(db.Float, default=0.0)
    my_ref_code = db.Column(db.String(10), unique=True)
    referred_by = db.Column(db.String(10), nullable=True)
    referrals = db.Column(db.Text, default="[]")
    ref_bonus_earned = db.Column(db.Float, default=0.0)
    ref_bonus_paid = db.Column(db.Boolean, default=False)
    created = db.Column(db.DateTime, default=datetime.utcnow)

class CrashHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    crash_value = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class HouseStats(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    total_deposited = db.Column(db.Float, default=0.0)
    total_withdrawn = db.Column(db.Float, default=0.0)
    total_fees = db.Column(db.Float, default=0.0)
    total_bets = db.Column(db.Float, default=0.0)
    total_won = db.Column(db.Float, default=0.0)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20))
    mpesa_phone = db.Column(db.String(20))
    amount = db.Column(db.Float)
    type = db.Column(db.String(20))
    status = db.Column(db.String(20), default="pending")
    external_ref = db.Column(db.String(100), unique=True)
    mpesa_code = db.Column(db.String(50), nullable=True)
    created = db.Column(db.DateTime, default=datetime.utcnow)

def gen_code():
    return ''.join(random.choices(string.ascii_uppercase+string.digits, k=6))
def get_house():
    hs = HouseStats.query.first()
    if not hs:
        hs = HouseStats()
        db.session.add(hs)
        db.session.commit()
    return hs
def get_house_profit():
    hs = get_house()
    return hs.total_deposited - hs.total_withdrawn + hs.total_fees + (hs.total_bets - hs.total_won)
def get_user_obj():
    email = session.get('email')
    if not email: return None, None
    u = User.query.filter_by(phone=email).first()
    return (email, u) if u else (None, None)
def generate_crash():
    total_bets = db.session.query(db.func.sum(User.current_bet)).scalar() or 0
    if total_bets > 5000 and random.random() < 0.6:
        return round(random.uniform(1.0, 1.8),2)
    r = random.random()
    if r < 0.45: return round(random.uniform(1.0, 1.95),2)
    elif r < 0.80: return round(random.uniform(2.0, 5.0),2)
    elif r < 0.95: return round(random.uniform(5.0, 15.0),2)
    else: return round(random.uniform(15.0, 80.0),2)
def credit_user(user_obj, amount):
    user_obj.real_balance += amount
    user_obj.total_deposited += amount
    hs = get_house()
    hs.total_deposited += amount
    if user_obj.total_deposited >= MIN_DEPOSIT_TO_UNLOCK:
        user_obj.bonus_locked = False
    if user_obj.referred_by and not user_obj.ref_bonus_paid and user_obj.total_deposited >= 350:
        owner = User.query.filter_by(my_ref_code=user_obj.referred_by).first()
        if owner:
            owner.bonus_balance += REFERRAL_BONUS
            owner.ref_bonus_earned += REFERRAL_BONUS
            lst = json.loads(owner.referrals) if owner.referrals else []
            lst.append(user_obj.phone)
            owner.referrals = json.dumps(lst)
            user_obj.ref_bonus_paid = True

with app.app_context():
    db.create_all()
    if not HouseStats.query.first():
        db.session.add(HouseStats())
        db.session.commit()
    if CrashHistory.query.count() == 0:
        for _ in range(25):
            db.session.add(CrashHistory(crash_value=round(random.uniform(1.2, 15),2)))
        db.session.commit()

@app.route('/')
def home():
    ref = request.args.get('ref', '').upper()
    return render_template('index.html', ref_code=ref, manual_till=MANUAL_TILL)
@app.route('/r/<code>')
def ref_redirect(code):
    return render_template('index.html', ref_code=code.upper(), manual_till=MANUAL_TILL)
@app.route('/admin')
def admin_page(): return render_template('admin.html')
@app.route('/health')
def health():
    return jsonify({"status":"live","v":"V21-STRONG","till":MANUAL_TILL,"channel":PAYHERO_CHANNEL,"users":User.query.count(),"profit":get_house_profit(),"has_keys":bool(PAYHERO_USER and PAYHERO_PASS)})

@app.route('/api/me')
def me():
    email, u = get_user_obj()
    if not u: return jsonify({"logged": False})
    can_claim = u.total_deposited >= MIN_DEPOSIT_TO_UNLOCK and not u.bonus_claimed
    return jsonify({"logged": True, "email": email, "real": u.real_balance, "bonus": u.bonus_balance, "total": u.real_balance+u.bonus_balance, "deposited": u.total_deposited, "bonus_locked": u.bonus_locked, "bonus_claimed": u.bonus_claimed, "can_claim": can_claim, "my_code": u.my_ref_code})

# ===== STRONG PASSWORD & LOGIN RULES LIKE PREVIOUS =====
@app.route('/api/auth', methods=['POST'])
def auth():
    data = request.json
    email = data.get('email','').lower().strip()
    pwd = data.get('password','')
    act = data.get('action','login')
    ref_code = data.get('referral','').strip().upper()
    
    # RULE 1: Required fields
    if not email or not pwd:
        return jsonify({"success": False, "error": "Phone and password required"})
    # RULE 2: Phone validation
    if len(email) < 9:
        return jsonify({"success": False, "error": "Enter valid phone number"})
    # RULE 3: Password strength
    if len(pwd) < 4:
        return jsonify({"success": False, "error": "Password must be at least 4 characters"})
    if len(pwd) > 30:
        return jsonify({"success": False, "error": "Password too long (max 30)"})
    
    existing = User.query.filter_by(phone=email).first()
    
    if act == 'register':
        # RULE 4: No duplicate accounts
        if existing:
            return jsonify({"success": False, "error": "Account already exists! Please login."})
        # RULE 5: Referral code check (if provided, must exist)
        if ref_code:
            ref_owner = User.query.filter_by(my_ref_code=ref_code).first()
            if not ref_owner and ref_code != "":
                # Allow registration even if ref invalid, but warn - or block? We allow for now
                pass
        my_code = gen_code()
        while User.query.filter_by(my_ref_code=my_code).first():
            my_code = gen_code()
        new_user = User(phone=email, password_hash=generate_password_hash(pwd), my_ref_code=my_code, referred_by=ref_code if ref_code else None, referrals="[]")
        db.session.add(new_user)
        db.session.commit()
        session['email'] = email
        return jsonify({"success": True, "my_code": my_code})
    else:
        # LOGIN RULES
        if not existing:
            return jsonify({"success": False, "error": "Account not found! Please register first."})
        if not check_password_hash(existing.password_hash, pwd):
            return jsonify({"success": False, "error": "Incorrect password! Try again."})
        session['email'] = email
        return jsonify({"success": True})

@app.route('/api/logout', methods=['POST'])
def logout(): session.clear(); return jsonify({"success": True})
@app.route('/api/config')
def get_config():
    return jsonify({"manual_till": MANUAL_TILL, "channel_id": PAYHERO_CHANNEL, "stk_enabled": bool(PAYHERO_USER and PAYHERO_PASS)})

@app.route('/api/deposit/stk', methods=['POST'])
def deposit_stk():
    email, u = get_user_obj()
    if not u: return jsonify({"success": False, "error": "Login first"})
    amount = float(request.json.get('amount', 350))
    phone = request.json.get('phone','').strip()
    if amount < 10: return jsonify({"success": False, "error": "Min 10"})
    if not PAYHERO_USER or not PAYHERO_PASS:
        return jsonify({"success": False, "error": "STK not configured, use Manual"})
    if phone.startswith("0"): phone = "254"+phone[1:]
    if phone.startswith("+"): phone = phone[1:]
    if phone.startswith("7"): phone = "254"+phone
    ext_ref = f"STK-{random.randint(100000,999999)}"
    payload = {"amount": amount, "phone_number": phone, "channel_id": int(PAYHERO_CHANNEL), "provider": "m-pesa", "external_reference": ext_ref, "callback_url": CALLBACK_URL}
    try:
        r = requests.post(PAYHERO_URL, json=payload, auth=(PAYHERO_USER, PAYHERO_PASS), timeout=25)
        res = r.json()
        tr = Transaction(phone=email, mpesa_phone=phone, amount=amount, type="deposit_stk", status="pending", external_ref=ext_ref)
        db.session.add(tr)
        db.session.commit()
        if r.status_code in [200,201] or res.get("success") or res.get("status") == "QUEUED":
            return jsonify({"success": True, "msg": f"STK sent to {phone}! Enter PIN. Auto-credit."})
        else:
            return jsonify({"success": False, "error": str(res)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/deposit/manual', methods=['POST'])
def deposit_manual():
    email, u = get_user_obj()
    if not u: return jsonify({"success": False, "error": "Login first"})
    amount = float(request.json.get('amount', 0))
    mpesa_code = request.json.get('mpesa_code','').strip().upper()
    if amount < 10: return jsonify({"success": False, "error": "Min 10"})
    if not mpesa_code or len(mpesa_code) < 5:
        return jsonify({"success": False, "error": "Enter M-Pesa code e.g QGH7..."})
    if Transaction.query.filter_by(mpesa_code=mpesa_code).first():
        return jsonify({"success": False, "error": "Code already used!"})
    ext_ref = f"MAN-{mpesa_code}-{random.randint(100,999)}"
    credit_user(u, amount)
    tr = Transaction(phone=email, amount=amount, type="deposit_manual", status="success", external_ref=ext_ref, mpesa_code=mpesa_code)
    db.session.add(tr)
    db.session.commit()
    return jsonify({"success": True, "msg": f"Manual KES {amount} auto-approved! Code {mpesa_code} credited."})

@app.route('/api/deposit', methods=['POST'])
def deposit_old():
    if PAYHERO_USER and PAYHERO_PASS:
        return deposit_stk()
    else:
        return deposit_manual()

@app.route('/api/payhero/callback', methods=['POST'])
def payhero_callback():
    data = request.get_json()
    try:
        success = data.get("success") or (data.get("response", {}).get("ResultCode") == 0) or data.get("status") == "SUCCESS"
        ext_ref = data.get("external_reference") or data.get("ExternalReference") or data.get("response", {}).get("ExternalReference")
        if success and ext_ref:
            tr = Transaction.query.filter_by(external_ref=ext_ref).first()
            if tr and tr.status == "pending":
                u = User.query.filter_by(phone=tr.phone).first()
                if u:
                    credit_user(u, tr.amount)
                    tr.status = "success"
                    db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        print(e)
        return jsonify({"success": True})

@app.route('/api/claim-bonus', methods=['POST'])
def claim_bonus():
    email, u = get_user_obj()
    if not u: return jsonify({"success": False})
    if u.bonus_claimed: return jsonify({"success": False, "error": "Already claimed"})
    if u.total_deposited < MIN_DEPOSIT_TO_UNLOCK: return jsonify({"success": False, "error": f"Deposit {MIN_DEPOSIT_TO_UNLOCK} first"})
    u.bonus_balance += WELCOME_BONUS; u.bonus_claimed = True; u.bonus_locked = False
    db.session.commit()
    return jsonify({"success": True, "msg": f"CLAIMED {WELCOME_BONUS}!"})

@app.route('/api/crash')
def get_crash():
    cp = generate_crash()
    db.session.add(CrashHistory(crash_value=cp))
    db.session.commit()
    all_h = CrashHistory.query.order_by(CrashHistory.id.desc()).all()
    if len(all_h) > 30:
        for old in all_h[30:]:
            db.session.delete(old)
        db.session.commit()
    return jsonify({"crash": cp})

@app.route('/api/bet', methods=['POST'])
def place_bet():
    email, u = get_user_obj()
    if not u: return jsonify({"success": False})
    amt = float(request.json.get('amount',0))
    if amt > u.real_balance+u.bonus_balance: return jsonify({"success": False, "error": "Insufficient"})
    if u.real_balance >= amt: u.real_balance -= amt
    else:
        rem = amt - u.real_balance; u.real_balance=0; u.bonus_balance-=rem
    u.current_bet=amt; u.total_bet+=amt
    hs = get_house(); hs.total_bets+=amt
    db.session.commit()
    return jsonify({"success": True})

@app.route('/api/cashout', methods=['POST'])
def do_cashout():
    email, u = get_user_obj()
    if not u: return jsonify({"success": False})
    bet=float(request.json.get('bet',0)); mult=float(request.json.get('multiplier',0)); win=round(bet*mult,2)
    if u.bonus_balance>0: u.bonus_balance+=win*0.3; u.real_balance+=win*0.7
    else: u.real_balance+=win
    u.total_won+=win; u.current_bet=0
    hs = get_house(); hs.total_won+=win
    db.session.commit()
    return jsonify({"success": True, "win": win})

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    email, u = get_user_obj()
    if not u: return jsonify({"success": False})
    amt=float(request.json.get('amount',0)); total=u.real_balance+u.bonus_balance
    if u.bonus_balance>0 and total < MIN_WITHDRAW_BONUS: return jsonify({"success": False, "error": f"BONUS ACTIVE: Need KES {MIN_WITHDRAW_BONUS}. Have {total:.0f}"})
    if u.bonus_balance==0 and total < MIN_WITHDRAW_NOBONUS: return jsonify({"success": False, "error": f"Min withdraw KES {MIN_WITHDRAW_NOBONUS}"})
    if amt>total: return jsonify({"success": False, "error": "Insufficient"})
    if amt < 100: return jsonify({"success": False, "error": "Min withdraw 100"})
    fee=amt*WITHDRAW_FEE; pay=amt-fee
    if u.real_balance>=amt: u.real_balance-=amt
    else: rem=amt-u.real_balance; u.real_balance=0; u.bonus_balance-=rem
    u.total_withdrawn+=pay
    hs = get_house(); hs.total_withdrawn+=pay; hs.total_fees+=fee
    tr = Transaction(phone=email, amount=pay, type="withdraw", status="pending_manual", external_ref=f"W-{random.randint(100000,999999)}")
    db.session.add(tr)
    db.session.commit()
    return jsonify({"success": True, "msg": f"Withdraw KES {pay:.0f} (fee {fee:.0f}) pending! Admin will send."})

@app.route('/api/history')
def history():
    hist = CrashHistory.query.order_by(CrashHistory.id.desc()).limit(25).all()
    return jsonify([h.crash_value for h in reversed(hist)])

@app.route('/api/my-referral')
def my_ref():
    email,u = get_user_obj()
    if not u: return jsonify({"success":False})
    link = f"https://{request.host}/r/{u.my_ref_code}"
    count = len(json.loads(u.referrals)) if u.referrals else 0
    return jsonify({"code": u.my_ref_code, "link": link, "count": count, "earned": u.ref_bonus_earned})

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    if request.json.get('password','') == ADMIN_PASS:
        session['is_admin']=True; return jsonify({"success": True})
    return jsonify({"success": False})

@app.route('/api/admin/stats')
def admin_stats():
    if not session.get('is_admin'): return jsonify({"success": False})
    hs = get_house()
    return jsonify({"users": User.query.count(), "house_profit": get_house_profit(), "total_dep": hs.total_deposited, "total_with": hs.total_withdrawn, "total_fees": hs.total_fees, "pending_withdrawals": Transaction.query.filter_by(type="withdraw", status="pending_manual").count()})

@app.route('/api/admin/withdrawals')
def admin_withdrawals():
    if not session.get('is_admin'): return jsonify({"success": False})
    pend = Transaction.query.filter_by(type="withdraw", status="pending_manual").order_by(Transaction.id.desc()).all()
    return jsonify([{"id": t.id, "phone": t.phone, "amount": t.amount, "date": str(t.created)} for t in pend])

@app.route('/api/admin/complete-withdrawal', methods=['POST'])
def complete_withdrawal():
    if not session.get('is_admin'): return jsonify({"success": False})
    tid = request.json.get('id')
    tr = Transaction.query.get(tid)
    if not tr: return jsonify({"success": False})
    tr.status = 'success'
    db.session.commit()
    return jsonify({"success": True, "msg": f"Withdrawal KES {tr.amount} to {tr.phone} marked PAID - Now send via M-Pesa!"})

if __name__ == '__main__':
    port=int(os.environ.get("PORT",5000))
    app.run(host='0.0.0.0', port=port)
