import copy, io, sys, unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from uuid import UUID
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'apps/api'))
from pypdf import PdfReader
from report import build_report

RUN = {
 'id':'a334b848-bcb8-40d0-af74-246f1ffd03d4','case_id':'CASE-PDF',
 'created_at':'2026-10-08T21:05:05+00:00','duration_seconds':9.965,
 'model':'qwen2.5:7b','decision':None,
 'result':{'mode':'ollama','recommendation':{'status':'supported','summary':'Frozen summary',
 'hypothesis':'No root cause has been established.', 'recommended_next_step':'Check processing for 15 minutes.',
 'evidence_ids':['KB-001#v1-s1']},
 'sources':[{'id':'KB-001#v1-s1','title':'Certificate procedure','content':'Preserve <document> & records.', 'similarity':.651}],
 'escalation_drafts':[{'id':'DRAFT-001','subject':'Engineering draft','body':'Unsent body\nDocument: DOC-001'}],
 'external_actions_executed':[]}}
CASE={'title':'Certificate missing','study_id':'CT-204','site_id':'SITE-104','status':'open'}

class ReportTests(unittest.TestCase):
 def text(self,run=RUN):
  pdf=build_report(run,[{'event_type':'investigation_completed','actor_name':'Badrinath','created_at':'2026-10-08T21:05:05Z'}],CASE)
  self.assertTrue(pdf.startswith(b'%PDF-'))
  return '\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
 def test_frozen_sources_drafts_and_pending_decision(self):
  before=copy.deepcopy(RUN);text=self.text()
  for needle in ['CASE-PDF','KB-001#v1-s1','15 minutes','Preserve <document> & records.','UNSENT','DOC-001','Pending review','Badrinath','Investigation Completed']:
   self.assertIn(needle,text)
  self.assertEqual(RUN,before)
 def test_approved_reviewer_and_notes(self):
  run=copy.deepcopy(RUN);run.update(decision='approved',reviewer='Renée',review_notes='Reviewed synthetic evidence.',reviewed_at='2026-10-08T22:00:00Z')
  text=self.text(run)
  for needle in ['approved','Renée','Reviewed synthetic evidence.']:self.assertIn(needle,text)
 def test_unsupported_and_missing_snapshots(self):
  run=copy.deepcopy(RUN);run['result']={'recommendation':{'status':'insufficient_evidence','evidence_ids':[]},'operational_evidence':{'synchronization':{'snapshot':None,'records':[]}}}
  text=self.text(run)
  self.assertIn('insufficient_evidence',text);self.assertIn('No escalation drafts were created.',text);self.assertIn('No operational snapshot available.',text)
 def test_long_untrusted_text_splits_pages(self):
  run=copy.deepcopy(RUN);run['result']['sources'][0]['content']=('Procedure <script> & text. '+ 'x'*180+'\n')*200
  self.assertIn('<script>',self.text(run))
 def test_endpoint_uses_workspace_scope_and_binary_response(self):
  import main
  actor={'workspace_id':'workspace-A','role':'owner'}
  connection=MagicMock();connection.execute.return_value.fetchall.return_value=[]
  with patch.object(main,'connect') as connect, patch.object(main,'get_run',return_value=RUN) as get_run, patch.object(main,'get_case',return_value=CASE):
   connect.return_value.__enter__.return_value=connection
   response=main.investigation_pdf(UUID(RUN['id']),actor)
   get_run.assert_called_once_with(actor,UUID(RUN['id']),connection)
   self.assertEqual(response.media_type,'application/pdf');self.assertTrue(response.body.startswith(b'%PDF-'))
   self.assertIn('.pdf',response.headers['content-disposition']);self.assertEqual(response.headers['cache-control'],'no-store')
 def test_endpoint_rejects_missing_or_cross_workspace_run(self):
  import main
  from fastapi import HTTPException
  with patch.object(main,'connect') as connect, patch.object(main,'get_run',side_effect=HTTPException(404,'Not found')):
   with self.assertRaises(HTTPException) as caught: main.investigation_pdf(UUID(RUN['id']),{'workspace_id':'other'})
   self.assertEqual(caught.exception.status_code,404)

if __name__=='__main__':unittest.main()
