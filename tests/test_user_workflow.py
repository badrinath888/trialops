import sys,unittest
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'apps/api'))
from user_workflow import guidance,Submission,LinkDecision
from pydantic import ValidationError
from uuid import uuid4
class GuidanceTests(unittest.TestCase):
 def test_current_verification_and_human_gates(self):
  n=datetime.now(timezone.utc);item={'id':'C','status':'open'};run={'id':'R','decision':'approved','result':{'recommendation':{'status':'supported'}}};ch={'run_id':'R','status':'active','items':[{'state':'verified'}]}
  def get(ev,rs=[]):return guidance(item,[run],[ch],[{'id':'Q','status':'requested'}],rs,ev,[],[],n,'owner')
  self.assertNotIn('resolution',[a['action'] for a in get([{'kind':'snapshot','observed_at':n}])['actions']])
  self.assertEqual(get([{'kind':'human_observation','observed_at':n}])['primary']['action'],'resolution')
  self.assertEqual(get([{'kind':'human_observation','observed_at':n}],[{'status':'pending','request_id':'Q'}])['primary']['action'],'requests')
 def test_role_and_closed_state(self):
  n=datetime.now(timezone.utc);args=({'id':'C','status':'open'},[],[],[],[],[],[],[],n,'analyst')
  self.assertEqual([a['action'] for a in guidance(*args)['actions']],['investigate'])
  self.assertEqual([a['action'] for a in guidance(*args[:-1],'owner')['actions']],['investigate'])
  self.assertFalse(guidance({**args[0],'status':'resolved'},*args[1:])['actions'])

 def test_submission_boundary(self):
  for text in ('short',' '*20,'x'*4001,'valid response\x00with null','valid response\ud800with surrogate'):
   with self.assertRaises(ValidationError):Submission(submission_id=uuid4(),text=text)
  with self.assertRaises(ValidationError):LinkDecision(reason='short')
  self.assertEqual(Submission(submission_id=uuid4(),text='  valid written response  ').text,'valid written response')

 def test_withdrawn_response_not_actionable(self):
  n=datetime.now(timezone.utc)
  result=guidance({'id':'C','status':'open'},[{'id':'R','decision':'pending','result':{}}],[],[{'id':'Q','status':'cancelled'}],[{'status':'pending','request_id':'Q'}],[],[],[],n,'owner')
  self.assertEqual(result['primary']['action'],'findings')
