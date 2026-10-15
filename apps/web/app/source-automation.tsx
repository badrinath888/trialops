"use client";
import {useCallback,useEffect,useState} from 'react';
import {api,plural,stamp} from './lib';
type Row=Record<string,any>;
const ADAPTER:Record<string,string>={mock_portal:'Mock upload portal (synthetic)',mock_hub:'Mock binder hub (synthetic)'};
const SCENARIO:Record<string,string>={processing_completed:'Processing completed',duplicate_delivery:'Duplicate delivery',conflicting_event_id:'Conflicting event ID',older_observation:'Older observation',wrong_version:'Wrong document version',unmatched_document:'Unmatched document'};
export function SourceAutomation({me}:{me:Row}){
 const [d,setD]=useState<Row|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[name,setName]=useState(''),[adapter,setAdapter]=useState('mock_portal'),[key,setKey]=useState(''),[caseId,setCaseId]=useState(''),[scenario,setScenario]=useState('processing_completed'),[msg,setMsg]=useState('');
 const load=useCallback(async()=>{try{setD(await api('/sources'));setError('')}catch(e){setError((e as Error).message)}},[]);
 useEffect(()=>{if(me.role==='owner')void load()},[me.role,load]);
 if(me.role!=='owner')return null;
 const run=async(fn:()=>Promise<unknown>)=>{setBusy(true);setError('');setMsg('');try{await fn();await load()}catch(e){setError((e as Error).message)}finally{setBusy(false)}};
 const a=d?.activity;
 return <section className="panel source-automation" aria-label="Document-processing sources">
  <h3>Document-processing sources <small className="subtle">· synthetic mock sources only</small></h3>
  <p className="subtle">Mock sources deliver locally controlled test events. TrialOps saves exact-match evidence, updates the affected checks and prepares a next action. It never confirms linkage, sends messages, approves or resolves a case. No real vendor account is connected.</p>
  {error&&<p role="alert" className="error">{error}</p>}
  {msg&&<p role="status">{msg}</p>}
  {!d?<p role="status">Loading sources…</p>:<>
   <ul className="source-list">{d.sources.map((s:Row)=><li key={s.id} className="work-item">
    <strong>{s.name}</strong> · {ADAPTER[s.adapter]} · <span role="status">{s.status==='enabled'?(s.last_error?'Enabled · error':'Enabled · connected'):s.status==='paused'?'Paused':'Revoked'}</span>
    <div className="subtle">Last successful collection: {s.last_success_at?stamp(s.last_success_at):'none yet'}{s.last_error?` · ${s.last_error}`:''}</div>
    {s.status!=='revoked'&&<div className="actions">
     <button className="outline" disabled={busy} onClick={()=>run(()=>api(`/sources/${s.id}/status`,{status:s.status==='enabled'?'paused':'enabled'}))}>{s.status==='enabled'?'Pause':'Enable'}</button>
     <button className="outline" disabled={busy} onClick={()=>run(()=>api(`/sources/${s.id}/status`,{status:'revoked'}))}>Revoke key</button></div>}
   </li>)}</ul>
   {d.sources.length===0&&<p className="subtle">No mock source yet.</p>}
   <form className="source-form" onSubmit={e=>{e.preventDefault();void run(async()=>{const r=await api('/sources',{name,adapter});setKey(r.source_key);setName('')})}}>
    <label>Source name<input value={name} onChange={e=>setName(e.target.value)} minLength={3} maxLength={60} required/></label>
    <label>Mock adapter<select value={adapter} onChange={e=>setAdapter(e.target.value)}>{Object.keys(ADAPTER).map(k=><option key={k} value={k}>{ADAPTER[k]}</option>)}</select></label>
    <button disabled={busy}>Add mock source</button>
   </form>
   {key&&<p role="status">Source key (shown once): <code>{key}</code></p>}
   <label className="check"><input type="checkbox" checked={d.draft_preparation} disabled={busy} onChange={e=>run(()=>api('/sources/automation',{draft_preparation:e.target.checked}))}/> Prepare an unsent draft request for the suggested next action (off by default; never sent automatically)</label>
   {d.sources.some((s:Row)=>s.status==='enabled')&&<details><summary>Send a synthetic test event</summary>
    <form className="source-form" onSubmit={e=>{e.preventDefault();const s=d.sources.find((x:Row)=>x.status==='enabled');void run(async()=>{const r=await api(`/sources/${s.id}/mock-event`,{case_id:caseId,scenario});setMsg(`Delivery ${r.delivery}. The worker processes it in the background.`)})}}>
     <label>Case ID (needs a defined Document journey)<input value={caseId} onChange={e=>setCaseId(e.target.value)} required maxLength={100}/></label>
     <label>Scenario<select value={scenario} onChange={e=>setScenario(e.target.value)}>{d.scenarios.map((k:string)=><option key={k} value={k}>{SCENARIO[k]}</option>)}</select></label>
     <button disabled={busy||!caseId}>Send test event</button></form></details>}
   <details><summary>Recent events and counts</summary>
    <p className="subtle">{plural(a.received,'event')} received · {a.processed} processed · {a.deduplicated} duplicate deliveries · {a.quarantined} quarantined · {a.unmatched} unmatched · {a.failed} failed · {a.waiting} waiting · {plural(a.checks_updated,'check')} updated across {plural(a.affected_cases,'case')} · {plural(a.suggestions,'suggestion')} · {plural(a.drafts_prepared,'draft')} prepared · {plural(a.reviewer_actions,'reviewer action')}. {a.note}</p>
    <ul>{d.events.map((e:Row)=><li key={e.id}><code>{e.external_id}</code> · {e.source_name} · {e.status}{e.reason?` (${e.reason.replace(/_/g,' ')})`:''}{e.case_id?` · ${e.case_id}`:''} · {stamp(e.received_at)}
     {['unmatched','ambiguous'].includes(e.status)&&<> <button type="button" className="text-button" disabled={busy} onClick={()=>run(()=>api(`/sources/events/${e.id}/reroute`,{}))}>Re-evaluate routing</button></>}</li>)}</ul>
   </details></>}
 </section>;
}
