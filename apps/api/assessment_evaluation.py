"""Independent, offline specification-derived labels; the evaluated model never authors labels."""
import copy,json,time
from pathlib import Path
from datetime import datetime,timezone
from workflows import canonical
from assessments import assess,config


def dataset():
    data=json.loads(Path(__file__).with_name('evaluation_data').joinpath('assessments-v1.json').read_text())
    data['sha256']=canonical(data)
    return data


def evaluate(configuration,heartbeat=lambda:None):
    data=dataset()
    if data['sha256']!=configuration['dataset_sha256']: raise ValueError('Assessment evaluation dataset changed')
    rows=[];correct=total=valid=cited_total=failures=tp=fp=fn=0
    for s in data['scenarios']:
        heartbeat();start=time.monotonic()
        row={'scenario_id':s['id'],'kind':s['kind'],'expected':s['expected']}
        expected_semantic=s['kind']!='linkage' and not s['expected'].get('no_questions')
        if expected_semantic:cited_total+=1
        try:
            cfg=copy.deepcopy(configuration['assessment_configuration']) if s['kind']!='linkage' else config('linkage')
            result=assess(s['kind'],s.get('text',''),s['sources'],s['context'],cfg)
            row['result']=result;row['citation_validity']=True if result.get('engine')=='local_ollama' else None
            if result.get('engine')=='local_ollama':valid+=1
            if s['kind']=='wording':
                actual=[r['label'] for r in result['claims']];row['actual_labels']=actual
                correct+=sum(a==b for a,b in zip(actual,s['expected']['labels']));total+=len(s['expected']['labels'])
            elif s['kind']=='linkage':
                predicted={r['id'] for r in result['candidates'] if r['eligible_for_confirmation']}
                expected=set(s['expected']['eligible_pairs']);tp+=len(predicted&expected);fp+=len(predicted-expected);fn+=len(expected-predicted)
                row['predicted_pairs']=sorted(predicted)
            else:
                qs=result['questions'];row['question_count']=len(qs)
                row['expected_behavior_met']=len(qs)<=3 and (not s['expected'].get('no_questions') or not qs)
                row['human_usefulness_judgments']=[]
        except Exception as e:
            failures+=1;row.update(execution_failure=type(e).__name__+': '+str(e)[:200],citation_validity=False)
            if s['kind']=='wording':total+=len(s['expected']['labels'])
            if s['kind']=='linkage':fn+=len(s['expected']['eligible_pairs'])
        row['latency_seconds']=round(time.monotonic()-start,3);rows.append(row)
    return {'dataset_version':data['version'],'dataset_sha256':data['sha256'],'configuration':configuration,'executed_at':datetime.now(timezone.utc).isoformat(),'scenarios':rows,
      'counts':{'scenarios':len(rows),'claim_labels_correct':correct,'claim_labels_total':total,'claim_label_accuracy':round(correct/total,4) if total else None,'citation_valid_results':valid,'citation_results_total':cited_total,'citation_validity':round(valid/cited_total,4) if cited_total else None,'linkage_true_positive':tp,'linkage_false_positive':fp,'linkage_false_negative':fn,'linkage_precision':round(tp/(tp+fp),4) if tp+fp else None,'linkage_recall':round(tp/(tp+fn),4) if tp+fn else None,'mean_latency_seconds':round(sum(r['latency_seconds'] for r in rows)/len(rows),3),'execution_failures':failures,'recorded_human_question_judgments':0},
      'ground_truth_provenance':data['label_provenance'],'security_tests':'Deterministic access/revocation/output/timeout/lease tests are reported separately; these quality rates do not establish security.','subjective_judgment':None}
