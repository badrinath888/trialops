"use client";
import {useCallback,useEffect,useState} from 'react';
import {api,stamp} from './lib';
type Row=Record<string,any>;
const LABEL:Record<string,string>={off:'Off',paused:'Paused',watching:'Watching',pending:'Change detected · checking',processing:'Processing update',failed:'Update failed',unavailable:'Unavailable'};
function Update({u}:{u:Row}){
 return <article className="work-item watch-update">
  <strong>{stamp(u.created_at)}{u.stale&&<span className="subtle"> · Stale: inputs changed since this update</span>}</strong>
  <p><b>What changed</b></p><ul>{u.changes.map((t:string,i:number)=><li key={i}>{t}</li>)}</ul>
  {u.uncertain.length>0&&<><p><b>Still uncertain</b></p><ul>{u.uncertain.map((t:string,i:number)=><li key={i}>{t}</li>)}</ul></>}
  <p><b>Suggested next review action</b> · {u.next_action}</p>
  <details><summary>Evidence references and model output</summary>
   <ul>{u.refs.map((r:Row,i:number)=><li key={i}><code>{r.id}</code> · version <code>{String(r.version).slice(0,12)}</code> · observed {r.observed_at?stamp(r.observed_at):'date not recorded'}</li>)}</ul>
   <small>Changes and linkage are detected deterministically (no AI).</small>
   {u.model.status==='completed'&&<><p><b>Local model suggestions · not verified</b></p><ul>{u.model.questions.map((q:Row,i:number)=><li key={i}>{q.question} <small>({q.uncertainty})</small></li>)}</ul></>}
   {u.model.status==='unavailable'&&<small> {u.model.detail}</small>}
  </details>
 </article>;
}
export function CaseWatch({cid,refreshKey}:{cid:string;refreshKey?:string}){
 const [d,setD]=useState<Row|null>(null),[hidden,setHidden]=useState(false),[error,setError]=useState(''),[busy,setBusy]=useState(false),[picked,setPicked]=useState<string[]|null>(null);
 const load=useCallback(async()=>{try{const r=await api('/cases/'+encodeURIComponent(cid)+'/watch');setD(r);setError('')}catch(e){const m=(e as Error).message;if((e as Row).status===403)setHidden(true);else setError(m)}},[cid]);
 useEffect(()=>{void load()},[load,refreshKey]);
 useEffect(()=>{if(!d||d.status!=='active')return;const t=setInterval(()=>void load(),['processing','pending'].includes(d.state)?4000:10000);return()=>clearInterval(t)},[d,load]);
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
    <Update u={d.updates[0]}/>
    {d.updates.length>1&&<details><summary>{d.updates.length-1} earlier update{d.updates.length>2?'s':''}</summary>{d.updates.slice(1).map((u:Row)=><Update key={u.id} u={u}/>)}</details>}
   </>}
  </>}
 </section>;
}
