"""Fresh isolated workspaces/accounts only. Local Mailpit only; never external mail."""
import sys,time,json,re,secrets,copy,urllib.request,concurrent.futures
from pathlib import Path
from datetime import datetime,timezone,timedelta
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parent));sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'apps/api'))
from integration import Client
from db import connect
from security import digest
from reminders import scan_reminders
clients=[Client(),Client(),Client()];a,b,x=clients;workspaces=[];users=[];groups=0
now=lambda:datetime.now(timezone.utc)
def passed(s):
 global groups
 groups+=1;print('PASS:',s,flush=True)
def mail_token(email,purpose):
 for _ in range(30):
  with urllib.request.urlopen('http://mailpit:8025/api/v1/messages',timeout=3) as r:data=json.load(r)
  for m in data['messages']:
   if any(t['Address']==email for t in m['To']):
    with urllib.request.urlopen('http://mailpit:8025/api/v1/message/'+m['ID'],timeout=3) as r:text=json.load(r)['Text']
    match=re.search(r'#'+purpose+r':([A-Za-z0-9_-]+)',text)
    if match:return match.group(1)
  time.sleep(.2)
 raise AssertionError('Local catcher did not receive expected purpose mail')
try:
 for client in clients:
  wid=client.call('/auth/demo',{})['workspace_id'];workspaces.append(wid);users.append(client.call('/auth/me')['user_id'])
 w=workspaces[0];uid,bid=users[:2]
 with connect() as c:c.execute("INSERT INTO memberships(workspace_id,user_id,role) VALUES(%s,%s,'reviewer')",(w,bid))
 b.call('/auth/switch',{'workspace_id':w})
 contact={'id':str(uuid4()),'name':'Engineering support','category':'document processing','primary_contact':'primary@sample.invalid','backup_contact':'backup@sample.invalid','escalation_route':'Use the reviewed engineering escalation draft.','study_id':'CT-204','site_id':'SITE-104'}
 saved=a.call('/contacts',contact);assert a.call('/contacts',contact)['id']==saved['id'];x.call('/contacts',{**contact,'expected_version':1},404)
 with connect() as c:c.execute("UPDATE memberships SET role='analyst' WHERE workspace_id=%s AND user_id=%s",(w,bid))
 b.call('/contacts',{**contact,'expected_version':saved['version']},403);b.call('/cases/CASE-4/assignment',{'owner_id':bid},403)
 with connect() as c:c.execute("UPDATE memberships SET role='reviewer' WHERE workspace_id=%s AND user_id=%s",(w,bid))
 a.call('/contacts',{**contact,'expected_version':saved['version'],'study_id':'CT-101'},422)
 passed('scoped contact create/idempotency, current role enforcement and study/site validation')
 rid=a.run('CASE-4')['id'];item=a.call('/cases/CASE-4')['case']
 a.call('/cases/CASE-4/assignment',{'owner_id':uid,'due_at':(now()+timedelta(days=1)).isoformat(),'expected_updated_at':item['updated_at']})
 start=now()-timedelta(seconds=1)
 blocker={'id':str(uuid4()),'waiting_on':'Correct receipt','reason':'Waiting on exact upload receipt from engineering.','responsible_id':uid,'contact_id':contact['id'],'started_at':start.isoformat(),'follow_up_at':(now()-timedelta(milliseconds=100)).isoformat()}
 # Case already exists before start; create two overlapping active intervals.
 one=a.call('/cases/CASE-4/blockers',blocker);two=a.call('/cases/CASE-4/blockers',{**blocker,'id':str(uuid4()),'waiting_on':'Current binder verification'})
 assert a.call('/cases/CASE-4/blockers',blocker)['id']==one['id'];x.call('/cases/CASE-4/blockers',blocker,422);assert not x.call('/cases/CASE-4/blockers')['history'];x.call('/cases/CASE-4/blockers/'+one['id']+'/clear',{'reason':'Must not clear another workspace record.'},404)
 history=a.call('/cases/CASE-4/blockers');assert len(history['history'])==2 and history['blocked_seconds']<10
 with connect() as c:c.execute("UPDATE reminder_scans SET last_scan_at=now()-interval '2 hours' WHERE workspace_id=%s",(w,))
 scan_reminders();assert any('Blocker' in n['title'] for n in a.call('/notifications'))
 assert a.call('/waiting-queue')['blockers']
 passed('multiple scoped blockers, interval union, idempotency, overview queue and existing reminder channel')
 req={'id':str(uuid4()),'run_id':rid,'title':'Certificate receipt request','items':['Please send upload receipt DOC-ONE'],'contact_id':contact['id']}
 first=a.call('/cases/CASE-4/requests',req,201);assert a.call('/cases/CASE-4/requests',req,201)['id']==first['id']
 matches=a.call('/cases/CASE-4/request-matches',{'items':['Provide upload receipt for DOC-ONE']});assert matches and matches[0]['matched_items']
 a.call('/cases/CASE-4/requests',{**req,'id':str(uuid4()),'items':['Provide upload receipt for DOC-ONE']},409)
 override=a.call('/cases/CASE-4/requests',{**req,'id':str(uuid4()),'duplicate_reason':'Separate evidence scope required for second reviewer.'},201);assert override['duplicate_reason']
 a.call('/cases/CASE-4/requests',{**req,'id':str(uuid4()),'items':['Upload receipt DOC-TWO']},201)
 concurrent_req={**req,'id':str(uuid4()),'items':['Upload receipt DOC-THREE']}
 with concurrent.futures.ThreadPoolExecutor(2) as pool:copies=list(pool.map(lambda _:a.call('/cases/CASE-4/requests',concurrent_req,201),range(2)))
 assert copies[0]['id']==copies[1]['id']
 with connect() as c:assert c.execute('SELECT count(*) AS n FROM information_requests WHERE workspace_id=%s AND id=%s',(w,concurrent_req['id'])).fetchone()['n']==1
 passed('duplicate explanation/warning, reasoned override, genuine differences and replay prevention')
 item=a.call('/cases/CASE-4')['case'];handover={'id':str(uuid4()),'recipient_id':bid,'reason':'Incoming reviewer should continue the receipt checks.','expected_updated_at':item['updated_at']}
 h=a.call('/cases/CASE-4/handover',handover);assert a.call('/cases/CASE-4')['case']['owner_id']==uid
 a.call('/cases/CASE-4/assignment',{'owner_id':bid},409)
 assert a.call('/cases/CASE-4/handover')['outstanding']['blockers'];a.call('/cases/CASE-4/handover/'+h['id'],{'action':'accept','reason':'I checked outstanding evidence and accept ownership.'},403)
 decision={'action':'accept','reason':'I checked outstanding evidence and accept ownership.'}
 with concurrent.futures.ThreadPoolExecutor(2) as pool:answers=list(pool.map(lambda _:b.call('/cases/CASE-4/handover/'+h['id'],decision),range(2)))
 assert all(r['status']=='accepted' for r in answers);assert a.call('/cases/CASE-4')['case']['owner_id']==bid
 with connect() as c:assert c.execute("SELECT count(*) AS n FROM case_events WHERE workspace_id=%s AND case_id='CASE-4' AND event_type='handover_accepted'",(w,)).fetchone()['n']==1
 passed('owner retained until recipient accepts; concurrent acceptance is idempotent with single attributed audit')
 for action in ('decline','cancel'):
  item=a.call('/cases/CASE-4')['case'];h=a.call('/cases/CASE-4/handover',{**handover,'id':str(uuid4()),'recipient_id':uid,'expected_updated_at':item['updated_at']})
  a.call('/cases/CASE-4/handover/'+h['id'],{'action':action,'reason':'Explicit reviewer decision with reason retained.'});assert a.call('/cases/CASE-4')['case']['owner_id']==bid
 item=a.call('/cases/CASE-4')['case'];h=a.call('/cases/CASE-4/handover',{**handover,'id':str(uuid4()),'recipient_id':uid,'expected_updated_at':item['updated_at']})
 with connect() as c:c.execute('DELETE FROM memberships WHERE workspace_id=%s AND user_id=%s',(w,uid))
 a.call('/cases/CASE-4/handover/'+h['id'],decision,401)
 with connect() as c:c.execute("INSERT INTO memberships VALUES(%s,%s,'owner')",(w,uid))
 a.call('/cases/CASE-4/handover/'+h['id'],{'action':'cancel','reason':'Recipient membership must be current before handover.'})
 for bl in (one,two):a.call('/cases/CASE-4/blockers/'+bl['id']+'/clear',{'reason':'Current evidence received and explicitly verified.'})
 archived=a.call('/contacts',{**contact,'expected_version':saved['version'],'archived':True});assert not a.call('/contacts?study_id=CT-204&site_id=SITE-104')
 a.call('/cases/CASE-4/blockers',{**blocker,'id':str(uuid4())},422)
 package=a.call('/cases/CASE-4/package.json');assert package['handovers'] and package['blockers'] and package['waiting_time'];assert 'account_tokens' not in a.call('/export')['workflows']
 passed('decline/cancel retain owner, membership revocation, blocker clearing/history, archive safety and token-free exports')
 auth=Client();email='five-'+str(uuid4())+'@sample.invalid';password='original-password-long'
 new=auth.call('/auth/register',{'email':email,'name':'Five auth test','password':password},201);workspaces.append(new['workspace_id']);users.append(auth.call('/auth/me')['user_id']);verify=mail_token(email,'verify')
 auth.call('/auth/reset-password',{'token':verify,'password':'updated-password-long'},422)
 auth.call('/auth/verify-email',{'token':verify});assert auth.call('/auth/me')['email_verified_at'];auth.call('/auth/verify-email',{'token':verify},422)
 unknown=auth.call('/auth/recovery',{'email':'missing-'+str(uuid4())+'@sample.invalid'});known=auth.call('/auth/recovery',{'email':email});assert unknown==known;reset=mail_token(email,'reset')
 with connect() as c:
  assert c.execute('SELECT 1 FROM account_tokens WHERE token_hash=%s',(digest(reset),)).fetchone();assert not c.execute('SELECT 1 FROM account_tokens WHERE token_hash=%s',(reset,)).fetchone()
 auth.call('/auth/verify-email',{'token':reset},422);auth.call('/auth/reset-password',{'token':reset,'password':'updated-password-long'});auth.call('/auth/me',expected=401);auth.call('/auth/reset-password',{'token':reset,'password':'updated-password-long'},422)
 auth.call('/auth/login',{'email':email,'password':password},401);auth.call('/auth/login',{'email':email,'password':'updated-password-long'})
 expired=secrets.token_urlsafe(48)
 with connect() as c:c.execute("INSERT INTO account_tokens(token_hash,user_id,purpose,expires_at) VALUES(%s,%s,'reset',now()-interval '1 minute')",(digest(expired),users[-1]))
 auth.call('/auth/reset-password',{'token':expired,'password':'updated-password-long'},422)
 passed('local mail delivery, purpose/hash/expiry/single-use checks, generic recovery, reset revokes sessions and preserves login')
 auth.call('/auth/recovery',{'email':email});concurrent_token=mail_token(email,'reset')
 def reset_once(_):
  try:auth.call('/auth/reset-password',{'token':concurrent_token,'password':'concurrent-password-long'});return 200
  except AssertionError as e:return e.args[0][1]
 with concurrent.futures.ThreadPoolExecutor(2) as pool:statuses=sorted(pool.map(reset_once,range(2)))
 assert statuses==[200,422],statuses;auth.call('/auth/me',expected=401);auth.call('/auth/login',{'email':email,'password':'concurrent-password-long'})
 auth.call('/auth/recovery',{'email':email});auth.call('/auth/recovery',{'email':email},429)
 passed('concurrent token consumption succeeds once; recovery rate limit enforced; all sessions revoked again')
 print('PASS:',groups,'five-feature integration groups; all created test accounts/workspaces cleaned.')
finally:
 with connect() as c:
  for wid in workspaces:c.execute('DELETE FROM workspaces WHERE id=%s',(wid,))
  for uid in users:c.execute('DELETE FROM users WHERE id=%s',(uid,))
