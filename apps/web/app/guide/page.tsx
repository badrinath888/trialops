"use client";
import Link from "next/link";
import { useState } from "react";
import { api } from "../lib";
import { Icon } from "../ui";
export default function Guide() {
  const [busy,setBusy]=useState(false),[error,setError]=useState("");
  async function sample(){setBusy(true);setError("");try{await api("/auth/demo",{});window.location.assign("/workspace");}catch(e){setError((e as Error).message);setBusy(false);}}
  const sections=[
    ["getting-started","Getting started","Try the sample workspace, or create an account for persistent work. Samples expire after 24 hours. Registered sessions last seven days."],
    ["submit","Submit an issue","Give the issue a clear title and description. Choose its study and site. Review classification suggestions before using them, then create the case."],
    ["investigate","Investigate","Run an investigation to retrieve procedures and historical site records. It continues in the background if you leave. Open Evidence or Records to inspect the details; the worker shows failures and allows retry."],
    ["review","Review & resolve","Check the full cited procedures, historical records, and draft text. Owners and reviewers can approve supported recommendations or reject with notes. Approval does not send drafts or close the case. Resolve separately after completing current checks; reopening preserves the activity trail."],
    ["knowledge","Knowledge & records","Owners can upload UTF-8 text, Markdown, or text-based PDFs up to 2 MB and 30 pages. Review extraction before saving. Scanned or encrypted PDFs are unsupported. Edits create versions; saved runs keep their earlier evidence. Import historical synthetic JSON records through Operational records using the example format."],
  ];
  return <><nav className="public-nav"><Link href="/" className="wordmark">TrialOps<span>✳</span></Link><div className="public-links"><Link href="/">← Back to home</Link></div><Link className="button outline" href="/sign-in">Sign in</Link><button disabled={busy} aria-busy={busy} onClick={sample}>{busy?"Preparing…":"Try sample workspace"}</button></nav>
    <main id="main-content" className="guide-page">{error&&<p className="error" role="alert">{error}</p>}<p className="eyebrow">PRODUCT GUIDE</p><h1>A clear path through the work.</h1><p className="hero-lead">Start with a case. Follow the evidence. Record your decision.</p>
    <div className="guide-layout"><nav className="guide-contents" aria-label="Guide contents">{sections.map(([id,title])=><a key={id} href={"#"+id}>{title}</a>)}<a href="#data-policy">Data policy</a></nav><div>
    <div className="guide-steps">{[["file","Choose a case","Open the issue and its context."],["search","Inspect the evidence","Review procedures and recorded conditions."],["check","Record a decision","Approve or reject after reviewing."]].map(([icon,title,text],i)=><article key={title}><span className="step-num">{i+1}</span><Icon name={icon} size={24}/><h2>{title}</h2><p>{text}</p></article>)}</div>
    {sections.map(([id,title,text])=><details key={id} id={id} className="guide-detail"><summary>{title}</summary><p>{text}</p></details>)}
      <details id="data-policy" className="guide-detail"><summary>Data policy & release boundaries</summary>
        <p>
          Do not enter patient identifiers, personal health information,
          clinical records, or confidential production data. This release has
          not undergone a healthcare compliance certification or independent
          security audit. It is suitable for synthetic operational evaluation
          and public feedback.
        </p>
        <p>
          Account identifiers, uploaded procedures, case descriptions, review
          notes, and feedback are stored in the deployment’s PostgreSQL
          database. Owners can export workspace records. No analytics,
          advertising trackers, or third-party AI APIs are enabled. If Ollama is
          configured on another server, selected issue and procedure text is
          sent to that configured server.
        </p>
        <p>
          Expired sample workspaces are removed by the worker. Registered
          workspaces persist until the operator removes them; backups may retain
          earlier data. The person hosting the application controls access,
          backup retention, and data deletion. Reviewer identity comes from the
          signed-in account; names are not independently verified.
        </p>
        <p>
          ROI values are scenario assumptions, not measured time savings or cash
          savings. Hardware, development, electricity, and maintenance costs are
          excluded unless you include them in your scenario assumptions.
        </p>
        <p>
          Feedback is retained for up to 30 days for the deployment operator.
          Expiring a sample workspace removes its workspace records, while
          feedback remains with the account and workspace association cleared.
        </p>
      </details>

    <details className="guide-detail"><summary>Can I try without an account?</summary><p>Yes. Try sample workspace creates your own temporary workspace with sample cases.</p></details>
    <details className="guide-detail"><summary>Does approval send an escalation?</summary><p>No. Approval records your review. Copying a draft does not send it.</p></details>
    <details className="guide-detail"><summary>Is this for patient care?</summary><p>No. TrialOps supports operational evaluation. Do not enter patient information or use it for clinical decisions.</p></details>
    <div className="actions"><button disabled={busy} aria-busy={busy} onClick={sample}>{busy?"Preparing…":"Try sample workspace"}</button><Link className="button outline" href="/sign-in?mode=register">Create a workspace</Link></div>
    </div></div></main></>;
}
