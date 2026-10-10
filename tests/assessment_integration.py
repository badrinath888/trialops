"""Run only on the isolated stack; delete only freshly created test workspaces."""
import sys,time,json,copy
from pathlib import Path
from uuid import uuid4,UUID
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'apps/api'))
from integration import Client
from db import connect
from psycopg.types.json import Jsonb
from assessments import context,fresh_actor,config,process_assessment
from worker import run_once

a,b=Client(),Client();workspaces=[];groups=0

def passed(name):
 global groups
 groups+=1;print('PASS:',name,flush=True)

def wait(rid):
 for _ in range(180):
  r=next(x for x in a.call('/cases/CASE-LINKAGE-DEMO/assessments') if x['id']==rid)
  if r['status'] in ('completed','failed'):return r
  time.sleep(1)
 raise AssertionError('Assessment did not finish')

def start(kind,selected,text=''):
 id=str(uuid4());a.call('/cases/CASE-LINKAGE-DEMO/assessments',{'id':id,'kind':kind,'source_ids':[s['id'] for s in selected],'text':text},202);return wait(id)

def manual_job():
 id,token,jid=uuid4(),uuid4(),uuid4()
 with connect() as c:
  who=fresh_actor(c,w,uid);catalog,digest,ctx=context(c,who,'CASE-LINKAGE-DEMO');selected=[s for s in catalog if s['kind']=='document_processing'][:1]
  inp={'id':str(id),'kind':'wording','text':'The record reports pending.','source_ids':[s['id'] for s in selected]}
  c.execute("INSERT INTO case_assessments(workspace_id,id,case_id,kind,actor_id,input,context_hash,configuration,frozen_evidence) VALUES(%s,%s,'CASE-LINKAGE-DEMO','wording',%s,%s,%s,%s,%s)",(w,id,uid,Jsonb(inp),digest,Jsonb(config('wording')),Jsonb(json.loads(json.dumps({'sources':selected,'context':ctx},default=str)))))
  return c.execute("INSERT INTO jobs(id,workspace_id,actor_id,kind,target_id,status,lease_token,lease_expires_at,started_at,attempts) VALUES(%s,%s,%s,'assess',%s,'running',%s,now()+interval '10 minutes',now(),1) RETURNING *",(jid,w,uid,str(id),token)).fetchone()

try:
 w=a.call('/auth/demo',{})['workspace_id'];workspaces.append(w);wb=b.call('/auth/demo',{})['workspace_id'];workspaces.append(wb);uid=a.call('/auth/me')['user_id']
 a.call('/assessment-demo',{'stage':'start'});a.call('/assessment-demo',{'stage':'start'})
 sources=a.call('/cases/CASE-LINKAGE-DEMO/assessment-sources')['sources'];records=[s for s in sources if 'ASSESSMENT' not in s['id'] and s['fields'].get('id','').startswith(('PROC-DEMO','SYNC-DEMO'))]
 assert len(records)==2
 b.call('/cases/CASE-LINKAGE-DEMO/assessment-sources',expected=404)
 a.call('/cases/CASE-LINKAGE-DEMO/assessments',{'id':str(uuid4()),'kind':'linkage','text':'','source_ids':[records[0]['id'],'forged-record']},422)
 a.call('/cases/CASE-LINKAGE-DEMO/investigate',{},202)
 for _ in range(180):
  detail=a.call('/cases/CASE-LINKAGE-DEMO');runs=detail['runs']
  if runs:break
  time.sleep(1)
 assert runs
 sources=a.call('/cases/CASE-LINKAGE-DEMO/assessment-sources')['sources'];procedures=[s for s in sources if s['kind']=='procedure'];assert procedures
 result=start('linkage',records);assert result['status']=='completed' and result['result']['engine']=='deterministic';assert not any(c['eligible_for_confirmation'] for c in result['result']['candidates'])
 a.call('/cases/CASE-LINKAGE-DEMO/assessments/'+result['id']+'/decisions',{'id':str(uuid4()),'action':'confirm_link','target':result['result']['candidates'][0]['id'],'reason':'Same site is not sufficient linkage.'},422)
 passed('cross-workspace and forged-source denial; deterministic same-site/unrelated identifiers cannot be confirmed')
 wording=start('wording',records+procedures[:1],'The failed synchronization job caused the missing certificate DOC-DEMO-CERT-001.');assert wording['status']=='completed',wording.get('error');assert wording['result']['claims'][0]['label'] in ('insufficient evidence','not assessable'),wording['result']
 decision={'id':str(uuid4()),'action':'disagree','target':'C1','reason':'Synthetic reviewer records a contrary judgment for audit verification.','value':'not assessable'}
 a.call('/cases/CASE-LINKAGE-DEMO/assessments/'+wording['id']+'/decisions',decision);a.call('/cases/CASE-LINKAGE-DEMO/assessments/'+wording['id']+'/decisions',decision)
 cached=a.call('/cases/CASE-LINKAGE-DEMO/assessments',{'id':str(uuid4()),'kind':'wording','text':wording['input']['text'],'source_ids':wording['input']['source_ids']},202);assert cached['id']==wording['id']
 passed('actual local Ollama unsupported-causation assessment, attributed disagreement and input/config/evidence-valid reuse')
 question=start('questions',records+procedures[:1]);assert question['status']=='completed',question.get('error');assert 1<=len(question['result']['questions'])<=3
 a.call('/cases/CASE-LINKAGE-DEMO/assessments/'+question['id']+'/decisions',{'id':str(uuid4()),'action':'question_usefulness','target':'0','reason':'Synthetic test judgment: a focused receipt question clarifies the unknown linkage.','value':'useful'})
 path='/cases/CASE-LINKAGE-DEMO/assessments/'+question['id']+'/request-draft';draft=a.call(path,{'index':0});assert a.call(path,{'index':0})==draft
 info=next(r for r in a.call('/cases/CASE-LINKAGE-DEMO/workflow')['requests'] if r['id']==draft['request_id']);assert info['status']=='draft'
 passed('bounded prioritized questions, synthetic usefulness judgment, existing unsent request draft and repeat idempotency')
 a.call('/assessment-demo',{'stage':'updated'})
 history=a.call('/cases/CASE-LINKAGE-DEMO/assessments');assert all(r['stale'] for r in history);assert next(r for r in history if r['id']==wording['id'])['result']==wording['result']
 a.call('/cases/CASE-LINKAGE-DEMO/assessments/'+result['id']+'/decisions',{'id':str(uuid4()),'action':'confirm_link','target':result['result']['candidates'][0]['id'],'reason':'Historical stale candidate cannot be confirmed.'},409)
 sources=a.call('/cases/CASE-LINKAGE-DEMO/assessment-sources')['sources'];updated=[s for s in sources if s['fields'].get('upload_receipt_id')=='UPLOAD-DEMO-CORRECT']
 linkage=start('linkage',updated);eligible=[c for c in linkage['result']['candidates'] if c['eligible_for_confirmation']];assert eligible
 a.call('/cases/CASE-LINKAGE-DEMO/assessments/'+linkage['id']+'/decisions',{'id':str(uuid4()),'action':'confirm_link','target':eligible[0]['id'],'reason':'Reviewer checked exact document, receipt and job IDs with observation dates.','value':'confirmed'})
 package=a.call('/cases/CASE-LINKAGE-DEMO/package.json');assert package['assessments'] and package['assessment_decisions'];assert package['case']['status']=='open'
 passed('updated receipt produces exact candidate; old assessments frozen/stale; human confirmation audited; exports retain history and no automatic closure')
 # Revoked before execution and on history return.
 job=manual_job()
 with connect() as c:c.execute("UPDATE memberships SET role='analyst' WHERE workspace_id=%s AND user_id=%s",(w,uid))
 with patch('assessments.assess') as model:
  try:process_assessment(job);raise AssertionError('Revocation accepted')
  except Exception as e:assert getattr(e,'status_code',None)==403
  model.assert_not_called()
 a.call('/cases/CASE-LINKAGE-DEMO/assessments',expected=403)
 with connect() as c:c.execute("UPDATE memberships SET role='owner' WHERE workspace_id=%s AND user_id=%s",(w,uid));c.execute("UPDATE jobs SET status='failed',finished_at=now() WHERE id=%s",(job['id'],))
 passed('revoked permission prevents model dispatch and result return')
 # Revocation while inference runs: no result save.
 job=manual_job()
 def revoke(*args):
  with connect() as c:c.execute("UPDATE memberships SET role='analyst' WHERE workspace_id=%s AND user_id=%s",(w,uid))
  return {'engine':'local_ollama','claims':[]}
 with patch('assessments.assess',revoke):
  try:process_assessment(job);raise AssertionError('Revoked result saved')
  except Exception as e:assert getattr(e,'status_code',None)==403
 with connect() as c:
  assert c.execute('SELECT result FROM case_assessments WHERE workspace_id=%s AND id=%s',(w,job['target_id'])).fetchone()['result'] is None
  c.execute("UPDATE memberships SET role='owner' WHERE workspace_id=%s AND user_id=%s",(w,uid));c.execute("UPDATE jobs SET status='failed',finished_at=now() WHERE id=%s",(job['id'],))
 passed('authorization rechecked after inference before saving')
 job=manual_job()
 def lose(*args):
  with connect() as c:c.execute('UPDATE jobs SET lease_token=%s WHERE id=%s',(uuid4(),job['id']))
  return {'engine':'local_ollama','claims':[]}
 with patch('assessments.assess',lose):process_assessment(job)
 with connect() as c:
  assert c.execute('SELECT result FROM case_assessments WHERE workspace_id=%s AND id=%s',(w,job['target_id'])).fetchone()['result'] is None
  c.execute("UPDATE jobs SET status='failed',finished_at=now() WHERE id=%s",(job['id'],))
 job=manual_job()
 with patch('worker.claim',return_value=job),patch('worker.process',side_effect=TimeoutError('synthetic timeout')):assert run_once()
 with connect() as c:assert c.execute('SELECT status FROM jobs WHERE id=%s',(job['id'],)).fetchone()['status']=='failed'
 passed('lost lease/interruption cannot overwrite results; timeout produces durable explicit failure')
 print('PASS:',groups,'connected assessment/security groups; quality evaluation remains separate.')
finally:
 with connect() as c:
  for wid in workspaces:c.execute('DELETE FROM workspaces WHERE id=%s AND demo=true',(wid,))
