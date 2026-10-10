"""Purpose-bound account tokens; plaintext exists only in memory and delivery."""
import os,secrets,smtplib,time
from datetime import datetime,timezone,timedelta
from email.message import EmailMessage
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Request
from pydantic import Field
from models import Model,Credentials
from db import connect
from security import actor,digest,password_hash,rate
router=APIRouter()
GENERIC={'message':'If an eligible account exists, recovery instructions will be delivered when email is configured.'}
class Recovery(Model):
 email:str=Field(min_length=5,max_length=254)
class Token(Model):
 token:str=Field(min_length=20,max_length=200)
class Reset(Token):
 password:str=Field(min_length=12,max_length=128)

def delivery_configured():return bool(os.getenv('SMTP_HOST') and os.getenv('MAIL_FROM'))
def deliver(email,token,purpose):
 if not delivery_configured():return False
 origin=os.getenv('APP_PUBLIC_URL','http://localhost:3001').rstrip('/')
 msg=EmailMessage();msg['From']=os.environ['MAIL_FROM'];msg['To']=email
 msg['Subject']='TrialOps password recovery' if purpose=='reset' else 'Verify your TrialOps email'
 # Fragment keeps tokens out of URL access logs/referrers; client removes it immediately.
 msg.set_content(f"Open {origin}/account-access#{purpose}:{token}\nThis single-use link expires. If you did not request it, ignore it.")
 for attempt in range(2):
  try:
   cls=smtplib.SMTP_SSL if os.getenv('SMTP_SSL')=='true' else smtplib.SMTP
   with cls(os.environ['SMTP_HOST'],int(os.getenv('SMTP_PORT','587')),timeout=5) as smtp:
    if os.getenv('SMTP_STARTTLS','true')=='true' and cls==smtplib.SMTP:smtp.starttls()
    if os.getenv('SMTP_USER'):smtp.login(os.environ['SMTP_USER'],os.getenv('SMTP_PASSWORD',''))
    smtp.send_message(msg)
   return True
  except (OSError,smtplib.SMTPException,ValueError):
   if attempt==0:time.sleep(.25)
 return False

def issue(uid,purpose):
 token=secrets.token_urlsafe(48)
 with connect() as c:
  u=c.execute('SELECT * FROM users WHERE id=%s AND NOT guest FOR UPDATE',(uid,)).fetchone()
  if not u:return False
  c.execute('UPDATE account_tokens SET used_at=now() WHERE user_id=%s AND purpose=%s AND used_at IS NULL',(uid,purpose))
  c.execute('INSERT INTO account_tokens(token_hash,user_id,purpose,expires_at) VALUES(%s,%s,%s,%s)',(digest(token),uid,purpose,datetime.now(timezone.utc)+timedelta(minutes=30 if purpose=='reset' else 1440)))
  c.execute('INSERT INTO account_events(user_id,kind) VALUES(%s,%s)',(uid,purpose+'_requested'))
 delivered=deliver(u['email'],token,purpose)
 with connect() as c:c.execute('INSERT INTO account_events(user_id,kind) VALUES(%s,%s)',(uid,'email_delivered' if delivered else 'email_unavailable'))
 return delivered

@router.get('/auth/delivery-status')
def status():return {'configured':delivery_configured(),'external_delivery_verified':False}
@router.post('/auth/recovery')
def recovery(body:Recovery,request:Request):
 email=body.email.strip().lower();rate('recovery-ip:'+request.headers.get('x-client-ip','unknown'),10,900);rate('recovery-email:'+email,3,900)
 with connect() as c:u=c.execute('SELECT id FROM users WHERE email=%s AND NOT guest',(email,)).fetchone()
 if u:issue(u['id'],'reset')
 return GENERIC
@router.post('/auth/verification')
def verification(a=Depends(actor)):
 rate('verification:'+str(a['user_id']),3,900)
 if a['guest']:raise HTTPException(422,'Sample accounts cannot verify email.')
 sent=issue(a['user_id'],'verify')
 return {'message':'Verification email requested.' if sent else 'Email delivery is not configured or unavailable. Existing login access is preserved.'}

def consume(token,purpose,password=None):
 hashed=digest(token)
 with connect() as c:
  t=c.execute('SELECT * FROM account_tokens WHERE token_hash=%s AND purpose=%s',(hashed,purpose)).fetchone()
  if not t:raise HTTPException(422,'Link is invalid, expired or already used.')
  # Same user-first lock order as issuance prevents reset/issuance deadlocks.
  c.execute('SELECT id FROM users WHERE id=%s FOR UPDATE',(t['user_id'],))
  used=c.execute('UPDATE account_tokens SET used_at=now() WHERE token_hash=%s AND purpose=%s AND used_at IS NULL AND expires_at>now() RETURNING user_id',(hashed,purpose)).fetchone()
  if not used:raise HTTPException(422,'Link is invalid, expired or already used.')
  if purpose=='reset':
   c.execute('UPDATE users SET password_hash=%s WHERE id=%s',(password_hash(password),used['user_id']))
   c.execute('DELETE FROM sessions WHERE user_id=%s',(used['user_id'],))
   c.execute("UPDATE account_tokens SET used_at=now() WHERE user_id=%s AND purpose='reset' AND used_at IS NULL",(used['user_id'],))
  else:c.execute('UPDATE users SET email_verified_at=now() WHERE id=%s',(used['user_id'],))
  c.execute('INSERT INTO account_events(user_id,kind) VALUES(%s,%s)',(used['user_id'],purpose+'_completed'))
 return {'message':'Password reset. Sign in again on all devices.' if purpose=='reset' else 'Email verified. Existing account access is unchanged.'}
@router.post('/auth/reset-password')
def reset(body:Reset,request:Request):
 rate('consume-ip:'+request.headers.get('x-client-ip','unknown'),20,900)
 return consume(body.token,'reset',body.password)
@router.post('/auth/verify-email')
def verify(body:Token,request:Request):
 rate('consume-ip:'+request.headers.get('x-client-ip','unknown'),20,900)
 return consume(body.token,'verify')
