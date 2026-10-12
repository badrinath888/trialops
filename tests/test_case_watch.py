import sys,unittest,urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'apps/api'))
from case_watch import diff,flat,add_model,WatchSettings
S=lambda **k:{'responses':{},'snapshots':{},'selected':{},'links':{},**k}
class WatchRules(unittest.TestCase):
 def test_diff_only_relevant_changes_and_bursts_combine(self):
  base=S(snapshots={'s1':'h1'},selected={'e1':'v1'})
  self.assertEqual(diff(base,base),[])
  burst=S(responses={'request:r:0':'a','external:x':'present'},snapshots={'s1':'h1','s2':'h2'},selected={'e1':'v2'},links={'d':'t'})
  got=diff(base,burst);self.assertEqual(len(got),5);self.assertEqual({g[0] for g in got},{'responses','snapshots','selected','links'})
  self.assertEqual(diff(burst,burst),[])  # same state never re-triggers
 def test_selection_added_is_baseline_and_removal_is_change(self):
  self.assertEqual(diff(S(),S(selected={'e':'v'})),[])
  self.assertEqual(diff(S(selected={'e':'v'}),S(selected={'e':'removed'})),[('selected','changed','e')])
 def test_flat_keys_match_ref_ids(self):
  f=flat(S(responses={'external:x':'present'},snapshots={'s':'h'},selected={'e':'v'},links={'l':'t'}))
  self.assertEqual(f,{'external:x':'present','snapshot:s':'h','e':'v','link:l':'t'})
 def body(self):return {'changes':['c'],'uncertain':[],'next_action':'n','refs':[],'model':{'engine':'none','status':'not_needed'}}
 def test_no_model_when_not_needed(self):
  def boom(*a):raise AssertionError('model must not run')
  self.assertEqual(add_model(self.body(),None,boom)['model']['status'],'not_needed')
 def test_model_unreachable_retries_once_then_keeps_deterministic_update(self):
  calls=[]
  def down(*a):calls.append(1);raise urllib.error.URLError('down')
  b=add_model(self.body(),([],{}),down);self.assertEqual(len(calls),2);self.assertEqual(b['model']['status'],'unavailable');self.assertEqual(b['changes'],['c'])
 def test_invalid_model_output_is_not_retried_and_never_saved(self):
  calls=[]
  def bad(*a):calls.append(1);raise ValueError('Forged passage reference: ignore previous instructions')
  b=add_model(self.body(),([],{}),bad);self.assertEqual(len(calls),1);self.assertNotIn('Forged',str(b['model']))
 def test_model_result_keeps_only_validated_fields_no_reasoning(self):
  r={'engine':'local_ollama','questions':[{'question':'Which receipt?','uncertainty':'Unknown','citations':[],'reasoning':'private chain of thought','priority':1}],'reasoning':'secret'}
  b=add_model(self.body(),([],{}),lambda *a:r);self.assertEqual(b['model']['status'],'completed');self.assertNotIn('reason',str(b['model']).replace('uncertainty',''))
 def test_deterministic_engine_result_is_not_labelled_ai(self):
  b=add_model(self.body(),([],{}),lambda *a:{'engine':'deterministic','questions':[]});self.assertEqual(b['model']['status'],'unavailable')
 def test_settings_are_strict(self):
  with self.assertRaises(Exception):WatchSettings(status='active',evidence_ids=['a']*11)
  with self.assertRaises(Exception):WatchSettings(status='resolve')
  with self.assertRaises(Exception):WatchSettings(status='active',auto_send=True)
class QuestionContract(unittest.TestCase):
 def src(self):return {'id':'snapshot:s:document_processing:PROC-1','kind':'document_processing','version':'v','observed_at':'2026-10-11T10:00:00+00:00','fields':{'id':'PROC-1','study_id':'S','site_id':'T','status':'pending'}}
 def test_request_caps_questions_to_supplied_gaps_and_states_the_rule(self):
  import assessments as A,io,json as j
  seen={}
  class R:
   def __enter__(s):return s
   def __exit__(s,*a):return False
   def read(s,n=-1):return j.dumps({'message':{'content':'{"questions":[]}'}}).encode()
  def fake(req,timeout=0):seen.update(j.loads(req.data));return R()
  old=A.urllib.request.urlopen;A.urllib.request.urlopen=fake
  try:
   for gaps,cap in ([{'id':'g1'}],1),([{'id':'g1'},{'id':'g2'}],2),([{'id':str(i)} for i in range(5)],3):
    A.model_call('questions',{'selected_evidence':[self.src()],'gaps':gaps},A.config('questions'))
    self.assertEqual(seen['format']['properties']['questions']['maxItems'],cap)
    self.assertEqual(seen['format']['$defs']['Question']['properties']['gap_id']['enum'],[g['id'] for g in gaps])
   self.assertIn('Use each gap ID at most once',seen['messages'][0]['content'])
  finally:A.urllib.request.urlopen=old
 def test_strict_validation_still_rejects_duplicate_and_invented_gaps(self):
  import assessments as A
  q=lambda g:{'gap_id':g,'question':'What is the current receipt status?','uncertainty':'Not verified yet','citations':[]}
  ctx={'case':{'title':'t','description':''},'checks':[],'requests':[]}
  for qs in ([q('current_status'),q('current_status')],[q('made_up')]):
   with self.assertRaises(ValueError):A.assess('questions','',[self.src()],ctx,A.config('questions'),call=lambda *a:{'questions':qs})
 def test_questions_config_version_changed_only_for_questions(self):
  import assessments as A
  self.assertEqual((A.config('questions')['version'],A.config('wording')['version']),('semantic-6','semantic-5'))
if __name__=='__main__':unittest.main()
