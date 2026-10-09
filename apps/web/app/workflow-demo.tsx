"use client";
import { useState } from "react";
import { Icon } from "./ui";
const steps = [
  { label: "Procedure", icon: "file", title: "Start with a documented check", detail: "KB-001 · Certificate missing from binder", text: "Check the upload receipt, processing status, study assignment, and binder filters." },
  { label: "Record", icon: "clock", title: "Compare the recorded condition", detail: "25 minutes pending · historical sample", text: "The sample exceeds the procedure’s 15-minute threshold. Verify the current status and case linkage." },
  { label: "Review", icon: "shield", title: "You decide the next step", detail: "Engineering draft · unsent", text: "Review the cited procedure and draft. Approving records your decision; it does not send an escalation." },
];
export default function WorkflowDemo() {
  const [index,setIndex]=useState(0),step=steps[index];
  return <div className="workflow-demo">
    <p className="demo-caption">Click through the sample workflow</p>
    <div className="demo-selector" role="tablist" aria-label="Sample workflow">
      {steps.map((item,i)=><button key={item.label} type="button" role="tab" id={"demo-tab-"+i} aria-controls={"demo-panel-"+i} aria-selected={index===i} tabIndex={index===i?0:-1} onClick={()=>setIndex(i)} onKeyDown={e=>{let n=i;if(e.key==="ArrowRight")n=(i+1)%3;else if(e.key==="ArrowLeft")n=(i+2)%3;else if(e.key==="Home")n=0;else if(e.key==="End")n=2;else return;e.preventDefault();setIndex(n);(e.currentTarget.parentElement?.children[n] as HTMLElement)?.focus();}}>{item.label}</button>)}
    </div>
    <div key={index} role="tabpanel" id={"demo-panel-"+index} aria-labelledby={"demo-tab-"+index} className="demo-pane">
      <Icon name={step.icon} size={25}/><h3>{step.title}</h3><strong className="demo-label">{step.detail}</strong><p>{step.text}</p>
    </div>
  </div>;
}
