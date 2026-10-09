"use client";
import { useEffect,useState } from "react";
export default function JobProgress({status,createdAt}:{status:string;createdAt?:string}) {
  const [now,setNow]=useState(Date.now());
  useEffect(()=>{const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[]);
  const start=createdAt?Date.parse(createdAt):NaN,seconds=Number.isFinite(start)?Math.max(0,Math.floor((now-start)/1000)):null;
  const phase=status==="queued"?0:1;
  return <div className="job-status">
    <div className="progress-line" aria-hidden="true"/>
    <strong role="status">{phase===0?"Investigation queued":"Investigation running"}</strong>
    <ol className="job-phases" aria-label="Investigation progress">{["Queued","Gather & investigate","Ready to review"].map((label,i)=><li key={label} className={i===phase?"current":i<phase?"done":""} aria-current={i===phase?"step":undefined}><i aria-hidden="true">{i<phase?"✓":i+1}</i>{label}</li>)}</ol>
    <p>Your investigation continues if you leave this page.</p>
    {seconds!==null&&<p aria-hidden="true"><time>{seconds}s</time> since queued · duration depends on the worker and model.</p>}
  </div>;
}
