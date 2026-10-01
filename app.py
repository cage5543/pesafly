import os, random, string
from datetime import datetime
from flask import Flask, request, jsonify, session, render_template
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'pesafly-secret-2026-strong-key-123')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///pesafly.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

def gen_ref_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    real_balance = db.Column(db.Float, default=0.0)
    bonus_balance = db.Column(db.Float, default=0.0)
    deposited = db.Column(db.Float, default=0.0)
    bonus_claimed = db.Column(db.Boolean, default=False)
    referral_code = db.Column(db.String(10), unique=True, default=gen_ref_code)
    referred_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    referral_earnings = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class CrashHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    crash_value = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()
    if CrashHistory.query.count() == 0:
        for _ in range(20):
            r = random.random()
            if r < 0.5: c = random.uniform(1.01, 1.99)
            elif r < 0.85: c = random.uniform(2.0, 5.0)
            else: c = random.uniform(5.0, 50.0)
            db.session.add(CrashHistory(crash_value=round(c,2)))
        db.session.commit()

def get_current_user():
    uid = session.get('user_id')
    return User.query.get(uid) if uid else None

def generate_crash():
    r = random.random()
    if r < 0.45: crash = random.uniform(1.02, 1.99)
    elif r < 0.75: crash = random.uniform(2.0, 5.0)
    elif r < 0.92: crash = random.uniform(5.0, 15.0)
    else: crash = random.uniform(15.0, 100.0)
    return round(crash, 2)

@app.route('/')
def index():
    ref_code = request.args.get('ref', '')
    return render_template('index.html', ref_code=ref_code)

@app.route('/api/me')
def me():
    user = get_current_user()
    if not user:
        return jsonify({"logged": False})
    return jsonify({"logged": True, "phone": user.phone, "real": user.real_balance, "bonus": user.bonus_balance, "deposited": user.deposited, "bonus_claimed": user.bonus_claimed})

@app.route('/api/auth', methods=['POST'])
def auth():
    data = request.get_json()
    phone = data.get('email','').strip()
    password = data.get('password','').strip()
    action = data.get('action','login')
    referral_input = data.get('referral','').strip()

    if not phone or not password:
        return jsonify({"success": False, "error": "Phone and password required"})
    if len(password) < 4:
        return jsonify({"success": False, "error": "Password too short (min 4 chars)"})

    existing = User.query.filter_by(phone=phone).first()

    if action == 'register':
        if existing:
            return jsonify({"success": False, "error": "Account already exists! Please login instead."})
        hashed = generate_password_hash(password)
        new_user = User(phone=phone, password_hash=hashed)
        if referral_input:
            ref_user = User.query.filter_by(referral_code=referral_input.upper()).first()
            if ref_user:
                new_user.referred_by = ref_user.id
        db.session.add(new_user)
        db.session.commit()
        session['user_id'] = new_user.id
        return jsonify({"success": True})
    else:
        if not existing:
            return jsonify({"success": False, "error": "Account not found! Please register first."})
        if not check_password_hash(existing.password_hash, password):
            return jsonify({"success": False, "error": "Incorrect password! Try again."})
        session['user_id'] = existing.id
        return jsonify({"success": True})

@app.route('/api/deposit', methods=['POST'])
def deposit():
    user = get_current_user()
    if not user: return jsonify({"success": False, "error": "Login first"})
    amount = float(request.get_json().get('amount',0))
    if amount < 10: return jsonify({"success": False, "error": "Min KES 10"})
    user.real_balance += amount
    user.deposited += amount
    if user.referred_by:
        ref = User.query.get(user.referred_by)
        if ref:
            ref.real_balance += amount*0.10
            ref.referral_earnings += amount*0.10
    db.session.commit()
    return jsonify({"success": True, "msg": f"Deposited KES {amount}!"})

@app.route('/api/claim-bonus', methods=['POST'])
def claim_bonus():
    user = get_current_user()
    if not user: return jsonify({"success": False, "error": "Login first"})
    if user.bonus_claimed: return jsonify({"success": False, "error": "Already claimed"})
    if user.deposited < 350: return jsonify({"success": False, "error": "Deposit KES 350 first"})
    user.bonus_balance += 1000
    user.bonus_claimed = True
    db.session.commit()
    return jsonify({"success": True, "msg": "KES 1000 Bonus claimed!"})

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    user = get_current_user()
    if not user: return jsonify({"success": False, "error": "Login first"})
    amount = float(request.get_json().get('amount',0))
    total = user.real_balance + user.bonus_balance
    if user.bonus_claimed and total < 3000:
        return jsonify({"success": False, "error": "Need KES 3000 to withdraw after bonus"})
    if amount > total: return jsonify({"success": False, "error": f"Insufficient KES {total}"})
    if user.real_balance >= amount: user.real_balance -= amount
    else:
        rem = amount - user.real_balance
        user.real_balance = 0
        user.bonus_balance -= rem
    db.session.commit()
    return jsonify({"success": True, "msg": f"Withdraw KES {amount} requested!"})

@app.route('/api/crash')
def crash():
    value = generate_crash()
    db.session.add(CrashHistory(crash_value=value))
    db.session.commit()
    all_h = CrashHistory.query.order_by(CrashHistory.id.desc()).all()
    if len(all_h) > 50:
        for old in all_h[50:]: db.session.delete(old)
        db.session.commit()
    return jsonify({"crash": value})

@app.route('/api/history')
def history():
    last = CrashHistory.query.order_by(CrashHistory.id.desc()).limit(20).all()
    return jsonify([h.crash_value for h in reversed(last)])

@app.route('/api/bet', methods=['POST'])
def bet():
    user = get_current_user()
    if not user: return jsonify({"success": False, "error": "Login first"})
    amount = float(request.get_json().get('amount',0))
    total = user.real_balance + user.bonus_balance
    if amount > total: return jsonify({"success": False, "error": f"Insufficient KES {total}"})
    if user.real_balance >= amount: user.real_balance -= amount
    else:
        rem = amount - user.real_balance
        user.real_balance = 0
        user.bonus_balance -= rem
    db.session.commit()
    return jsonify({"success": True})

@app.route('/api/cashout', methods=['POST'])
def cashout():
    user = get_current_user()
    if not user: return jsonify({"success": False, "error": "Login first"})
    data = request.get_json()
    win = float(data.get('bet',0)) * float(data.get('multiplier',1))
    user.real_balance += win
    db.session.commit()
    return jsonify({"success": True, "win": win})

@app.route('/api/my-referral')
def my_referral():
    user = get_current_user()
    if not user: return jsonify({"code": None})
    count = User.query.filter_by(referred_by=user.id).count()
    link = f"{request.host_url.rstrip('/')}/?ref={user.referral_code}"
    return jsonify({"code": user.referral_code, "link": link, "count": count, "earned": round(user.referral_earnings,2)})

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    return jsonify({"success": True})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
