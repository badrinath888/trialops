"""Workspace-scoped handover, blockers, directory and deterministic request matching."""
import re
from datetime import datetime,timezone
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException
from pydantic import Field,field_validator
from psycopg.types.json import Jsonb
from db import connect
from models import Model,Text,Assignment
from security import actor,require
from release_api import case,audit,member
router=APIRouter()

def current(c,a,write=False):
 row=c.execute('SELECT m.role FROM memberships m JOIN workspaces w ON w.id=m.workspace_id WHERE m.workspace_id=%s AND m.user_id=%s AND (w.expires_at IS NULL OR w.expires_at>now()) FOR SHARE OF m,w',(a['workspace_id'],a['user_id'])).fetchone()
 if not row:raise HTTPException(403,'Current workspace membership required.')
 if write:require({**a,'role':row['role']})
 return row['role']

def contact_ref(c,a,uid,study=None,site=None):
 if uid is None:return None
 r=c.execute('SELECT * FROM support_contacts WHERE workspace_id=%s AND id=%s FOR SHARE',(a['workspace_id'],uid)).fetchone()
 if not r or r['archived'] or (r['study_id'] and study and r['study_id']!=study) or (r['site_id'] and site and r['site_id']!=site):raise HTTPException(422,'Select an active contact relevant to this workspace/study/site.')
 return r

class Contact(Model):
 id:UUID;name:Text=Field(max_length=200);category:Text=Field(max_length=100)
 primary_contact:Text=Field(max_length=300);backup_contact:str=Field(default='',max_length=300);escalation_route:str=Field(default='',max_length=2000)
 study_id:str|None=Field(default=None,max_length=100);site_id:str|None=Field(default=None,max_length=100)
 archived:bool=False;expected_version:int|None=Field(default=None,ge=1)
@router.get('/contacts')
def contacts(study_id:str|None=None,site_id:str|None=None,include_archived:bool=False,a=Depends(actor)):
 with connect() as c:
  current(c,a)
  return c.execute('SELECT * FROM support_contacts WHERE workspace_id=%s AND (%s OR NOT archived) AND (%s::text IS NULL OR study_id IS NULL OR study_id=%s) AND (%s::text IS NULL OR site_id IS NULL OR site_id=%s) ORDER BY archived,name,id LIMIT 200',(a['workspace_id'],include_archived,study_id,study_id,site_id,site_id)).fetchall()
@router.post('/contacts')
def save_contact(body:Contact,a=Depends(actor)):
 with connect() as c:
  current(c,a,True)
  if body.site_id:
   s=c.execute('SELECT study_id FROM sites WHERE workspace_id=%s AND id=%s',(a['workspace_id'],body.site_id)).fetchone()
   if not s or not body.study_id or s['study_id']!=body.study_id:raise HTTPException(422,'Site must belong to the selected study.')
  if body.study_id and not c.execute('SELECT 1 FROM studies WHERE workspace_id=%s AND id=%s',(a['workspace_id'],body.study_id)).fetchone():raise HTTPException(422,'Study not in workspace.')
  old=c.execute('SELECT * FROM support_contacts WHERE workspace_id=%s AND id=%s FOR UPDATE',(a['workspace_id'],body.id)).fetchone()
  fields=('name','category','primary_contact','backup_contact','escalation_route','study_id','site_id','archived');values=[getattr(body,k) for k in fields]
  if old:
   if body.expected_version is None and all(old[k]==getattr(body,k) for k in fields):return old
   if body.expected_version!=old['version']:raise HTTPException(409,'Contact changed. Reload before saving.')
   row=c.execute('UPDATE support_contacts SET name=%s,category=%s,primary_contact=%s,backup_contact=%s,escalation_route=%s,study_id=%s,site_id=%s,archived=%s,version=version+1,actor_id=%s,updated_at=now() WHERE workspace_id=%s AND id=%s RETURNING *',(*values,a['user_id'],a['workspace_id'],body.id)).fetchone()
  else:
   if body.expected_version:raise HTTPException(404,'Contact not found.')
   if c.execute('SELECT count(*) AS n FROM support_contacts WHERE workspace_id=%s',(a['workspace_id'],)).fetchone()['n']>=200:raise HTTPException(422,'Directory limit reached (200).')
   row=c.execute('INSERT INTO support_contacts(name,category,primary_contact,backup_contact,escalation_route,study_id,site_id,archived,actor_id,workspace_id,id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *',(*values,a['user_id'],a['workspace_id'],body.id)).fetchone()
  c.execute('INSERT INTO support_contact_events(workspace_id,contact_id,actor_id,actor_name,event_type,payload) VALUES(%s,%s,%s,%s,%s,%s)',(a['workspace_id'],body.id,a['user_id'],a['name'],'contact_archived' if body.archived else 'contact_saved',freeze({'version':row['version'],'name':body.name})))
  return row

class Handover(Model):
 id:UUID;recipient_id:UUID;reason:Text=Field(min_length=10,max_length=2000)
 expected_updated_at:datetime
 _aware=field_validator('expected_updated_at')(Assignment.aware.__func__)
class HandoverDecision(Model):
 action:str=Field(pattern='^(accept|decline|cancel)$');reason:Text=Field(min_length=10,max_length=2000)

def summary(c,a,cid):
 return {'checks':c.execute("SELECT id,items,due_at FROM investigation_checks WHERE workspace_id=%s AND case_id=%s AND status='active'",(a['workspace_id'],cid)).fetchall(),'requests':c.execute("SELECT id,title,items,status,due_at,owner_id FROM information_requests WHERE workspace_id=%s AND case_id=%s AND status IN ('draft','requested')",(a['workspace_id'],cid)).fetchall(),'blockers':c.execute('SELECT * FROM case_blockers WHERE workspace_id=%s AND case_id=%s AND cleared_at IS NULL',(a['workspace_id'],cid)).fetchall()}
def freeze(value):
 import json
 return Jsonb(json.loads(json.dumps(value,default=str)))
@router.get('/cases/{cid}/handover')
def handovers(cid:str,a=Depends(actor)):
 with connect() as c:
  current(c,a);item=case(a,cid,c)
  return {'case':item,'outstanding':summary(c,a,cid),'history':c.execute('SELECT h.*,u.name AS recipient_name FROM case_handovers h JOIN users u ON u.id=h.recipient_id WHERE h.workspace_id=%s AND h.case_id=%s ORDER BY created_at DESC,id',(a['workspace_id'],cid)).fetchall()}
@router.post('/cases/{cid}/handover')
def start_handover(cid:str,body:Handover,a=Depends(actor)):
 with connect() as c:
  current(c,a,True);item=case(a,cid,c,True);member(c,a,body.recipient_id)
  old=c.execute('SELECT * FROM case_handovers WHERE workspace_id=%s AND id=%s',(a['workspace_id'],body.id)).fetchone()
  if old:
   if old['case_id']!=cid or old['recipient_id']!=body.recipient_id or old['reason']!=body.reason:raise HTTPException(409,'Handover ID reused with different input.')
   return old
  if item['status']!='open' or item['owner_id']==body.recipient_id:raise HTTPException(422,'Choose a different current member for an open case.')
  if item['updated_at']!=body.expected_updated_at:raise HTTPException(409,'Case changed. Reload handover.')
  if c.execute("SELECT 1 FROM case_handovers WHERE workspace_id=%s AND case_id=%s AND status='pending'",(a['workspace_id'],cid)).fetchone():raise HTTPException(409,'Cancel or complete the pending handover first.')
  row=c.execute('INSERT INTO case_handovers(workspace_id,id,case_id,sender_id,recipient_id,owner_at_creation,reason,summary) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *',(a['workspace_id'],body.id,cid,a['user_id'],body.recipient_id,item['owner_id'],body.reason,freeze({'case_deadline':item['due_at'],**summary(c,a,cid)}))).fetchone()
  audit(c,a,cid,'handover_requested',body.reason,payload={'handover_id':str(body.id),'recipient_id':str(body.recipient_id),'owner_retained':str(item['owner_id'])})
  return row
@router.post('/cases/{cid}/handover/{hid}')
def decide_handover(cid:str,hid:UUID,body:HandoverDecision,a=Depends(actor)):
 with connect() as c:
  role=current(c,a);item=case(a,cid,c,True)
  row=c.execute('SELECT * FROM case_handovers WHERE workspace_id=%s AND case_id=%s AND id=%s FOR UPDATE',(a['workspace_id'],cid,hid)).fetchone()
  if not row:raise HTTPException(404,'Handover not found.')
  recipient=row['recipient_id']==a['user_id']
  if (body.action in ('accept','decline') and not recipient) or (body.action=='cancel' and not (row['sender_id']==a['user_id'] or role=='owner')):raise HTTPException(403,'Only the recipient may accept/decline; sender or owner may cancel.')
  status={'accept':'accepted','decline':'declined','cancel':'cancelled'}[body.action]
  if row['status']!='pending':
   if row['status']==status and row['decided_by']==a['user_id'] and row['decision_reason']==body.reason:return row
   raise HTTPException(409,'Handover already decided.')
  if body.action=='accept':
   member(c,a,row['recipient_id']);member(c,a,row['sender_id'])
   if item['status']!='open' or item['owner_id']!=row['owner_at_creation']:raise HTTPException(409,'Case ownership/status changed; cancel and create a current handover.')
   c.execute('UPDATE cases SET owner_id=%s,updated_at=now() WHERE workspace_id=%s AND id=%s',(a['user_id'],a['workspace_id'],cid))
  saved=c.execute('UPDATE case_handovers SET status=%s,decision_reason=%s,decided_by=%s,decided_at=now() WHERE workspace_id=%s AND id=%s RETURNING *',(status,body.reason,a['user_id'],a['workspace_id'],hid)).fetchone()
  audit(c,a,cid,'handover_'+status,body.reason,payload={'handover_id':str(hid),'recipient_id':str(row['recipient_id'])})
  return saved

class Blocker(Model):
 id:UUID;waiting_on:Text=Field(max_length=300);reason:Text=Field(min_length=10,max_length=2000)
 responsible_id:UUID|None=None;contact_id:UUID|None=None
 started_at:datetime;follow_up_at:datetime
 _aware=field_validator('started_at','follow_up_at')(Assignment.aware.__func__)
class Clear(Model):
 reason:Text=Field(min_length=10,max_length=2000)

def blocked_seconds(rows,now):
 intervals=sorted((r['started_at'],min(r.get('cleared_at') or now,now)) for r in rows if r['started_at']<=now)
 total=0;start=end=None
 for left,right in intervals:
  if start is None:start,end=left,right
  elif left<=end:end=max(end,right)
  else:total+=(end-start).total_seconds();start,end=left,right
 if start is not None:total+=(end-start).total_seconds()
 return max(0,total)
@router.get('/cases/{cid}/blockers')
def blockers(cid:str,a=Depends(actor)):
 with connect() as c:
  current(c,a);item=case(a,cid,c);rows=c.execute('SELECT b.*,u.name AS responsible_name,t.name AS contact_name FROM case_blockers b LEFT JOIN users u ON u.id=b.responsible_id LEFT JOIN support_contacts t ON t.workspace_id=b.workspace_id AND t.id=b.contact_id WHERE b.workspace_id=%s AND b.case_id=%s ORDER BY started_at DESC,id',(a['workspace_id'],cid)).fetchall()
  return {'history':rows,'blocked_seconds':blocked_seconds(rows,item['resolved_at'] or datetime.now(timezone.utc)),'interpretation':'Union of overlapping blocked intervals; elapsed waiting time, not human effort.'}
@router.post('/cases/{cid}/blockers')
def add_blocker(cid:str,body:Blocker,a=Depends(actor)):
 with connect() as c:
  current(c,a,True);item=case(a,cid,c,True);member(c,a,body.responsible_id);contact_ref(c,a,body.contact_id,item['study_id'],item['site_id'])
  if not (body.responsible_id or body.contact_id):raise HTTPException(422,'Select a responsible member or directory contact.')
  if item['status']!='open' or not item['created_at']<=body.started_at<=datetime.now(timezone.utc) or body.follow_up_at<body.started_at:raise HTTPException(422,'Use a current open-case start time and follow-up after start.')
  old=c.execute('SELECT * FROM case_blockers WHERE workspace_id=%s AND id=%s',(a['workspace_id'],body.id)).fetchone()
  fields=('waiting_on','reason','responsible_id','contact_id','started_at','follow_up_at')
  if old:
   if old['case_id']!=cid or any(old[k]!=getattr(body,k) for k in fields):raise HTTPException(409,'Blocker ID reused with different input.')
   return old
  if c.execute('SELECT count(*) AS n FROM case_blockers WHERE workspace_id=%s AND case_id=%s',(a['workspace_id'],cid)).fetchone()['n']>=200:raise HTTPException(422,'Blocker history limit reached (200).')
  row=c.execute('INSERT INTO case_blockers(workspace_id,id,case_id,waiting_on,reason,responsible_id,contact_id,started_at,follow_up_at,actor_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *',(a['workspace_id'],body.id,cid,*[getattr(body,k) for k in fields],a['user_id'])).fetchone()
  audit(c,a,cid,'blocker_started',body.reason,payload={'blocker_id':str(body.id),'waiting_on':body.waiting_on,'follow_up_at':str(body.follow_up_at)})
  return row
@router.post('/cases/{cid}/blockers/{bid}/clear')
def clear_blocker(cid:str,bid:UUID,body:Clear,a=Depends(actor)):
 with connect() as c:
  current(c,a,True);case(a,cid,c,True)
  old=c.execute('SELECT * FROM case_blockers WHERE workspace_id=%s AND case_id=%s AND id=%s FOR UPDATE',(a['workspace_id'],cid,bid)).fetchone()
  if not old:raise HTTPException(404,'Blocker not found.')
  if old['cleared_at']:
   if old['clear_reason']==body.reason and old['cleared_by']==a['user_id']:return old
   raise HTTPException(409,'Blocker already cleared.')
  row=c.execute('UPDATE case_blockers SET cleared_at=now(),clear_reason=%s,cleared_by=%s WHERE workspace_id=%s AND id=%s RETURNING *',(body.reason,a['user_id'],a['workspace_id'],bid)).fetchone()
  audit(c,a,cid,'blocker_cleared',body.reason,payload={'blocker_id':str(bid)})
  return row
@router.get('/waiting-queue')
def waiting_queue(a=Depends(actor)):
 with connect() as c:
  current(c,a)
  return {'blockers':c.execute("SELECT b.*,c.title FROM case_blockers b JOIN cases c ON c.workspace_id=b.workspace_id AND c.id=b.case_id WHERE b.workspace_id=%s AND b.cleared_at IS NULL AND c.status='open' ORDER BY b.follow_up_at,b.id LIMIT 100",(a['workspace_id'],)).fetchall(),'handovers':c.execute("SELECT h.*,c.title FROM case_handovers h JOIN cases c ON c.workspace_id=h.workspace_id AND c.id=h.case_id WHERE h.workspace_id=%s AND h.status='pending' AND (h.recipient_id=%s OR h.sender_id=%s) ORDER BY h.created_at LIMIT 100",(a['workspace_id'],a['user_id'],a['user_id'])).fetchall()}

STOP={'please','send','provide','request','a','an','the','for','of','to','with','can','you','me','us','we','need'}
def evidence_words(text):return set(re.findall(r'[a-z0-9]+',text.lower()))-STOP
def same_evidence(left,right):
 a,b=evidence_words(left),evidence_words(right)
 ids=lambda t:set(re.findall(r'\b(?:DOC|SYNC|JOB|PROC|UPLOAD|CASE|KB|CT|SITE)-[\w-]+\b',t,re.I))
 if ids(left.lower())!=ids(right.lower()):return False
 return bool(a and b) and (a==b or len(a&b)/len(a|b)>=.85)
def duplicate_matches(c,a,item,items,exclude=None):
 rows=c.execute("SELECT r.id,r.case_id,r.title,r.items,r.status FROM information_requests r JOIN cases c ON c.workspace_id=r.workspace_id AND c.id=r.case_id WHERE r.workspace_id=%s AND c.study_id=%s AND c.site_id=%s AND c.status='open' AND r.status IN ('draft','requested') ORDER BY r.created_at DESC LIMIT 200",(a['workspace_id'],item['study_id'],item['site_id'])).fetchall()
 return [{**r,'explanation':'The normalized evidence terms and exact record identifiers match an open request.','matched_items':[x for x in items if any(same_evidence(x,y) for y in r['items'])]} for r in rows if r['id']!=exclude and any(same_evidence(x,y) for x in items for y in r['items'])]
class Duplicate(Model):
 items:list[str]=Field(min_length=1,max_length=30)
@router.post('/cases/{cid}/request-matches')
def preview_matches(cid:str,body:Duplicate,a=Depends(actor)):
 with connect() as c:current(c,a);return duplicate_matches(c,a,case(a,cid,c),body.items)
