"use client";
import {useCallback,useEffect,useState} from 'react';
import {api,stamp} from './lib';
type Row=Record<string,any>;
const LABEL:Record<string,string>={off:'Off',paused:'Paused',watching:'Watching',pending:'Change detected · checking',processing:'Processing update',failed:'Update failed',unavailable:'Unavailable'};
function Refs({title,list}:{title:string;list:Row[]}){
 return <><p><b>{title}</b></p>{list.length===0?<p className="subtle">No exact record for these stages.</p>:<ul>{list.map((r:Row,i:number)=><li key={i}><code>{r.ref}</code> · {r.source_system} {r.source_ref} · {r.status?String(r.status).replace('_',' '):'no status'} · observed {stamp(r.observed_at)} · {r.role==='supporting'?'current':'historical'}</li>)}</ul>}</>;
}
function SourceUpdate({u,cid,reload}:{u:Row;cid:string;reload:()=>void}){
 const d=u.detail,[busy,setBusy]=useState(false),[err,setErr]=useState('');
 const review=async()=>{setBusy(true);setErr('');try{await api('/cases/'+encodeURIComponent(cid)+'/watch/updates/'+u.id+'/review',{});reload()}catch(e){setErr((e as Error).message)}finally{setBusy(false)}};
 return <article className="work-item watch-update source-update">
  <strong>{stamp(u.created_at)}{u.stale&&<span className="subtle"> · Superseded by newer evidence or changes</span>}</strong>
  <p className="source-headline" role="status">{u.changes[0]}</p>
  <p><b>Which checks changed</b></p><ul>{d.checks_updated.map((x:Row)=><li key={x.key}>{x.label} · {x.resolved?'now supported by exact evidence':'assessment changed; not resolved'}</li>)}</ul>
  <p><b>Still unknown or conflicting</b></p><ul>{u.uncertain.map((t:string,i:number)=><li key={i}>{t}</li>)}</ul>
  <p><b>Next action</b> · {u.next_action}</p>
  {d.draft?.state==='prepared'&&<p role="status">An unsent draft request was prepared (draft requests are in Missing-information requests). Nothing was sent.</p>}
  {d.draft?.state==='not_prepared'&&<p className="subtle">No draft prepared: {d.draft.reason}</p>}
  {d.ranking_stale&&<p className="subtle">The saved request order is now stale; it was not changed. Refresh it in the collection plan.</p>}
  {err&&<p role="alert">{err}</p>}
  <div className="actions"><button className="outline" disabled={busy} onClick={review}>Mark reviewed</button></div>
  <details><summary>Before/after evidence references and source details</summary>
   <Refs title="Before" list={d.evidence_before.filter((r:Row)=>!d.evidence_after.some((x:Row)=>x.ref===r.ref&&x.role===r.role))}/>
   <Refs title="After" list={d.evidence_after}/>
   <small>Source {d.source.name} · event <code>{d.source.event_id}</code> · revision {d.source.source_rev} · observed {stamp(d.source.observed_at)} · received {stamp(d.source.received_at)} · schema {d.source.schema_version} · hash <code>{d.source.content_hash.slice(0,12)}</code>. Synthetic mock source; not a real integration.</small>
  </details>
 </article>;
}
function Update({u,cid,reload}:{u:Row;cid:string;reload:()=>void}){
 if(u.detail)return <SourceUpdate u={u} cid={cid} reload={reload}/>;
 return <article className="work-item watch-update">
  <strong>{stamp(u.created_at)}{u.stale&&<span className="subtle"> · Stale: inputs changed since this update</span>}</strong>
  <p><b>What changed</b></p><ul>{u.changes.map((t:string,i:number)=><li key={i}>{t}</li>)}</ul>
  {u.uncertain.length>0&&<><p><b>Still uncertain</b></p><ul>{u.uncertain.map((t:string,i:number)=><li key={i}>{t}</li>)}</ul></>}
  <p><b>Suggested next review action</b> · {u.next_action}</p>
  <details><summary>Evidence references and model output</summary>
   <ul>{u.refs.map((r:Row,i:number)=><li key={i}><code>{r.id}</code> · version <code>{String(r.version).slice(0,12)}</code> · observed {r.observed_at?stamp(r.observed_at):'date not recorded'}</li>)}</ul>
   <small>Changes and linkage are detected deterministically (no AI).</small>
   {u.model.status==='completed'&&<><p><b>Local model suggestions · not verified</b></p><ul>{u.model.questions.map((q:Row,i:number)=><li key={i}>{q.question} <small>({q.uncertainty})</small></li>)}</ul></>}
   {u.model.status==='unavailable'&&<small> {u.model.detail}{u.model.failure&&` Diagnosis: ${u.model.failure.category}${u.model.failure.reason?' · '+u.model.failure.reason:''} · attempts ${u.model.failure.attempts}.`}</small>}
  </details>
 </article>;
}
export function CaseWatch({cid,refreshKey}:{cid:string;refreshKey?:string}){
 const [d,setD]=useState<Row|null>(null),[hidden,setHidden]=useState(false),[error,setError]=useState(''),[busy,setBusy]=useState(false),[picked,setPicked]=useState<string[]|null>(null);
 const load=useCallback(async()=>{try{const r=await api('/cases/'+encodeURIComponent(cid)+'/watch');setD(r);setError('')}catch(e){const m=(e as Error).message;if((e as Row).status===403)setHidden(true);else setError(m)}},[cid]);
 useEffect(()=>{void load()},[load,refreshKey]);
 useEffect(()=>{if(!d)return;const t=setInterval(()=>void load(),['processing','pending'].includes(d.state)?4000:d.status==='active'?10000:20000);return()=>clearInterval(t)},[d,load]);
 useEffect(()=>{const f=()=>void load();window.addEventListener('focus',f);return()=>window.removeEventListener('focus',f)},[load]);
 if(hidden)return null;
 const act=async(status:string,ids?:string[])=>{setBusy(true);try{setD(await api('/cases/'+encodeURIComponent(cid)+'/watch',{status,evidence_ids:ids??d?.evidence_ids??[]}));setPicked(null);setError('')}catch(e){setError((e as Error).message)}finally{setBusy(false)}};
 const retry=async()=>{setBusy(true);try{setD(await api('/cases/'+encodeURIComponent(cid)+'/watch/retry',{}));setError('')}catch(e){setError((e as Error).message)}finally{setBusy(false)}};
 const ids=picked??d?.evidence_ids??[],on=d&&d.status==='active';
 return <section className="panel case-watch" aria-label="Case watch">
  <div className="section-heading"><h2>Case watch</h2><span role="status">{d?LABEL[d.state]:'Loading…'}</span></div>
  {error&&<p role="alert">{error}</p>}
  {d&&<>
   <div className="actions">
    {d.status==='active'?<button className="outline" disabled={busy} onClick={()=>act('paused')}>Pause</button>:<button disabled={busy||d.state==='unavailable'} onClick={()=>act('active',ids)}>{d.status==='paused'?'Resume watch':'Watch this case'}</button>}
    {d.status!=='disabled'&&<button className="outline" disabled={busy} onClick={()=>act('disabled')}>Stop watching</button>}
    {d.state==='failed'&&<button disabled={busy} onClick={retry}>Retry update</button>}
   </div>
   {d.pause_reason&&d.status==='paused'&&<p role="status">{d.pause_reason}</p>}
   {d.state==='failed'&&<p role="alert">The last update failed. Nothing was confirmed or sent. Retry when ready.</p>}
   {d.state==='unavailable'&&<p>Resolved cases are not watched. Reopen the case to watch it.</p>}
   <small>Watches new responses, same study/site snapshots, selected evidence and confirmed links. It never approves, confirms evidence, sends or resolves.</small>
   <details><summary>Choose evidence to watch (optional) · {ids.length} selected</summary>
    {d.sources.length===0?<p>No case records or observations yet.</p>:d.sources.map((s:Row)=><label key={s.id}><input type="checkbox" checked={ids.includes(s.id)} disabled={!ids.includes(s.id)&&ids.length>=10} onChange={e=>setPicked(e.target.checked?[...ids,s.id]:ids.filter((x:string)=>x!==s.id))}/> {s.label}</label>)}
    {picked&&<button className="outline" disabled={busy||d.state==='unavailable'} onClick={()=>act(on?'active':d.status==='paused'?'paused':'active',picked)}>Save selection · only later changes are reported</button>}
   </details>
   {d.updates.length===0?<p>{on?'No relevant changes since watching began.':'No updates yet.'}</p>:<>
    <Update u={d.updates[0]} cid={cid} reload={()=>void load()}/>
    {d.updates.length>1&&<details><summary>{d.updates.length-1} earlier update{d.updates.length>2?'s':''}</summary>{d.updates.slice(1).map((u:Row)=><Update key={u.id} u={u} cid={cid} reload={()=>void load()}/>)}</details>}
   </>}
  </>}
 </section>;
}
