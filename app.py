from flask import Flask, render_template, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import random, os, requests, string, json
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "pesafly-v18-permanent-db-2026")
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL", "sqlite:///pesafly.db")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- CONFIG ---
ADMIN_PASS = "PesaAdmin123"
WELCOME_BONUS = 1000
MIN_DEPOSIT_TO_UNLOCK = 350
MIN_WITHDRAW_NOBONUS = 500
MIN_WITHDRAW_BONUS = 3000
WITHDRAW_FEE = 0.10
REFERRAL_BONUS = 150

# PayHero
PAYHERO_URL = "https://backend.payhero.co.ke/api/v2/payments"
PAYHERO_USER = os.environ.get("PAYHERO_API_USERNAME")
PAYHERO_PASS = os.environ.get("PAYHERO_API_PASSWORD")
PAYHERO_CHANNEL = os.environ.get("PAYHERO_CHANNEL_ID", "13363")

# --- DB MODELS - PERMANENT ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), unique=True, nullable=False)  # UNIQUE blocks duplicate
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
    referrals = db.Column(db.Text, default="[]")  # JSON list
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
    if not email:
        return None, None
    u = User.query.filter_by(phone=email).first()
    return (email, u) if u else (None, None)

def generate_crash():
    hs = get_house()
    total_bets = db.session.query(db.func.sum(User.current_bet)).scalar() or 0
    if total_bets > 5000 and random.random() < 0.6:
        return round(random.uniform(1.0, 1.8),2)
    r = random.random()
    if r < 0.45: return round(random.uniform(1.0, 1.95),2)
    elif r < 0.80: return round(random.uniform(2.0, 5.0),2)
    elif r < 0.95: return round(random.uniform(5.0, 15.0),2)
    else: return round(random.uniform(15.0, 80.0),2)

# Init DB
with app.app_context():
    db.create_all()
    if not HouseStats.query.first():
        db.session.add(HouseStats())
        db.session.commit()
    if CrashHistory.query.count() == 0:
        for _ in range(25):
            db.session.add(CrashHistory(crash_value=round(random.uniform(1.2, 15),2)))
        db.session.commit()

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
    return jsonify({"status":"live","v":"V18-DB","house_profit":get_house_profit(),"users":User.query.count(),"has_keys": bool(PAYHERO_USER)})

# --- API ---
@app.route('/api/me')
def me():
    email, u = get_user_obj()
    if not u: return jsonify({"logged": False})
    can_claim = u.total_deposited >= MIN_DEPOSIT_TO_UNLOCK and not u.bonus_claimed
    return jsonify({"logged": True, "email": email, "real": u.real_balance, "bonus": u.bonus_balance, "total": u.real_balance+u.bonus_balance, "deposited": u.total_deposited, "bonus_locked": u.bonus_locked, "bonus_claimed": u.bonus_claimed, "can_claim": can_claim, "my_code": u.my_ref_code})

# FIXED AUTH - PERMANENT
@app.route('/api/auth', methods=['POST'])
def auth():
    data = request.json
    email = data.get('email','').lower().strip()
    pwd = data.get('password','')
    act = data.get('action','login')
    ref_code = data.get('referral','').strip().upper()

    if not email or not pwd:
        return jsonify({"success": False, "error": "Phone and password required"})

    existing = User.query.filter_by(phone=email).first()

    if act == 'register':
        if existing:
            return jsonify({"success": False, "error": "Account already exists! Please login."})
        
        my_code = gen_code()
        while User.query.filter_by(my_ref_code=my_code).first():
            my_code = gen_code()

        new_user = User(
            phone=email,
            password_hash=generate_password_hash(pwd),
            my_ref_code=my_code,
            referred_by=ref_code if ref_code else None,
            referrals="[]"
        )
        db.session.add(new_user)
        db.session.commit()
        session['email'] = email
        return jsonify({"success": True, "my_code": my_code})
    else:
        if not existing:
            return jsonify({"success": False, "error": "Account not found! Please register first."})
        if not check_password_hash(existing.password_hash, pwd):
            return jsonify({"success": False, "error": "Incorrect password! Try again."})
        session['email'] = email
        return jsonify({"success": True})

@app.route('/api/logout', methods=['POST'])
def logout(): session.clear(); return jsonify({"success": True})

@app.route('/api/deposit', methods=['POST'])
def deposit():
    email, u = get_user_obj()
    if not u: return jsonify({"success": False, "error": "Login first"})
    data = request.json
    amount = float(data.get('amount', 350))
    phone = data.get('phone','').strip()
    hs = get_house()

    # TEST MODE if no PayHero keys
    if not PAYHERO_USER or not PAYHERO_PASS:
        u.real_balance += amount
        u.total_deposited += amount
        hs.total_deposited += amount
        if u.total_deposited >= MIN_DEPOSIT_TO_UNLOCK: u.bonus_locked = False
        if u.referred_by and not u.ref_bonus_paid and u.total_deposited >= 350:
            owner = User.query.filter_by(my_ref_code=u.referred_by).first()
            if owner:
                owner.bonus_balance += REFERRAL_BONUS
                owner.ref_bonus_earned += REFERRAL_BONUS
                lst = json.loads(owner.referrals)
                lst.append(email)
                owner.referrals = json.dumps(lst)
                u.ref_bonus_paid = True
        db.session.commit()
        return jsonify({"success": True, "msg": f"TEST Added KES {amount}. Now CLAIM bonus!", "real": u.real_balance})

    if not phone: return jsonify({"success": False, "error": "Phone required"})
    if phone.startswith("0"): phone = "254"+phone[1:]
    if phone.startswith("7"): phone = "254"+phone
    payload = {"amount": amount, "phone_number": phone, "channel_id": int(PAYHERO_CHANNEL), "provider": "m-pesa", "external_reference": f"PESAF-{random.randint(1000,9999)}", "callback_url": os.environ.get("PAYHERO_CALLBACK_URL","https://pesafly.onrender.com/payhero/callback")}
    try:
        r = requests.post(PAYHERO_URL, json=payload, auth=(PAYHERO_USER, PAYHERO_PASS), timeout=20)
        res = r.json()
        if r.status_code in [200,201] or res.get("success"):
            u.real_balance += amount; u.total_deposited += amount; hs.total_deposited += amount
            if u.total_deposited >= MIN_DEPOSIT_TO_UNLOCK: u.bonus_locked = False
            if u.referred_by and not u.ref_bonus_paid and u.total_deposited >= 350:
                owner = User.query.filter_by(my_ref_code=u.referred_by).first()
                if owner:
                    owner.bonus_balance += REFERRAL_BONUS
                    owner.ref_bonus_earned += REFERRAL_BONUS
                    lst = json.loads(owner.referrals)
                    lst.append(email)
                    owner.referrals = json.dumps(lst)
                    u.ref_bonus_paid = True
            db.session.commit()
            return jsonify({"success": True, "msg": f"STK sent to {phone}! Enter PIN. Then CLAIM"})
        else:
            return jsonify({"success": False, "error": str(res)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/claim-bonus', methods=['POST'])
def claim_bonus():
    email, u = get_user_obj()
    if not u: return jsonify({"success": False})
    if u.bonus_claimed: return jsonify({"success": False, "error": "Already claimed"})
    if u.total_deposited < MIN_DEPOSIT_TO_UNLOCK: return jsonify({"success": False, "error": f"Deposit {MIN_DEPOSIT_TO_UNLOCK} first"})
    u.bonus_balance += WELCOME_BONUS; u.bonus_claimed = True; u.bonus_locked = False
    db.session.commit()
    return jsonify({"success": True, "msg": f"CLAIMED {WELCOME_BONUS}! Total KES {u.real_balance+u.bonus_balance}", "real": u.real_balance, "bonus": u.bonus_balance})

@app.route('/api/crash')
def get_crash():
    cp = generate_crash()
    db.session.add(CrashHistory(crash_value=cp))
    db.session.commit()
    # keep 30
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
    return jsonify({"success": True, "real": u.real_balance, "bonus": u.bonus_balance})

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
    return jsonify({"success": True, "win": win, "real": u.real_balance, "bonus": u.bonus_balance})

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    email, u = get_user_obj()
    if not u: return jsonify({"success": False})
    amt=float(request.json.get('amount',0)); total=u.real_balance+u.bonus_balance
    if u.bonus_balance>0 and total < MIN_WITHDRAW_BONUS: return jsonify({"success": False, "error": f"BONUS ACTIVE: Need KES {MIN_WITHDRAW_BONUS} to withdraw. You have {total:.0f}. Need {MIN_WITHDRAW_BONUS-total:.0f} more"})
    if u.bonus_balance==0 and total < MIN_WITHDRAW_NOBONUS: return jsonify({"success": False, "error": f"Min withdraw KES {MIN_WITHDRAW_NOBONUS}. You have {total:.0f}"})
    if amt>total: return jsonify({"success": False, "error": "Insufficient"})
    fee=amt*WITHDRAW_FEE; pay=amt-fee
    if u.real_balance>=amt: u.real_balance-=amt
    else: rem=amt-u.real_balance; u.real_balance=0; u.bonus_balance-=rem
    u.total_withdrawn+=pay
    hs = get_house(); hs.total_withdrawn+=pay; hs.total_fees+=fee
    db.session.commit()
    return jsonify({"success": True, "msg": f"Withdraw KES {pay:.0f} (fee {fee:.0f}) sent! TEST", "total": u.real_balance+u.bonus_balance})

@app.route('/api/history')
def history():
    hist = CrashHistory.query.order_by(CrashHistory.id.desc()).limit(25).all()
    vals = [h.crash_value for h in reversed(hist)]
    return jsonify(vals)

@app.route('/api/live-bets')
def live_bets():
    import string as _s
    names = ["Brian","Kevin","Faith","Sharon","Moses","Wanjiku","Otieno","Kamau","Njeri","Grace","Mutiso","John","Akinyi","Chebet","Njoroge"]
    bets=[]
    for _ in range(40):
        bets.append({"name": f"{random.choice(names)}{random.randint(10,999)}", "bet": random.choice([50,100,200,350,500,1000]), "cash": round(random.uniform(1.2,8),2)})
    return jsonify(bets)

@app.route('/api/my-referral')
def my_ref():
    email,u = get_user_obj()
    if not u: return jsonify({"success":False})
    link = f"https://pesafly.onrender.com/r/{u.my_ref_code}"
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
    return jsonify({"users": User.query.count(), "house_profit": get_house_profit(), "total_dep": hs.total_deposited, "total_with": hs.total_withdrawn, "total_fees": hs.total_fees, "total_bets": hs.total_bets, "total_won": hs.total_won})

@app.route('/api/admin/users')
def admin_users():
    if not session.get('is_admin'): return jsonify({"success": False})
    data=[]
    for u in User.query.all():
        refs = json.loads(u.referrals) if u.referrals else []
        data.append({"email": u.phone, "real": u.real_balance, "bonus": u.bonus_balance, "total": u.real_balance+u.bonus_balance, "deposited": u.total_deposited, "code": u.my_ref_code, "refs": len(refs), "ref_earn": u.ref_bonus_earned, "claimed": u.bonus_claimed})
    return jsonify(data)

if __name__ == '__main__':
    port=int(os.environ.get("PORT",5000))
    app.run(host='0.0.0.0', port=port)
