import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'apps/api'))
from assessments import model_call,linkage,select_sources,assess,config,validate_refs,validate_text,similar,claims
from assessment_evaluation import dataset

class AssessmentRules(unittest.TestCase):
 def setUp(self): self.data=dataset();self.s=self.data['scenarios'][0];self.doc,self.job,self.proc=copy.deepcopy(self.s['sources'])
 def test_linkage_scope_and_wrong_document(self):
  for s in self.data['scenarios']:
   if s['kind']=='linkage':self.assertEqual({r['id'] for r in linkage(s['sources'],s['context']['case'])['candidates'] if r['eligible_for_confirmation']},set(s['expected']['eligible_pairs']))
  self.job['fields']['site_id']='SITE-OTHER'
  with self.assertRaises(ValueError):linkage([self.doc,self.job])
 def test_selection_identifiers_dates_scope(self):
  selected=[self.doc['id']]
  self.assertEqual(select_sources([self.doc],selected,self.s['context']['case']),[self.doc])
  for ids in ([self.doc['id']]*2,['forged']):
   with self.assertRaises(ValueError):select_sources([self.doc],ids,self.s['context']['case'])
  for field,value in [('document_id','bad id; shell'),('uploaded_at','2024-01-01')]:
   d=copy.deepcopy(self.doc);d['fields'][field]=value
   with self.assertRaises(ValueError):select_sources([d],[d['id']],self.s['context']['case'])
 def test_citations_and_thresholds(self):
  for ref in [{'source_id':'forged','field':'status','quote':'failed'},{'source_id':self.doc['id'],'field':'status','quote':'failed'},{'source_id':self.doc['id'],'field':'processing_status','quote':'processed'}]:
   with self.assertRaises(ValueError):validate_refs([ref],[self.doc])
  ref={'source_id':self.doc['id'],'field':'processing_status','quote':'pending'};validate_refs([ref],[self.doc]);self.assertEqual(ref['version'],'snapshot-v1')
  for text in ('Request DOC-FORGED-999','Escalate after 16 minutes'):
   with self.assertRaises(ValueError):validate_text(text,[self.doc,self.proc])
  validate_text('Escalate after 15 minutes',[self.proc])
 def test_strict_model_output_and_complete_claims(self):
  call=lambda *args:{'claims':[{'claim_id':'C1','label':'supported by selected evidence','explanation':'Record reports pending status.','correction':'','citations':[{'source_id':self.doc['id'],'field':'processing_status','quote':'pending'}]}]}
  self.assertEqual(assess('wording','The record is pending.',[self.doc],self.s['context'],config('wording'),call)['claims'][0]['label'],'supported by selected evidence')
  with self.assertRaises(ValueError):assess('wording','Pending. Other claim.',[self.doc],self.s['context'],config('wording'),call)
  with self.assertRaises(ValueError):assess('wording','Pending.',[self.doc],self.s['context'],config('wording'),lambda *args:{'claims':[],'tools':['shell']})
 def test_unavailable_and_timeout(self):
  from unittest.mock import patch
  cfg=config("wording");cfg["endpoint"]="http://example.com"
  with patch("urllib.request.urlopen") as fetch:
   with self.assertRaises(ValueError):model_call("wording",{},cfg)
   fetch.assert_not_called()
  with patch("urllib.request.urlopen",side_effect=TimeoutError("test timeout")):
   with self.assertRaises(TimeoutError):model_call("wording",{},config("wording"))
 def test_input_and_output_bounds(self):
  from unittest.mock import patch,MagicMock
  with patch("urllib.request.urlopen") as fetch:
   with self.assertRaises(ValueError):model_call("wording",{"data":"x"*22000},config("wording"))
   fetch.assert_not_called()
  mock=MagicMock();mock.__enter__.return_value.read.return_value=b"x"*20001
  with patch("urllib.request.urlopen",return_value=mock):
   with self.assertRaises(ValueError):model_call("wording",{},config("wording"))
 def test_questions_duplicate_and_gap_validation(self):
  ctx=copy.deepcopy(self.s['context']);q='Which exact document ID and upload receipt connects this certificate?';ctx['requests']=[{'title':'Receipt','items':[q],'status':'requested'}]
  response={'questions':[{'gap_id':'linkage','question':q,'uncertainty':'Exact linkage is unknown.','citations':[{'source_id':self.proc['id'],'field':'content','quote':'Check the upload receipt'}]}]}
  self.assertEqual(assess('questions','',[self.doc,self.job,self.proc],ctx,config('questions'),lambda *a:copy.deepcopy(response))['questions'],[])
  response['questions'][0]['gap_id']='invented'
  with self.assertRaises(ValueError):assess('questions','',[self.doc,self.job,self.proc],ctx,config('questions'),lambda *a:response)
  self.assertTrue(similar(q,q));self.assertEqual(len(claims('First. Second.')),2)

 def test_server_owned_passage_mapping(self):
  from unittest.mock import patch,MagicMock
  payload={'selected_evidence':[self.doc],'claims':[{'claim_id':'C1','text':'The record reports pending.'}]}
  cfg=config('wording')
  def response(ref):
   r=MagicMock();r.__enter__.return_value=r;r.read.return_value=json.dumps({'message':{'content':json.dumps({'claims':[{'claim_id':'C1','label':'insufficient evidence','explanation':'No direct proof.','correction':'','citations':[ref]}]})}}).encode();return r
  with patch('assessments.urllib.request.urlopen',return_value=response({'reference_id':'P1'})):
   result=model_call('wording',payload,cfg);ref=result['claims'][0]['citations'][0];self.assertEqual(ref['source_id'],self.doc['id']);self.assertEqual(ref['quote'],self.doc['fields'][ref['field']])
  for ref in ({'reference_id':'FORGED'},{'reference_id':'P1','quote':'rewritten'}):
   with patch('assessments.urllib.request.urlopen',return_value=response(ref)):
    with self.assertRaises(ValueError):model_call('wording',payload,cfg)

if __name__=='__main__': unittest.main()
