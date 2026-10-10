"""Deterministic retry workload boundary; fresh expiring workspace only, no inference."""
import sys
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'apps/api'))
from integration import Client
from db import connect
from evaluation import configuration
from assessment_evaluation import dataset
from psycopg.types.json import Jsonb
client=Client();wid=client.call('/auth/demo',{})['workspace_id'];uid=client.call('/auth/me')['user_id'];rid=uuid4()
try:
 with connect() as c:
  cfg=configuration('ollama','assessments')
  c.execute('INSERT INTO evaluation_runs(workspace_id,id,dataset_version,model,configuration,actor_id) VALUES(%s,%s,%s,%s,%s,%s)',(wid,rid,dataset()['version'],cfg['model'],Jsonb(cfg),uid))
  c.execute("INSERT INTO jobs(id,workspace_id,actor_id,kind,target_id,status,finished_at) VALUES(%s,%s,%s,'evaluate',%s,'failed',now())",(uuid4(),wid,uid,str(rid)))
  # Leased placeholders cannot be dispatched by the real worker.
  for _ in range(2):c.execute("INSERT INTO jobs(id,workspace_id,actor_id,kind,target_id,status,lease_token,lease_expires_at) VALUES(%s,%s,%s,'assess',%s,'running',%s,now()+interval '10 minutes')",(uuid4(),wid,uid,str(uuid4()),uuid4()))
 client.call('/evaluations/'+str(rid)+'/retry',{},429)
 with connect() as c:
  assert c.execute("SELECT count(*) AS n FROM jobs WHERE workspace_id=%s AND kind IN ('assess','evaluate') AND status IN ('queued','running')",(wid,)).fetchone()['n']==2
 print('PASS: evaluation retry respects two-active shared workspace workload limit; no inference dispatched.')
finally:
 with connect() as c:c.execute('DELETE FROM workspaces WHERE id=%s AND demo=true',(wid,))
