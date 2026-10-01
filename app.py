from flask import Flask, render_template, request, jsonify, session
import os, random, json
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'pesafly_company_2026_legit_key'

# In-memory DB for demo - Replace with real DB later
users = {}
history = [2.3, 1.2, 5.6, 3.4, 1.8, 10.2, 2.1]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/me')
def me():
    phone = session.get('phone')
    if not phone or phone not in users:
        return jsonify({'logged': False})
    u = users[phone]
    total = u['real'] + u['bonus'] + u['ref_bonus']
    return jsonify({
        'logged': True,
        'phone': phone,
        'real': u['real'],
        'bonus': u['bonus'],
        'ref_bonus': u['ref_bonus'],
        'total': total,
        'withdraw_limit': 500 if not u['first_done'] else 200,
        'first_deposit_done': u['first_done'],
        'bonus_claimed': u['bonus_claimed'],
        'ref_link': f"https://pesafly.onrender.com/?ref={phone}",
        'referrals': u['referrals'],
        'referral_earnings': len(u['referrals'])*50,
        'transactions': u['transactions'][-10:],
        'bets': u['bets'][-10:],
        'can_withdraw': total >= 200
    })@app.route('/api/auth', methods=['POST'])
def auth():
    data = request.json
    phone = data.get('phone','').strip()
    pwd = data.get('password','')
    ref = data.get('ref','')
    action = data.get('action','login')
    if not phone or len(phone)<10:
        return jsonify({'success':False,'error':'Enter valid M-Pesa 07...'})
    if action=='register':
        if phone in users:
            return jsonify({'success':False,'error':'Account exists, Login'})
        users[phone]={'real':0,'bonus':0,'ref_bonus':0,'first_done':False,'bonus_claimed':False,'referrals':[],'transactions':[],'bets':[],'password':pwd,'ref_by':ref}
        if ref and ref in users:
            users[ref]['referrals'].append(phone)
            users[ref]['ref_bonus']+=50
            users[ref]['transactions'].append({'type':'Referral Bonus','amount':50,'status':'Approved','time':str(datetime.now())})
        session['phone']=phone
        return jsonify({'success':True})
    else:
        if phone not in users or users[phone]['password']!=pwd:
            return jsonify({'success':False,'error':'Wrong phone/password'})
        session['phone']=phone
        return jsonify({'success':True})

@app.route('/api/deposit', methods=['POST'])
def deposit():
    phone=session.get('phone')
    if not phone: return jsonify({'success':False,'error':'Login first'})
    amt=float(request.json.get('amount',0))
    if amt<50: return jsonify({'success':False,'error':'Min deposit KES 50 - PesaFly Company'})
    u=users[phone]
    # LEGIT LOGIC: First deposit bonus 10% up to 100
    bonus=0
    if not u['first_done']:
        bonus=min(amt*0.10,100)
        u['first_done']=True
        u['bonus_claimed']=True
    u['real']+=amt
    u['bonus']+=bonus
    u['transactions'].append({'type':f'Deposit via PayHero - PesaFly Company','amount':amt+bonus,'status':'Approved','time':str(datetime.now())})
    if bonus>0:
        return jsonify({'success':True,'msg':f'✅ STK Sent! KES {amt} + Bonus {bonus} = {amt+bonus}. Pay to PesaFly Company - Check M-Pesa'})
    return jsonify({'success':True,'msg':f'✅ Deposit KES {amt} Approved - PesaFly Company - Secured by PayHero'})

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    phone=session.get('phone')
    if not phone: return jsonify({'success':False,'error':'Login'})
    amt=float(request.json.get('amount',0))
    u=users[phone]
    total=u['real']+u['bonus']+u['ref_bonus']
    if total<200: return jsonify({'success':False,'error':f'Need KES 200 to withdraw. You have {total}'})
    if amt>total: return jsonify({'success':False,'error':'Insufficient balance'})
    # Deduct real first
    if u['real']>=amt: u['real']-=amt
    else:
        rem=amt-u['real']; u['real']=0
        if u['bonus']>=rem: u['bonus']-=rem
        else: u['ref_bonus']-=(rem-u['bonus']); u['bonus']=0
    u['transactions'].append({'type':'Withdraw to M-Pesa','amount':-amt,'status':'Processing 30s - PesaFly Company','time':str(datetime.now())})
    return jsonify({'success':True,'msg':f'✅ Withdraw KES {amt} sent to {phone} via PesaFly Company - PayHero'})

@app.route('/api/crash')
def crash_api():
    r=random.random()
    if r<0.15: c=round(random.uniform(1,1.5),2)
    elif r<0.85: c=round(random.uniform(1.5,9),2)
    else: c=round(random.uniform(10,60),2)
    history.append(c)
    if len(history)>20: history.pop(0)
    return jsonify({'crash':c})

@app.route('/api/history')
def hist(): return jsonify(history[-15:])

@app.route('/api/bet', methods=['POST'])
def bet():
    phone=session.get('phone')
    if not phone: return jsonify({'success':False,'error':'Login'})
    amt=float(request.json.get('amount',0))
    u=users[phone]
    total=u['real']+u['bonus']+u['ref_bonus']
    if amt>total: return jsonify({'success':False,'error':'No balance - Deposit to PesaFly Company'})
    if u['real']>=amt: u['real']-=amt
    else:
        rem=amt-u['real']; u['real']=0
        if u['bonus']>=rem: u['bonus']-=rem
        else: u['ref_bonus']-=(rem-u['bonus']); u['bonus']=0
    u['bets'].append({'amount':amt,'multi':0,'status':'PLACED','win':0,'time':str(datetime.now())})
    return jsonify({'success':True})

@app.route('/api/cashout', methods=['POST'])
def cashout():
    phone=session.get('phone')
    if not phone: return jsonify({'success':False})
    bet_amt=float(request.json.get('bet',0))
    multi=float(request.json.get('multiplier',1))
    win=bet_amt*multi
    users[phone]['real']+=win
    if users[phone]['bets']: users[phone]['bets'][-1]={'amount':bet_amt,'multi':multi,'status':f'WON {multi:.2f}x','win':win,'time':str(datetime.now())}
    users[phone]['transactions'].append({'type':f'Win {multi:.2f}x','amount':win,'status':'Approved','time':str(datetime.now())})
    return jsonify({'success':True,'win':win})

@app.route('/api/set-ref', methods=['POST'])
def setref(): return jsonify({'success':True})

@app.route('/api/logout')
def logout(): session.pop('phone',None); return jsonify({'success':True})

@app.route('/api/forgot', methods=['POST'])
def forgot():
    phone=request.json.get('phone')
    newp=request.json.get('new_password')
    if phone in users: users[phone]['password']=newp; return jsonify({'success':True,'msg':'Password reset OK'})
    return jsonify({'success':False,'error':'Phone not found'})

if __name__=='__main__':
    port=int(os.environ.get('PORT',10000))
    app.run(host='0.0.0.0',port=port)
