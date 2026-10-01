from flask import Flask, render_template, request, jsonify, session
import os, random
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'pesafly_company_2026_key_12345'

users = {}
history = [2.1, 1.5, 3.2, 5.1, 1.1, 8.2, 2.3]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/me')
def me():
    try:
        phone = session.get('phone')
        if not phone or phone not in users:
            return jsonify({'logged':False})
        u = users[phone]
        total = u['real'] + u['bonus'] + u['ref_bonus']
        return jsonify({
            'logged': True, 'phone': phone,
            'real': u['real'], 'bonus': u['bonus'], 'ref_bonus': u['ref_bonus'], 'total': total,
            'withdraw_limit': 500 if not u['first_done'] else 200,
            'first_deposit_done': u['first_done'], 'bonus_claimed': u['bonus_claimed'],
            'ref_link': f"https://pesafly.onrender.com/?ref={phone}",
            'referrals': u['referrals'], 'referral_earnings': len(u['referrals'])*50,
            'transactions': u['transactions'][-20:], 'bets': u['bets'][-20:]
        })
    except Exception as e:
        return jsonify({'logged':False, 'error':str(e)})

@app.route('/api/auth', methods=['POST'])
def auth():
    try:
        data = request.get_json()
        if not data: return jsonify({'success':False,'error':'No data'})
        phone = str(data.get('phone','')).strip()
        pwd = str(data.get('password','')).strip()
        action = data.get('action','login')
        ref = data.get('ref','') or data.get('referral','')
        if len(phone)<9: return jsonify({'success':False,'error':'Enter valid 07...'})
        if len(pwd)<4: return jsonify({'success':False,'error':'Password min 4 chars'})
        if action=='register':
            if phone in users:
                return jsonify({'success':False,'error':'Phone exists! Login'})
            users[phone]={'real':0,'bonus':0,'ref_bonus':0,'first_done':False,'bonus_claimed':False,'referrals':[],'transactions':[],'bets':[],'password':pwd,'ref_by':ref}
            if ref and ref in users:
                users[ref]['referrals'].append(phone)
                users[ref]['ref_bonus']+=50
                users[ref]['transactions'].append({'type':'Referral Bonus','amount':50,'status':'Approved','time':str(datetime.now())[:19]})
            session['phone']=phone
            return jsonify({'success':True})
        else:
            if phone not in users: return jsonify({'success':False,'error':'No account, Register'})
            if users[phone]['password']!=pwd: return jsonify({'success':False,'error':'Wrong password'})
            session['phone']=phone
            return jsonify({'success':True})
    except Exception as e:
        return jsonify({'success':False,'error': f'Server error: {str(e)}'})

@app.route('/api/deposit', methods=['POST'])
def deposit():
    phone=session.get('phone')
    if not phone: return jsonify({'success':False,'error':'Login first'})
    try:
        amt=float(request.get_json().get('amount',0))
        if amt<50: return jsonify({'success':False,'error':'Min 50 - PesaFly Company'})
        u=users[phone]
        bonus=0
        if not u['first_done']:
            bonus=min(amt*0.10,100)
            u['first_done']=True
            u['bonus_claimed']=True
        u['real']+=amt
        u['bonus']+=bonus
        u['transactions'].append({'type':'Deposit PesaFly Company','amount':amt+bonus,'status':'Approved','time':str(datetime.now())[:19]})
        return jsonify({'success':True,'msg':f'STK sent! KES {amt} + Bonus {bonus} - PesaFly Company'})
    except Exception as e:
        return jsonify({'success':False,'error':str(e)})

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    phone=session.get('phone')
    if not phone: return jsonify({'success':False,'error':'Login'})
    amt=float(request.get_json().get('amount',0))
    u=users[phone]
    total=u['real']+u['bonus']+u['ref_bonus']
    if total<200: return jsonify({'success':False,'error':f'Need 200, you have {total}'})
    if amt>total: return jsonify({'success':False,'error':'Insufficient'})
    if u['real']>=amt: u['real']-=amt
    else:
        rem=amt-u['real']; u['real']=0
        if u['bonus']>=rem: u['bonus']-=rem
        else: u['ref_bonus']-=(rem-u['bonus']); u['bonus']=0
    u['transactions'].append({'type':'Withdraw M-Pesa','amount':-amt,'status':'Processing 30s','time':str(datetime.now())[:19]})
    return jsonify({'success':True})

@app.route('/api/crash')
def crash_api():
    r=random.random()
    if r<0.15: c=round(random.uniform(1,1.5),2)
    elif r<0.85: c=round(random.uniform(1.5,9),2)
    else: c=round(random.uniform(10,60),2)
    history.append(c)
    if len(history)>30: history.pop(0)
    return jsonify({'crash':c})

@app.route('/api/history')
def hist(): return jsonify(history[-15:])
@app.route('/api/bet', methods=['POST'])
def bet():
    phone=session.get('phone')
    if not phone: return jsonify({'success':False,'error':'Login'})
    amt=float(request.get_json().get('amount',0))
    u=users[phone]; total=u['real']+u['bonus']+u['ref_bonus']
    if amt>total: return jsonify({'success':False,'error':'No balance'})
    if u['real']>=amt: u['real']-=amt
    else:
        rem=amt-u['real']; u['real']=0
        if u['bonus']>=rem: u['bonus']-=rem
        else: u['ref_bonus']-=(rem-u['bonus']); u['bonus']=0
    u['bets'].append({'amount':amt,'multi':0,'status':'PLACED','win':0,'time':str(datetime.now())[:19]})
    return jsonify({'success':True})
@app.route('/api/cashout', methods=['POST'])
def cashout():
    phone=session.get('phone')
    if not phone: return jsonify({'success':False})
    bet_amt=float(request.get_json().get('bet',0)); multi=float(request.get_json().get('multiplier',1))
    win=bet_amt*multi; users[phone]['real']+=win
    if users[phone]['bets']: users[phone]['bets'][-1]={'amount':bet_amt,'multi':multi,'status':f'WON {multi:.2f}x','win':win,'time':str(datetime.now())[:19]}
    users[phone]['transactions'].append({'type':f'Win {multi:.2f}x','amount':win,'status':'Approved','time':str(datetime.now())[:19]})
    return jsonify({'success':True,'win':win})
@app.route('/api/set-ref', methods=['POST'])
def setref(): return jsonify({'success':True})
@app.route('/api/logout')
def logout(): session.pop('phone',None); return jsonify({'success':True})
@app.route('/api/forgot', methods=['POST'])
def forgot():
    d=request.get_json(); ph=d.get('phone'); np=d.get('new_password')
    if ph in users: users[ph]['password']=np; return jsonify({'success':True,'msg':'Reset OK'})
    return jsonify({'success':False,'error':'Phone not found'})

if __name__=='__main__':
    port=int(os.environ.get('PORT',10000))
    app.run(host='0.0.0.0',port=port)
