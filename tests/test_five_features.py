import sys,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'apps/api'))
from five_features import same_evidence,blocked_seconds
from account_access import deliver
class FiveRules(unittest.TestCase):
 def test_duplicate_matching_preserves_identifiers(self):
  self.assertTrue(same_evidence('Please send upload receipt DOC-ONE','Provide the upload receipt for DOC-ONE'))
  self.assertFalse(same_evidence('Upload receipt DOC-ONE','Upload receipt DOC-TWO'))
  self.assertFalse(same_evidence('Upload receipt DOC-ONE','Current training certificate DOC-ONE'))
  self.assertFalse(same_evidence('',''))
 def test_union_not_sum_of_waiting(self):
  now=datetime.now(timezone.utc);start=now-timedelta(hours=4)
  rows=[{'started_at':start,'cleared_at':start+timedelta(hours=2)},{'started_at':start+timedelta(hours=1),'cleared_at':now-timedelta(hours=1)},{'started_at':now-timedelta(minutes=30),'cleared_at':None}]
  self.assertEqual(blocked_seconds(rows,now),3.5*3600);self.assertEqual(blocked_seconds([],now),0)
 def test_mail_disabled_and_bounded_retry(self):
  with patch.dict('os.environ',{},clear=True):self.assertFalse(deliver('test@sample.invalid','secret','reset'))
  with patch.dict('os.environ',{'SMTP_HOST':'mailpit','MAIL_FROM':'trialops@sample.invalid','SMTP_STARTTLS':'false'},clear=True),patch('account_access.smtplib.SMTP',side_effect=OSError('unavailable')) as smtp,patch('account_access.time.sleep'):
   self.assertFalse(deliver('test@sample.invalid','secret','reset'));self.assertEqual(smtp.call_count,2)
if __name__=='__main__':unittest.main()
