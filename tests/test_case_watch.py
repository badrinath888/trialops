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
if __name__=='__main__':unittest.main()
