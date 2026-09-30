from flask import Flask, render_template, request, jsonify, session
import random, os
from datetime import datetime
from collections import deque

app = Flask(__name__)
app.secret_key = "pesafly-v13-9-referral"

users_db = {} # phone -> data
all_withdraw_requests = []
history = deque(maxlen=20)
history.extend([round(random.uniform(1.2, 15.0),2) for _ in range(10)])

def get_user():
    phone = session.get('phone')
    return (phone, users_db.get(phone)) if phone else (None, None)

@app.route('/')
def index(): return render_template('index.html')
@app.route('/admin')
def admin(): return render_template('admin.html')

@app.route('/api/auth', methods=['POST'])
def auth():
    data = request.json
    phone = ''.join(filter(str.isdigit, data.get('phone','')))
    password = data.get('password','').strip()
    ref = ''.join(filter(str.isdigit, data.get('ref','') or session.get('pending_ref','') or ''))
    action = data.get('action','login')
    if len(phone) < 9: return jsonify({"success": False, "error": "Enter valid M-Pesa 07..."})
    if not password: return jsonify({"success": False, "error": "Enter password"})
    if action == 'register':
        if phone in users_db: return jsonify({"success": False, "error": "Number exists - login"})
        # referral validation
        referrer = ref if ref in users_db and ref!= phone else None
        users_db[phone] = {
            "password": password, "real": 0.0, "bonus": 0.0, "ref_bonus": 0.0,
            "deposited": 0.0, "first_deposit_done": False,
            "bonus_claimed": False, "bonus_locked": True,
            "referrer": referrer, "referrals": [], "referral_earnings": 0.0,
            "created": datetime.now().isoformat(),
            "transactions": [{"type":"REGISTER","amount":0,"time":datetime.now().isoformat(),"status":"Success"}],
            "bets": []
        }
        if referrer:
            users_db[referrer]['referrals'].append(phone)
        session['phone'] = phone
        session.pop('pending_ref', None)
        return jsonify({"success": True})
    else:
        u = users_db.get(phone)
        if not u: return jsonify({"success": False, "error": "Number not found"})
        if u['password']!= password: return jsonify({"success": False, "error": "Wrong password"})
        session['phone'] = phone
        return jsonify({"success": True})

@app.route('/api/set-ref', methods=['POST'])
def set_ref():
    ref = ''.join(filter(str.isdigit, request.json.get('ref','')))
    if ref: session['pending_ref'] = ref
    return jsonify({"success": True})

@app.route('/api/forgot', methods=['POST'])
def forgot():
    phone = ''.join(filter(str.isdigit, request.json.get('phone','')))
    u = users_db.get(phone)
    if not u: return jsonify({"success": False, "error": "Number not found"})
    u['password'] = request.json.get('new_password','')
    return jsonify({"success": True, "msg": "Password reset!"})

@app.route('/api/me')
def me():
    phone, u = get_user()
    if not u: return jsonify({"logged": False})
    total = u['real'] + u['bonus'] + u['ref_bonus']
    # withdraw limit logic
    if u['bonus_claimed'] or u['ref_bonus']>0:
        limit = 10000
    else:
        limit = 200
    can_withdraw = total >= limit and (not u['bonus_locked'] if u['bonus_claimed'] else True)
    ref_link = f"{request.host_url}?ref={phone}"
    return jsonify({
        "logged": True, "phone": phone, "real": u['real'], "bonus": u['bonus'], "ref_bonus": u['ref_bonus'],
        "total": total, "deposited": u['deposited'], "first_deposit_done": u['first_deposit_done'],
        "bonus_claimed": u['bonus_claimed'], "bonus_locked": u['bonus_locked'],
        "withdraw_limit": limit, "can_withdraw": can_withdraw,
        "ref_link": ref_link, "referrals": u['referrals'], "referral_earnings": u['referral_earnings'],
        "transactions": u['transactions'][-30:][::-1], "bets": u['bets'][-20:][::-1]
    })

@app.route('/api/logout', methods=['POST'])
def logout(): session.pop('phone',None); return jsonify({"success": True})

@app.route('/api/crash')
def crash():
    r=random.random()
    c=round(random.uniform(1.0,1.5),2) if r<0.15 else round(random.uniform(1.5,10),2) if r<0.85 else round(random.uniform(10,100),2)
    history.append(c); return jsonify({"crash": c})
@app.route('/api/history')
def hist(): return jsonify(list(history))

@app.route('/api/bet', methods=['POST'])
def bet():
    phone, u = get_user()
    if not u: return jsonify({"success": False, "error": "Login"})
    amount=float(request.json.get('amount',0))
    if amount<10: return jsonify({"success": False, "error": "Min 10"})
    total=u['real']+u['bonus']+u['ref_bonus']
    if total<amount: return jsonify({"success": False, "error": "No balance - Deposit 199 to unlock bonus"})
    # deduct real first, then bonus, then ref_bonus
    if u['real']>=amount: u['real']-=amount
    elif u['real']+u['bonus']>=amount:
        remain=amount-u['real']; u['real']=0; u['bonus']-=remain
    else:
        remain=amount-u['real']-u['bonus']; u['real']=0; u['bonus']=0; u['ref_bonus']-=remain
    u['bets'].append({"type":"BET","amount":amount,"multi":0,"win":0,"time":datetime.now().isoformat(),"status":"LOST"})
    u['transactions'].append({"type":"BET","amount":-amount,"time":datetime.now().isoformat(),"status":"Success"})
    return jsonify({"success": True})

@app.route('/api/cashout', methods=['POST'])
def cashout():
    phone, u = get_user()
    if not u: return jsonify({"success": False})
    bet_amt=float(request.json.get('bet',0)); multi=float(request.json.get('multiplier',1)); win=bet_amt*multi
    u['real']+=win
    if u['bets']: u['bets'][-1].update({"multi":multi,"win":win,"status":f"WON {multi:.2f}x"})
    u['transactions'].append({"type":"WIN","amount":win,"time":datetime.now().isoformat(),"status":f"{multi:.2f}x"})
    return jsonify({"success": True, "win": win})

@app.route('/api/deposit', methods=['POST'])
def deposit():
    phone, u = get_user()
    if not u: return jsonify({"success": False, "error": "Login"})
    amt=float(request.json.get('amount',0))
    # FIRST DEPOSIT RULE: must be 199 to unlock bonus
    if not u['first_deposit_done']:
        if amt < 199: return jsonify({"success": False, "error": "First deposit must be 199 to unlock KES 1000 bonus"})
        u['real']+=amt
        u['bonus']+=1000.0
        u['bonus_claimed']=True
        u['bonus_locked']=False # unlock directly as you requested
        u['first_deposit_done']=True
        u['deposited']+=amt
        u['transactions'].append({"type":"FIRST DEPOSIT","amount":amt,"time":datetime.now().isoformat(),"status":"Success"})
        u['transactions'].append({"type":"WELCOME BONUS","amount":1000,"time":datetime.now().isoformat(),"status":"Unlocked"})
        # REFERRAL BONUS to referrer
        ref_phone = u.get('referrer')
        if ref_phone and ref_phone in users_db:
            ref_u = users_db[ref_phone]
            ref_u['ref_bonus']+=300.0
            ref_u['referral_earnings']+=300.0
            ref_u['transactions'].append({"type":f"REFERRAL BONUS from {phone}","amount":300,"time":datetime.now().isoformat(),"status":"Bonus - Need 10000 to withdraw"})
        return jsonify({"success": True, "msg": f"Deposited {amt} + 1000 Bonus = {amt+1000} Total"})
    else:
        if amt < 99: return jsonify({"success": False, "error": "Min deposit 99"})
        u['real']+=amt; u['deposited']+=amt
        u['transactions'].append({"type":"DEPOSIT","amount":amt,"time":datetime.now().isoformat(),"status":"Success"})
        return jsonify({"success": True})

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    phone, u = get_user()
    if not u: return jsonify({"success": False, "error": "Login"})
    amt=float(request.json.get('amount',0))
    total=u['real']+u['bonus']+u['ref_bonus']
    limit = 10000 if (u['bonus_claimed'] or u['ref_bonus']>0) else 200
    if total < limit: return jsonify({"success": False, "error": f"Need {limit} to withdraw. You have {total:.0f}. Keep playing!"})
    if amt < 200: return jsonify({"success": False, "error": "Min withdraw 200"})
    if amt > u['real']: return jsonify({"success": False, "error": "Withdraw only REAL balance. Play bonus first to convert to real"})
    u['real']-=amt
    req = {"id": len(all_withdraw_requests)+1, "phone": phone, "amount": amt, "time": datetime.now().isoformat(), "status": "PENDING"}
    all_withdraw_requests.append(req)
    u['transactions'].append({"type":"WITHDRAW REQUEST","amount":-amt,"time":datetime.now().isoformat(),"status":"PENDING - Admin Approval"})
    return jsonify({"success": True, "msg": f"KES {amt} request sent - Awaiting Admin to {phone}"})

@app.route('/api/admin-data')
def admin_data():
    return jsonify({
        "users": [{"phone":k,"real":v['real'],"bonus":v['bonus'],"ref_bonus":v['ref_bonus'],"deposited":v['deposited'],"referrer":v['referrer'],"referrals":len(v['referrals'])} for k,v in users_db.items()],
        "withdraws": all_withdraw_requests[::-1], "total_users": len(users_db)
    })

@app.route('/api/admin-approve', methods=['POST'])
def approve():
    wid=int(request.json.get('id',0))
    for r in all_withdraw_requests:
        if r['id']==wid: r['status']="APPROVED"
    return jsonify({"success": True})

if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=True)