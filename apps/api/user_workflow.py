"""Deterministic personal guidance and restricted, unsent text-only response links."""
import hashlib,json,secrets,time,threading
from collections import OrderedDict,deque
from datetime import datetime,timezone,timedelta
from uuid import UUID,uuid4
from fastapi import APIRouter,Depends,HTTPException,Request,Response
from pydantic import Field,field_validator
from psycopg.types.json import Jsonb
from db import connect
from models import Model,Text
from security import actor,digest,rate,require
from five_features import current,contact_ref
from release_api import case,audit,row_version
router=APIRouter()
now=lambda:datetime.now(timezone.utc)
ATTRIBUTION='External link holder; identity not verified'

def action(cid,key,label,reason,**extra):
 return {'case_id':cid,'action':key,'label':label,'reason':reason,'href':'/workspace/cases/'+cid,**extra}

def guidance(item,runs,checks,requests,responses,evidence,jobs,blockers,cycle_start,role):
 cid=item['id'];write=role in ('owner','reviewer');actions=[];warnings=[]
 pending=any(r['status']=='pending' and any(q['id']==r.get('request_id') and q['status']=='requested' for q in requests) for r in responses)
 if item['status']!='open':return {'primary':None,'actions':[],'blockers':['Case is resolved. Reopening is a separate reviewed action.']}
 if jobs:warnings.append('An investigation is queued or running. Wait for its saved findings.')
 else:actions.append(action(cid,'investigate','Run investigation','Assess current selected procedures and saved records.'))
 if runs:actions.insert(0,action(cid,'findings','Review findings','A saved investigation is available; human approval is separate.'))
 if write and any(r['decision']=='pending' for r in runs):actions.insert(0,action(cid,'findings','Review findings','Saved findings await your review.'))
 if write and any(ch['status']=='draft' for ch in checks):actions.insert(0,action(cid,'checks','Review and activate suggested checks','Draft checks require human review before activation.'))
 if write and any(ch['status']=='active' and any(i['state'] in ('not_checked','needs_follow_up') for i in ch['items']) for ch in checks):actions.insert(0,action(cid,'checks','Complete outstanding checks','Active checks still need recorded evidence or follow-up.'))
 if write and pending:actions.insert(0,action(cid,'requests','Review a received response','External content is pending consideration; identity and truth are not verified.'))
 if write and runs:actions.append(action(cid,'requests','Request missing information','Use existing requests and gaps; avoid asking again for the same evidence.'))
 approved=[r for r in runs if r['decision']=='approved' and r['result'].get('recommendation',{}).get('status')=='supported']
 ready=False
 for r in approved:
  cs=[ch for ch in checks if ch['run_id']==r['id']]
  if cs and all(ch['status']=='active' for ch in cs) and not any(i['state']=='not_checked' for ch in cs for i in ch['items']) and any(e['kind']=='human_observation' and e['observed_at']>=cycle_start for e in evidence):ready=True
 if write and ready and not jobs:
  resolution=action(cid,'resolution','Consider recording resolution','Existing prerequisites appear satisfied. Review current verification, exceptions and rationale; the server rechecks every requirement.')
  actions.append(resolution)
  if not pending and not any(ch['status']=='active' and any(i['state']=='needs_follow_up' for i in ch['items']) for ch in checks):actions.insert(0,resolution);actions.pop()
 else:
  if not approved:warnings.append('Resolution needs an approved, supported investigation.')
  if not any(e['kind']=='human_observation' and e['observed_at']>=cycle_start for e in evidence):warnings.append('Record current-cycle human verification. Historical snapshots alone do not establish resolution.')
 for b in blockers[:5]:warnings.append('Waiting on '+b['waiting_on']+'; follow-up '+b['follow_up_at'].isoformat())
 if any(r['status']=='requested' for r in requests):warnings.append('Information is still requested; do not assume an answer.')
 return {'primary':actions[0] if actions else None,'actions':actions,'blockers':warnings,'advisory':True}

def state(c,a,cid):
 item=case(a,cid,c);w=a['workspace_id'];role=current(c,a)
 rows={t:c.execute('SELECT * FROM '+t+' WHERE workspace_id=%s AND case_id=%s ORDER BY id',(w,cid)).fetchall() for t in ('runs','investigation_checks','information_requests','external_responses','case_evidence','case_blockers')}
 jobs=c.execute("SELECT id,status FROM jobs WHERE workspace_id=%s AND target_id=%s AND kind='investigate' AND status IN ('queued','running') ORDER BY id",(w,cid)).fetchall()
 cycle=c.execute("SELECT created_at FROM case_events WHERE workspace_id=%s AND case_id=%s AND event_type='case_reopened' ORDER BY id DESC LIMIT 1",(w,cid)).fetchone()
 result=guidance(item,rows['runs'],rows['investigation_checks'],rows['information_requests'],rows['external_responses'],rows['case_evidence'],jobs,[b for b in rows['case_blockers'] if not b['cleared_at']],cycle['created_at'] if cycle else item['created_at'],role)
 result['version']=hashlib.sha256(json.dumps([item,rows,jobs,role],sort_keys=True,default=str).encode()).hexdigest();return result
@router.get('/cases/{cid}/next-step')
def next_step(cid:str,a=Depends(actor)):
 with connect() as c:
  c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ');return state(c,a,cid)
class OpenAction(Model):
 expected_version:str=Field(min_length=64,max_length=64);action:str=Field(max_length=30)
@router.post('/cases/{cid}/next-step/open')
def open_action(cid:str,body:OpenAction,a=Depends(actor)):
 with connect() as c:
  c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ');s=state(c,a,cid)
  if s['version']!=body.expected_version:raise HTTPException(409,'Workflow changed. Next step refreshed; review it before continuing.')
  if body.action not in [i['action'] for i in s['actions']]:raise HTTPException(409,'Action is no longer available.')
  return {'action':body.action}

@router.get('/my-work')
def my_work(a=Depends(actor)):
 with connect() as c:
  c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ');role=current(c,a);w=a['workspace_id'];uid=a['user_id'];act=[];waiting=[];n=now()
  cases=c.execute("SELECT c.*,u.name AS owner_name FROM cases c LEFT JOIN users u ON u.id=c.owner_id WHERE c.workspace_id=%s AND c.status='open' AND (c.owner_id=%s OR EXISTS(SELECT 1 FROM case_blockers b WHERE b.workspace_id=c.workspace_id AND b.case_id=c.id AND b.responsible_id=%s AND b.cleared_at IS NULL) OR EXISTS(SELECT 1 FROM information_requests r WHERE r.workspace_id=c.workspace_id AND r.case_id=c.id AND r.owner_id=%s AND r.status IN ('draft','requested','received')) OR EXISTS(SELECT 1 FROM case_handovers h WHERE h.workspace_id=c.workspace_id AND h.case_id=c.id AND h.recipient_id=%s AND h.status='pending')) ORDER BY c.due_at NULLS LAST,c.id LIMIT 300",(w,uid,uid,uid,uid)).fetchall();byid={r['id']:r for r in cases}
  bs=c.execute("SELECT b.*,u.name AS responsible_name,s.name AS contact_name FROM case_blockers b LEFT JOIN users u ON u.id=b.responsible_id LEFT JOIN support_contacts s ON s.workspace_id=b.workspace_id AND s.id=b.contact_id WHERE b.workspace_id=%s AND b.cleared_at IS NULL AND (b.responsible_id=%s OR EXISTS(SELECT 1 FROM cases c WHERE c.workspace_id=b.workspace_id AND c.id=b.case_id AND c.owner_id=%s AND c.status='open')) ORDER BY b.follow_up_at LIMIT 300",(w,uid,uid)).fetchall()
  for item in cases:
   cid=item['id'];blocked=any(b['case_id']==cid for b in bs)
   if item['owner_id']==uid:
    (waiting if blocked else act).append(action(cid,'next','Open case',('Assigned to you; active blockers need follow-up.' if blocked else 'This open case is assigned to you.'),title=item['title'],due_at=item['due_at']))
    if item['due_at'] and item['due_at']<n:act.append(action(cid,'next','Review follow-up','Your case follow-up deadline is overdue.',title=item['title'],due_at=item['due_at']))
  for b in bs:
   item=byid.get(b['case_id'])
   if not item or (b['responsible_id']!=uid and item['owner_id']!=uid):continue
   due=b['follow_up_at'];mine=b['responsible_id']==uid
   (act if mine and due<=n else waiting).append(action(b['case_id'],'continuity','Review blocker',('Your blocker follow-up is due.' if mine and due<=n else 'Waiting on '+(b['responsible_name'] or b['contact_name'] or 'recorded contact')+'.'),title=b['waiting_on'],due_at=due,responsible=b['responsible_name'] or b['contact_name'] or 'Recorded contact'))
  for ch in c.execute("SELECT ch.* FROM investigation_checks ch JOIN cases c ON c.workspace_id=ch.workspace_id AND c.id=ch.case_id WHERE ch.workspace_id=%s AND ch.status='active' AND ch.due_at<now() AND c.owner_id=%s AND c.status='open' ORDER BY ch.due_at LIMIT 300",(w,uid)).fetchall():
   item=byid.get(ch['case_id'])
   if item and item['owner_id']==uid and any(i['state'] in ('not_checked','needs_follow_up') for i in ch['items']):act.append(action(ch['case_id'],'checks','Complete overdue checks','Your active checklist has unfinished checks past its deadline.',title=item['title'],due_at=ch['due_at']))
  for r in c.execute("SELECT r.* FROM information_requests r JOIN cases c ON c.workspace_id=r.workspace_id AND c.id=r.case_id WHERE r.workspace_id=%s AND r.status IN ('draft','requested','received') AND c.status='open' AND coalesce(r.owner_id,c.owner_id)=%s ORDER BY r.due_at NULLS LAST,r.created_at DESC LIMIT 300",(w,uid)).fetchall():
   item=byid.get(r['case_id'])
   if not item or (r['owner_id'] or item['owner_id'])!=uid:continue
   pending=c.execute("SELECT 1 FROM external_responses WHERE workspace_id=%s AND request_id=%s AND status='pending'",(w,r['id'])).fetchone()
   if pending and r['status']=='requested' and role in ('owner','reviewer'):act.append(action(r['case_id'],'requests','Review response','An external response awaits human consideration.',title=r['title'],request_id=r['id']))
   elif r['status']=='draft':act.append(action(r['case_id'],'requests','Review request draft','Your information request is still a draft; nothing has been sent.',title=r['title'],request_id=r['id'],due_at=r['due_at']))
   elif r['status']=='requested':
    overdue=r['due_at'] and r['due_at']<=n
    (act if overdue else waiting).append(action(r['case_id'],'requests','Review information request','Follow up: your request deadline is overdue.' if overdue else 'Waiting for requested information.',title=r['title'],request_id=r['id'],due_at=r['due_at']))
  for h in c.execute("SELECT * FROM case_handovers WHERE workspace_id=%s AND recipient_id=%s AND status='pending' ORDER BY created_at LIMIT 100",(w,uid)).fetchall():
   if h['case_id'] in byid:act.append(action(h['case_id'],'continuity','Acknowledge handover','You are the named recipient. Ownership has not transferred.',title=byid[h['case_id']]['title']))
  return {'act':act,'waiting':waiting,'team_visibility':role in ('owner','reviewer'),'bounded_cases':300,'as_of':n}

class CreateLink(Model):
 expected_version:int=Field(ge=1);contact_id:UUID;expires_hours:int=Field(default=72,ge=1,le=336);clarification:str=Field(default="",max_length=2000)
class LinkDecision(Model):
 reason:str=Field(min_length=10,max_length=2000)
 @field_validator("reason",mode="before")
 @classmethod
 def trim_reason(cls,v):return v.strip() if isinstance(v,str) else v
class Review(LinkDecision):
 expected_version:int=Field(ge=1);decision:str=Field(pattern='^(accepted|clarification)$')
class Submission(Model):
 submission_id:UUID;text:str=Field(min_length=10,max_length=4000)
 @field_validator("text",mode="before")
 @classmethod
 def trim_text(cls,v):
  if isinstance(v,str) and ("\x00" in v or any(0xD800<=ord(ch)<=0xDFFF for ch in v)):raise ValueError("Response contains unsupported characters.")
  return v.strip() if isinstance(v,str) else v
class PortalPolicy(Model):
 enabled:bool

def policy(c,w,lock=False):
 if lock:c.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",('external-policy:'+str(w),))
 r=c.execute('SELECT external_responses_enabled FROM workspace_policies WHERE workspace_id=%s'+(' FOR SHARE' if lock else ''),(w,)).fetchone()
 return not r or r['external_responses_enabled']
def request_record(c,a,cid,rid):
 item=case(a,cid,c,True)
 r=c.execute('SELECT * FROM information_requests WHERE workspace_id=%s AND case_id=%s AND id=%s FOR UPDATE',(a['workspace_id'],cid,rid)).fetchone()
 if not r:raise HTTPException(404,'Request not found.')
 return item,r
@router.get('/policies/external-responses')
def portal_policy(a=Depends(actor)):
 with connect() as c:current(c,a);return {'enabled':policy(c,a['workspace_id'])}
@router.post('/policies/external-responses')
def set_portal_policy(body:PortalPolicy,a=Depends(actor)):
 with connect() as c:
  role=current(c,a);require({'role':role},('owner',))
  c.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",('external-policy:'+str(a['workspace_id']),))
  # Serialize policy changes with link creation/submission, including absent policy rows.
  c.execute('INSERT INTO workspace_policies(workspace_id) VALUES(%s) ON CONFLICT DO NOTHING',(a['workspace_id'],))
  c.execute('UPDATE workspace_policies SET external_responses_enabled=%s,version=version+1,updated_at=now() WHERE workspace_id=%s',(body.enabled,a['workspace_id']))
  return {'enabled':body.enabled}
@router.get('/cases/{cid}/requests/{rid}/portal')
def portal_records(cid:str,rid:UUID,a=Depends(actor)):
 with connect() as c:
  current(c,a);case(a,cid,c)
  if not c.execute('SELECT 1 FROM information_requests WHERE workspace_id=%s AND case_id=%s AND id=%s',(a['workspace_id'],cid,rid)).fetchone():raise HTTPException(404,'Request not found.')
  links=c.execute('SELECT id,request_id,created_by,expires_at,revoked_at,created_at FROM external_response_links WHERE workspace_id=%s AND request_id=%s ORDER BY created_at DESC LIMIT 30',(a['workspace_id'],rid)).fetchall()
  responses=c.execute('SELECT * FROM external_responses WHERE workspace_id=%s AND request_id=%s ORDER BY submitted_at DESC LIMIT 30',(a['workspace_id'],rid)).fetchall()
  return {'links':links,'responses':responses,'enabled':policy(c,a['workspace_id'])}
@router.post('/cases/{cid}/requests/{rid}/portal')
def create_link(cid:str,rid:UUID,body:CreateLink,a=Depends(actor)):
 with connect() as c:
  current(c,a,True);item,r=request_record(c,a,cid,rid)
  if not policy(c,a['workspace_id'],True):raise HTTPException(409,'External responses are disabled for this workspace.')
  if item['status']!='open' or r['status']!='requested':raise HTTPException(409,'Mark this open-case request as requested before creating a response link.')
  if r['version']!=body.expected_version:raise HTTPException(409,'Request changed. Reload before creating a link.')
  contact_ref(c,a,body.contact_id,item['study_id'],item['site_id'])
  count=c.execute('SELECT count(*) AS n FROM external_response_links WHERE workspace_id=%s AND request_id=%s',(a['workspace_id'],rid)).fetchone()['n']
  if count>=30:raise HTTPException(429,'Response link limit reached for this request.')
  token=secrets.token_urlsafe(48);lid=uuid4();expires=now()+timedelta(hours=body.expires_hours)
  c.execute('UPDATE external_response_links SET revoked_at=now() WHERE workspace_id=%s AND request_id=%s AND revoked_at IS NULL',(a['workspace_id'],rid))
  c.execute('INSERT INTO external_response_links(workspace_id,id,case_id,request_id,token_hash,contact_id,created_by,question,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',(a['workspace_id'],lid,cid,rid,digest(token),body.contact_id,a['user_id'],Jsonb({'title':r['title'],'items':r['items'],'clarification':body.clarification.strip()}),expires))
  audit(c,a,cid,'external_response_link_created','Restricted text-only link created; nothing sent.',r['run_id'],{'link_id':str(lid),'request_id':str(rid),'expires_at':expires.isoformat(),'identity_verified':False})
  return {'id':lid,'fragment':'#'+token,'expires_at':expires,'no_message_sent':True}
@router.post('/cases/{cid}/requests/{rid}/portal/{lid}/revoke')
def revoke_link(cid:str,rid:UUID,lid:UUID,body:LinkDecision,a=Depends(actor)):
 with connect() as c:
  current(c,a,True);item,r=request_record(c,a,cid,rid)
  link=c.execute('UPDATE external_response_links SET revoked_at=coalesce(revoked_at,now()) WHERE workspace_id=%s AND request_id=%s AND id=%s RETURNING id',(a['workspace_id'],rid,lid)).fetchone()
  if not link:raise HTTPException(404,'Link not found.')
  audit(c,a,cid,'external_response_link_revoked',body.reason,r['run_id'],{'link_id':str(lid),'request_id':str(rid)})
  return {'revoked':True}
@router.post('/cases/{cid}/requests/{rid}/responses/{sid}/review')
def review_response(cid:str,rid:UUID,sid:UUID,body:Review,a=Depends(actor)):
 with connect() as c:
  current(c,a,True);item,r=request_record(c,a,cid,rid)
  if item['status']!='open' or r['status']!='requested':raise HTTPException(409,'This request is no longer eligible for response review.')
  s=row_version(c,a,'external_responses',sid,body.expected_version)
  if s['request_id']!=rid:raise HTTPException(404,'Response not found.')
  if s['status']!='pending':raise HTTPException(409,'Response already reviewed. Clarification needs a new explicit link.')
  row=c.execute('UPDATE external_responses SET status=%s,review_reason=%s,reviewed_by=%s,reviewer_name=%s,reviewed_at=now(),version=version+1 WHERE workspace_id=%s AND id=%s RETURNING *',(body.decision,body.reason,a['user_id'],a['name'],a['workspace_id'],sid)).fetchone()
  if body.decision=='accepted':
   responses=[*r['responses'],{'text':s['text'],'external_response_id':str(sid),'provenance':'restricted_response_link','attribution':ATTRIBUTION,'recorded_at':s['submitted_at'].isoformat(),'reviewed_by':str(a['user_id']),'reviewer_name':a['name'],'accepted_for_consideration':True,'establishes_truth':False}]
   c.execute("UPDATE information_requests SET responses=%s,status='received',version=version+1,updated_at=now() WHERE workspace_id=%s AND id=%s",(Jsonb(responses),a['workspace_id'],rid))
  audit(c,a,cid,'external_response_reviewed',body.reason,r['run_id'],{'response_id':str(sid),'request_id':str(rid),'decision':body.decision,'establishes_truth':False,'checks_completed':False})
  return row

# ponytail: per-process read budget capped4096 keys; one API process today.
_read_limits=OrderedDict();_read_lock=threading.Lock()
def read_budget(request,token):
 keys=['ip:'+digest(request.headers.get('x-client-ip','unknown')),'token:'+digest(token)];n=time.monotonic()
 with _read_lock:
  queues=[]
  for key in keys:
   q=_read_limits.setdefault(key,deque());_read_limits.move_to_end(key)
   while q and q[0]<n-60:q.popleft()
   if len(q)>=30:raise HTTPException(429,'Too many link views. Wait before retrying.')
   queues.append(q)
  for q in queues:q.append(n)
  while len(_read_limits)>4096:_read_limits.popitem(last=False)

def token_from(request):
 token=request.headers.get('x-response-token','')
 if len(token)<40 or len(token)>100 or any(ch not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for ch in token):raise HTTPException(404,'Response link unavailable.')
 return token

def link_context(c,token,lock=False):
 link=c.execute('SELECT * FROM external_response_links WHERE token_hash=%s',(digest(token),)).fetchone()
 if not link:raise HTTPException(404,'Response link unavailable.')
 w=link['workspace_id'];cid=link['case_id'];rid=link['request_id']
 # Match member mutation lock order: case, request, policy, link.
 item=c.execute('SELECT status FROM cases WHERE workspace_id=%s AND id=%s'+(' FOR UPDATE' if lock else ''),(w,cid)).fetchone()
 r=c.execute('SELECT status FROM information_requests WHERE workspace_id=%s AND id=%s'+(' FOR UPDATE' if lock else ''),(w,rid)).fetchone()
 if lock:link=c.execute('SELECT * FROM external_response_links WHERE workspace_id=%s AND id=%s FOR UPDATE',(w,link['id'])).fetchone()
 ws=c.execute('SELECT expires_at FROM workspaces WHERE id=%s',(w,)).fetchone()
 if not item or not r or not ws or item['status']!='open' or r['status']!='requested' or (ws['expires_at'] and ws['expires_at']<=now()) or not policy(c,w,lock):raise HTTPException(410,'This request is unavailable or withdrawn.')
 if link['revoked_at']:raise HTTPException(410,'Response link revoked.')
 if link['expires_at']<=now():raise HTTPException(410,'Response link expired.')
 return link
@router.get('/external-response')
def external_view(request:Request,response:Response):
 token=token_from(request);read_budget(request,token);response.headers['Cache-Control']='no-store';response.headers['Referrer-Policy']='no-referrer'
 with connect() as c:
  link=link_context(c,token)
  submitted=c.execute('SELECT id FROM external_responses WHERE workspace_id=%s AND link_id=%s',(link['workspace_id'],link['id'])).fetchone()
  return {'question':link['question'] if not submitted else None,'state':'already_submitted' if submitted else 'available','expires_at':link['expires_at'],'identity_verified':False,'text_only':True}
@router.post('/external-response')
def external_submit(body:Submission,request:Request):
 token=token_from(request)
 if token in body.text or '/respond#' in body.text:raise HTTPException(422,'Omit response access links or tokens from the written response.')
 rate('external-ip:'+request.headers.get('x-client-ip','unknown'),20,900);rate('external-token:'+digest(token),10,900)
 with connect() as c:
  link=link_context(c,token,True);w=link['workspace_id'];rid=link['request_id']
  old=c.execute('SELECT * FROM external_responses WHERE workspace_id=%s AND link_id=%s',(w,link['id'])).fetchone()
  if old:
   if old['submission_id']==body.submission_id and old['text']==body.text:return {'state':'already_submitted','id':old['id']}
   raise HTTPException(409,'This link already has a submitted response.')
  sid=uuid4();c.execute('INSERT INTO external_responses(workspace_id,id,case_id,request_id,link_id,submission_id,text) VALUES(%s,%s,%s,%s,%s,%s,%s)',(w,sid,link['case_id'],rid,link['id'],body.submission_id,body.text))
  c.execute("INSERT INTO case_events(workspace_id,case_id,actor_name,event_type,notes,payload) VALUES(%s,%s,%s,'external_response_submitted',%s,%s)",(w,link['case_id'],ATTRIBUTION,ATTRIBUTION,Jsonb({'response_id':str(sid),'request_id':str(rid),'link_id':str(link['id']),'provenance':'restricted_response_link','identity_verified':False,'pending_human_review':True})))
  return {'state':'submitted','id':sid,'pending_human_review':True}
