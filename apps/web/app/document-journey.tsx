"use client";
import { useCallback, useEffect, useState } from "react";
import { api, plural, stamp } from "./lib";
import { SuggestedOrder } from "./priority-panel";
type Row = Record<string, any>;
const uid = () => crypto.randomUUID();
const humanize = (s?: string | null) => (s ? s.replace(/_/g, " ") : "");
const STATUS: Record<string, string[]> = {
  upload_receipt: ["received"], processing: ["pending", "running", "completed", "failed"], transfer: ["queued", "pending", "running", "completed", "failed"],
  destination_filing: ["pending", "completed", "failed"], binder_visibility: ["visible", "not_visible"],
};
const STAGE_LABEL: Record<string, string> = { upload_receipt: "Upload receipt", processing: "Processing", transfer: "Transfer / synchronization", destination_filing: "Destination filing", binder_visibility: "Binder visibility" };
const OVERALL: Record<string, string> = { verified: "Verified", not_verified: "Not verified", partially_verified: "Partially verified", insufficient_evidence: "Insufficient evidence" };
const RESULT: Record<string, string> = { verified: "Verified", contradicted: "Contradicted", insufficient: "Insufficient evidence" };
const BASIS: Record<string, string> = { native: "same-system identifier", source_declared: "source-declared cross-reference", reviewer_link: "reviewer-confirmed link" };
const LINK_KIND: Record<string, string> = { unlinked: "record", id_collision: "document", destination_collision: "destination" };
const toIso = (local: string) => (local ? new Date(local).toISOString() : null);

function Fields({ raw }: { raw: Row }) {
  return <details className="journey-fields"><summary>Supporting fields</summary><dl>{Object.entries(raw).map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd></div>)}</dl></details>;
}

function RecordLine({ r, extra }: { r: Row; extra?: React.ReactNode }) {
  return <li className="journey-record">
    <div><b>{r.source_system}</b> · {r.source_ref}{r.document_ref ? ` · document ${r.document_ref}` : " · no document reference"}{r.version ? ` v${r.version}` : ""}{r.transfer_ref ? ` · transfer ${r.transfer_ref}` : ""}{r.binder_ref ? ` · binder ${r.binder_ref}` : ""}</div>
    <div className="subtle">{r.status ? humanize(r.status) : r.status_raw ? `status “${r.status_raw}” not mapped` : "status not recorded"} · observed {stamp(r.observed_at)} · export {r.export_ref}{r.export_complete ? "" : " (incomplete)"}
      {r.role === "attested" ? ` · attested by ${r.attested_by} from a reviewed response; not verified by a system record${r.problems?.length ? "; not matched to this document: " + r.problems.map(humanize).join(", ") : ""}` : r.match_basis && r.role !== "excluded" ? ` · matched by ${BASIS[r.match_basis]}` : ""}{r.role === "earlier_observation" ? " · earlier observation" : ""}{r.stale ? " · older than the workspace freshness policy" : ""}</div>
    {r.link && <div className="subtle">Link rationale: {r.link.rationale} Evidence: {r.link.evidence} ({r.link.actor_name})</div>}
    {extra}<Fields raw={r.raw} />
  </li>;
}

function ConfirmLink({ cid, cand, snap, reload, setError }: { cid: string; cand: Row; snap: Row[]; reload: () => void; setError: (s: string) => void }) {
  const kind = LINK_KIND[cand.problems[0]];
  const [why, setWhy] = useState(""), [ev, setEv] = useState(""), [basis, setBasis] = useState(""), [busy, setBusy] = useState(false);
  if (!kind) return null;
  const from = kind === "destination" ? cand.binder_ref : kind === "document" ? cand.document_ref : cand.source_ref;
  const usable = kind === "destination" ? [] : snap.filter(x => !x.stale && x.exact_matches.some((m: Row) => m.left === from && m.field === (kind === "document" ? "document_id" : "job_id")));
  const go = async (e: React.FormEvent) => { e.preventDefault(); setBusy(true); setError(""); try { await api(`/cases/${encodeURIComponent(cid)}/journey/links`, { id: uid(), kind, from_system: cand.source_system, from_ref: from, rationale: why, evidence: ev, snapshot_decision_id: basis || null }); setWhy(""); setEv(""); reload(); } catch (x) { setError((x as Error).message); } finally { setBusy(false); } };
  return <details className="journey-inline"><summary>Confirm {kind} link for {cand.source_system} {from}</summary>
    <form onSubmit={go}><label>Why does this identify the intended {kind === "destination" ? "binder" : "document"}?<textarea value={why} onChange={e => setWhy(e.target.value)} rows={2} minLength={10} maxLength={1000} required /></label>
      <label>Evidence you reviewed<input value={ev} onChange={e => setEv(e.target.value)} minLength={5} maxLength={1000} required /></label>
      {usable.length > 0 && <label>Also rely on an existing confirmed link (optional; it otherwise applies to saved snapshots only)<select value={basis} onChange={e => setBasis(e.target.value)}><option value="">No</option>{usable.map(x => <option key={x.id} value={x.id}>Confirmed {stamp(x.at)} by {x.actor}</option>)}</select></label>}
      <button disabled={busy}>Save reviewed link</button></form></details>;
}

function Gap({ cid, stage, gap, contacts, onOpen, prioritizationId, reload, setError }: { cid: string; stage: string; gap: Row; contacts: Row[]; onOpen: () => void; prioritizationId?: string | null; reload: () => void; setError: (s: string) => void }) {
  const [q, setQ] = useState(gap.question), [contact, setContact] = useState(""), [dup, setDup] = useState(""), [busy, setBusy] = useState(false), [ok, setOk] = useState(false);
  const go = async (e: React.FormEvent) => { e.preventDefault(); setBusy(true); setError(""); try { await api(`/cases/${encodeURIComponent(cid)}/journey/collection`, { id: uid(), request_id: uid(), stage, gap_key: gap.key, question: q, would_settle: gap.would_settle, contact_id: contact || null, duplicate_reason: dup, prioritization_id: prioritizationId || null }); setOk(true); reload(); } catch (x) { setError((x as Error).message); } finally { setBusy(false); } };
  return <details className="journey-inline" onToggle={e => (e.currentTarget as HTMLDetailsElement).open && onOpen()}><summary>Plan evidence request · {gap.description}</summary>
    <form onSubmit={go}>
      <label>Question (editable; saved as an unsent draft)<textarea value={q} onChange={e => setQ(e.target.value)} rows={3} minLength={10} maxLength={1500} required /></label>
      <p className="subtle">Would settle: {gap.would_settle}</p>
      <label>Responsible contact (your choice; none is assumed)<select value={contact} onChange={e => setContact(e.target.value)}><option value="">No contact selected</option>{contacts.map(c => <option key={c.id} value={c.id}>{c.name} · {c.primary_contact}</option>)}</select></label>
      <label>Reason, only if a similar open request already exists<input value={dup} onChange={e => setDup(e.target.value)} maxLength={2000} /></label>
      <button disabled={busy}>Save draft request</button>{ok && <small role="status"> Draft saved in Missing-information requests. Nothing was sent.</small>}
    </form></details>;
}

function Attest({ cid, stage, responses, reload, setError }: { cid: string; stage: string; responses: Row[]; reload: () => void; setError: (s: string) => void }) {
  const [f, setF] = useState({ response_ref: "", source_system: "", source_ref: "", document_ref: "", version: "", binder_ref: "", transfer_ref: "", status: "", at: "", why: "" }), [busy, setBusy] = useState(false);
  const set = (k: string) => (e: React.ChangeEvent<any>) => setF({ ...f, [k]: e.target.value });
  const go = async (e: React.FormEvent) => { e.preventDefault(); setBusy(true); setError(""); try { await api(`/cases/${encodeURIComponent(cid)}/journey/attestations`, { id: uid(), response_ref: f.response_ref, stage, source_system: f.source_system, source_ref: f.source_ref, document_ref: f.document_ref || null, version: f.version || null, binder_ref: f.binder_ref || null, transfer_ref: f.transfer_ref || null, status: f.status || null, observed_at: toIso(f.at), rationale: f.why }); reload(); } catch (x) { setError((x as Error).message); } finally { setBusy(false); } };
  return <details className="journey-inline"><summary>Record a reviewed response as an attested observation</summary>
    <form onSubmit={go}><p className="subtle">Copy the structured identifiers the response reports. Reviewing a response does not make it a verified fact: this stays attested context until a system record supports it.</p>
      <label>Reviewed response<select value={f.response_ref} onChange={set("response_ref")} required><option value="">Choose a reviewed response</option>{responses.map(r => <option key={r.ref} value={r.ref}>{r.kind} · {stamp(r.submitted_at)} · {r.text.slice(0, 60)}</option>)}</select></label>
      <div className="journey-grid"><label>Source system<input value={f.source_system} onChange={set("source_system")} pattern="[a-z0-9][a-z0-9_\-]{1,59}" required /></label><label>Record reference<input value={f.source_ref} onChange={set("source_ref")} required /></label>
        <label>Document ID<input value={f.document_ref} onChange={set("document_ref")} /></label><label>Version<input value={f.version} onChange={set("version")} /></label>
        <label>Binder ID<input value={f.binder_ref} onChange={set("binder_ref")} /></label><label>Transfer ID<input value={f.transfer_ref} onChange={set("transfer_ref")} /></label>
        <label>Reported status<select value={f.status} onChange={set("status")}><option value="">Not stated</option>{STATUS[stage].map(x => <option key={x} value={x}>{humanize(x)}</option>)}</select></label>
        <label>Observed at (from the response)<input type="datetime-local" value={f.at} onChange={set("at")} required /></label></div>
      <label>Why these fields reflect the response<input value={f.why} onChange={set("why")} minLength={10} maxLength={1000} required /></label>
      <button disabled={busy}>Save attested observation</button></form></details>;
}

function Stage({ s, cid, me, contacts, onOpen, reload, setError }: { s: Row; cid: string; me: Row; contacts: Row[]; onOpen: () => void; reload: () => void; setError: (e: string) => void }) {
  const reviewer = me.can_write;
  return <details className={"journey-stage a-" + s.assessment}>
    <summary><span className="journey-label">{s.label}</span>
      <span className="journey-status">{s.operational_status ? humanize(s.operational_status) : "status not recorded"}</span>
      <span className="journey-assess">{s.assessment === "verified" ? "Verified" : s.assessment === "conflicting" ? "Conflicting" : "Unknown"}</span>
      <span className="journey-asof">{s.as_of ? "as of " + stamp(s.as_of) : "no observation"}</span></summary>
    <div className="journey-body">
      {s.conflicts.map((m: string, i: number) => <p key={i} className="journey-warn">{m}</p>)}
      {s.missing.length > 0 && <ul className="journey-missing">{s.missing.map((m: string, i: number) => <li key={i}>{m}</li>)}</ul>}
      {s.notes.map((m: string, i: number) => <p key={i} className="subtle">{m}</p>)}
      {s.records.length > 0 && <ul className="journey-records">{s.records.map((r: Row) => <RecordLine key={r.ref} r={r} />)}</ul>}
      {s.candidates.length > 0 && <><h4>Excluded candidates (not treated as this document)</h4>
        <ul className="journey-records">{s.candidates.map((r: Row) => <RecordLine key={r.ref} r={r} extra={<><div className="journey-warn">Excluded: {r.problems.map(humanize).join(", ")}</div>{reviewer && <ConfirmLink cid={cid} cand={r} snap={me.snapshot_links || []} reload={reload} setError={setError} />}</>} />)}</ul></>}
      {s.attested?.length > 0 && <><h4>Attested by a reviewed response (not verification)</h4><ul className="journey-records">{s.attested.map((r: Row) => <RecordLine key={r.ref} r={r} />)}</ul></>}
      {reviewer && (me.responses || []).length > 0 && <Attest cid={cid} stage={s.stage} responses={me.responses} reload={reload} setError={setError} />}
      {reviewer && s.gaps.map((g: Row) => <Gap key={g.key} cid={cid} stage={s.stage} gap={g} contacts={contacts} onOpen={onOpen} reload={reload} setError={setError} />)}
    </div>
  </details>;
}

function Subject({ cid, d, reload, setError }: { cid: string; d: Row; reload: () => void; setError: (s: string) => void }) {
  const s = d.subject, [f, setF] = useState({ document_system: s?.document_system || "", document_ref: s?.document_ref || "", document_version: s?.document_version || "", destination_system: s?.destination_system || "", binder_ref: s?.binder_ref || "" }), [busy, setBusy] = useState(false);
  const go = async (e: React.FormEvent) => { e.preventDefault(); setBusy(true); setError(""); try { await api(`/cases/${encodeURIComponent(cid)}/journey/subject`, { id: uid(), expected_rev: s?.rev || 0, ...f }); reload(); } catch (x) { setError((x as Error).message); } finally { setBusy(false); } };
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  return <form onSubmit={go} className="journey-grid" aria-label="Document and intended binder">
    <label>Document system<input value={f.document_system} onChange={set("document_system")} placeholder="e.g. mock-upload-portal" pattern="[a-z0-9][a-z0-9_\-]{1,59}" required /></label>
    <label>Document ID<input value={f.document_ref} onChange={set("document_ref")} pattern="[A-Za-z0-9][A-Za-z0-9_.\-]{0,99}" required /></label>
    <label>Version<input value={f.document_version} onChange={set("document_version")} pattern="[A-Za-z0-9][A-Za-z0-9_.\-]{0,29}" required /></label>
    <label>Destination system<input value={f.destination_system} onChange={set("destination_system")} placeholder="e.g. mock-binder-hub" pattern="[a-z0-9][a-z0-9_\-]{1,59}" required /></label>
    <label>Intended binder ID<input value={f.binder_ref} onChange={set("binder_ref")} pattern="[A-Za-z0-9][A-Za-z0-9_.\-]{0,99}" required /></label>
    <button disabled={busy}>{s ? "Save revision" : "Save definition"}</button></form>;
}

function Outcomes({ cid, d, reload, setError }: { cid: string; d: Row; reload: () => void; setError: (s: string) => void }) {
  const blank = { key: "", rev: 0, desc: "", human: false, reqs: [{ stage: "destination_filing", status: "completed" }, { stage: "binder_visibility", status: "visible" }], at: "", required: true };
  const [f, setF] = useState<Row>(blank), [busy, setBusy] = useState(false), [rat, setRat] = useState(""), [hum, setHum] = useState<Row>({});
  const ver = d.verifications[0], humanOnes = d.outcomes.filter((o: Row) => !o.requirements);
  const save = async (e: React.FormEvent, retired = false) => { e.preventDefault(); setBusy(true); setError(""); try { await api(`/cases/${encodeURIComponent(cid)}/journey/outcomes`, { id: uid(), key: f.key || uid(), expected_rev: f.rev, description: f.desc, requirements: f.human ? null : f.reqs, required: f.required, remediation_at: f.human ? null : toIso(f.at), retired }); setF(blank); reload(); } catch (x) { setError((x as Error).message); } finally { setBusy(false); } };
  const edit = (o: Row) => setF({ key: o.outcome_key, rev: o.rev, desc: o.description, human: !o.requirements, reqs: o.requirements || blank.reqs, at: o.remediation_at ? new Date(new Date(o.remediation_at).getTime() - new Date(o.remediation_at).getTimezoneOffset() * 60000).toISOString().slice(0, 16) : "", required: o.required });
  const run = async (e: React.FormEvent) => { e.preventDefault(); setBusy(true); setError(""); try { await api(`/cases/${encodeURIComponent(cid)}/journey/verify`, { id: uid(), rationale: rat, human: Object.fromEntries(Object.entries(hum).filter(([, v]: [string, any]) => v.result).map(([k, v]: [string, any]) => [k, { result: v.result, rationale: v.rationale || "" }])) }); setRat(""); setHum({}); reload(); } catch (x) { setError((x as Error).message); } finally { setBusy(false); } };
  const reqEdit = (i: number, p: Row) => setF({ ...f, reqs: f.reqs.map((r: Row, j: number) => j === i ? { ...r, ...p, ...(p.stage ? { status: STATUS[p.stage][0] } : {}) } : r) });
  return <details className="journey-section"><summary>Expected outcomes and verification · {plural(d.outcomes.length, "outcome")}{ver ? ` · ${OVERALL[ver.overall]}${ver.current ? "" : " (historical)"}` : ""}</summary>
    <p className="subtle">Verification compares later, authorized evidence with the saved outcomes. It never approves, resolves or reopens the case; those stay separate human actions.</p>
    {d.freshness_hours != null ? <p className="subtle">Workspace freshness policy: observations older than {d.freshness_hours} hours do not verify.</p> : <p className="subtle">No workspace freshness policy is configured, so no age limit is applied.</p>}
    <ul className="journey-records">{d.outcomes.map((o: Row) => {
      const res = ver?.results.find((r: Row) => r.outcome_key === o.outcome_key);
      return <li key={o.outcome_key} className="journey-record"><div>{o.description} <small className="subtle">#{o.outcome_key.slice(0, 8)}</small>{!o.required && " (optional)"} <small className="subtle">revision {o.rev} · {o.requirements ? o.requirements.map((r: Row) => `${STAGE_LABEL[r.stage]} = ${humanize(r.status)}`).join("; ") + ` · later than ${stamp(o.remediation_at)}` : "human assessment required"}</small></div>
        {res && <div className="subtle">{ver.current ? "Latest" : "Historical"} result: <b>{RESULT[res.result]}</b>{res.method === "needs_human_assessment" ? " — needs a human assessment" : ""}{res.reason ? ` · ${res.reason}` : res.parts.map((p: Row) => ` ${STAGE_LABEL[p.stage]}: ${p.reason}.`).join("")}</div>}
        {d.can_write && <button type="button" className="text-button" onClick={() => edit(o)}>Revise</button>}</li>; })}</ul>
    {d.can_write && <>
      <form onSubmit={e => save(e)} className="journey-form" aria-label="Expected outcome">
        <label>Expected outcome (before remediation){f.key && <small> · revising</small>}<textarea value={f.desc} onChange={e => setF({ ...f, desc: e.target.value })} rows={2} minLength={10} maxLength={500} required placeholder="The same document/version is filed and visible in the intended binder." /></label>
        <label className="check"><input type="checkbox" checked={f.human} onChange={e => setF({ ...f, human: e.target.checked })} /> Cannot be checked deterministically — a reviewer must assess it</label>
        {!f.human && <><div className="journey-grid">{f.reqs.map((r: Row, i: number) => <div key={i} className="journey-req"><label>Stage<select value={r.stage} onChange={e => reqEdit(i, { stage: e.target.value })}>{Object.keys(STATUS).map(k => <option key={k} value={k}>{STAGE_LABEL[k]}</option>)}</select></label>
          <label>Must be<select value={r.status} onChange={e => reqEdit(i, { status: e.target.value })}>{STATUS[r.stage].map(x => <option key={x} value={x}>{humanize(x)}</option>)}</select></label>
          <button type="button" className="text-button" onClick={() => setF({ ...f, reqs: f.reqs.filter((_: Row, j: number) => j !== i) })} disabled={f.reqs.length < 2}>Remove</button></div>)}</div>
          {f.reqs.length < 5 && <button type="button" className="outline" onClick={() => setF({ ...f, reqs: [...f.reqs, { stage: "destination_filing", status: "completed" }] })}>Add requirement</button>}
          <label>Remediation applied at (only later observations count)<input type="datetime-local" value={f.at} onChange={e => setF({ ...f, at: e.target.value })} required /></label></>}
        <label className="check"><input type="checkbox" checked={f.required} onChange={e => setF({ ...f, required: e.target.checked })} /> Required for the overall result</label>
        <div className="journey-buttons"><button disabled={busy}>{f.key ? "Save revision" : "Save outcome"}</button>
          {f.key && <><button type="button" className="outline" disabled={busy} onClick={e => save(e as any, true)}>Retire outcome</button><button type="button" className="outline" onClick={() => setF(blank)}>Cancel</button></>}</div>
      </form>
      <form onSubmit={run} className="journey-form" aria-label="Verify outcomes">
        <h4>Verify against current evidence</h4>
        {humanOnes.map((o: Row) => <fieldset key={o.outcome_key}><legend>Your assessment: {o.description} · #{o.outcome_key.slice(0, 8)}</legend>
          <label>Result<select value={hum[o.id]?.result || ""} onChange={e => setHum({ ...hum, [o.id]: { ...hum[o.id], result: e.target.value } })}><option value="">Not assessed yet</option><option value="verified">Verified</option><option value="contradicted">Contradicted</option><option value="insufficient">Insufficient evidence</option></select></label>
          <label>Rationale<input value={hum[o.id]?.rationale || ""} onChange={e => setHum({ ...hum, [o.id]: { ...hum[o.id], rationale: e.target.value } })} minLength={10} maxLength={1000} required={!!hum[o.id]?.result} /></label></fieldset>)}
        <label>Rationale for this verification<input value={rat} onChange={e => setRat(e.target.value)} minLength={10} maxLength={1000} required /></label>
        <button disabled={busy || d.outcomes.length === 0}>Record verification</button>
      </form></>}
    {ver && <p role="status"><b>{OVERALL[ver.overall]}</b> — recorded {stamp(ver.created_at)} by {ver.actor_name}. {ver.current ? "Reflects the evidence and outcomes shown now." : "Historical: outcomes or evidence changed since."}</p>}
    {d.outcome_history.length > d.outcomes.length && <details><summary>Outcome revision history ({d.outcome_history.length})</summary><ul>{d.outcome_history.map((o: Row) => <li key={o.id}>{stamp(o.created_at)} · {o.actor_name} · revision {o.rev}{o.retired ? " (retired)" : ""} · {o.description}</li>)}</ul></details>}
  </details>;
}

function Replay({ cid }: { cid: string }) {
  const [rows, setRows] = useState<Row[] | null>(null), [err, setErr] = useState("");
  const load = () => { if (!rows) api(`/cases/${encodeURIComponent(cid)}/journey/replay`).then(r => setRows(r.decisions)).catch(e => setErr(e.message)); };
  return <details className="journey-section" onToggle={e => (e.currentTarget as HTMLDetailsElement).open && load()}><summary>Decision replay · what was known at each saved decision</summary>
    {err && <p role="alert" className="error">{err}</p>}{!rows && !err && <p role="status">Loading…</p>}
    {rows?.length === 0 && <p className="subtle">No saved review or verification decisions yet.</p>}
    {rows?.map(r => <details key={r.id} className="journey-inline"><summary>{stamp(r.at)} · {r.kind === "verification" ? "Verification" : "Investigation review"} · {humanize(r.decision)} · {r.actor}</summary>
      <p><b>Recorded rationale:</b> {r.rationale || "none recorded"}</p>
      {!r.complete ? <p className="journey-warn">Replay incomplete. {r.incomplete_reason}</p> : <>
        <p><b>Known then:</b> {r.known.length ? r.known.map((k: Row) => `${k.label} (${humanize(k.operational_status) || "no status"})`).join("; ") : "no stage was verified"}.</p>
        <p><b>Unknown or conflicting then:</b> {r.unknown.length ? r.unknown.map((k: Row) => `${k.label}: ${k.conflicts[0] || k.missing[0]}`).join(" ") : "none"}</p>
        <p><b>Changed afterwards:</b> {[plural(r.changed_since.exports.length, "new export"), plural(r.changed_since.links.length, "link change"), plural(r.changed_since.outcome_revisions.length, "outcome revision"), plural(r.changed_since.stages.length, "stage difference")].join(", ")}.{r.changed_since.same_evidence_as_now ? " The journey evidence is unchanged." : ""}</p>
        {r.changed_since.stages.map((x: Row) => <p key={x.stage} className="subtle">{STAGE_LABEL[x.stage]}: {x.was}{x.status_was ? ` (${humanize(x.status_was)})` : ""} → {x.now}{x.status_now ? ` (${humanize(x.status_now)})` : ""}</p>)}</>}
      <p className="subtle">Recorded inputs only; this decision is immutable.</p></details>)}
  </details>;
}

function Importer({ cid, onDone, setError }: { cid: string; onDone: () => void; setError: (s: string) => void }) {
  const [exp, setExp] = useState(""), [map, setMap] = useState(""), [busy, setBusy] = useState(false), [ok, setOk] = useState("");
  const example = async (shape: string) => { try { const r = await api(`/cases/${encodeURIComponent(cid)}/journey/example?shape=${shape}`); setExp(JSON.stringify(r.export, null, 1)); setMap(JSON.stringify(r.mapping, null, 1)); } catch (x) { setError((x as Error).message); } };
  const go = async (e: React.FormEvent) => { e.preventDefault(); setBusy(true); setError(""); setOk(""); try { const r = await api("/operations/journey-import", { export: JSON.parse(exp), mapping: JSON.parse(map) }); setOk(r.status === "imported" ? `Imported ${plural(r.records, "record")}.` : "Already imported; nothing changed."); onDone(); } catch (x) { setError(x instanceof SyntaxError ? "Export and mapping must be valid JSON." : (x as Error).message); } finally { setBusy(false); } };
  return <form onSubmit={go} className="journey-form" aria-label="Import synthetic export">
    <p className="subtle">Synthetic mock-system exports only. Each export names its source system, coverage (complete or not), observation time and an explicit field mapping. Free-text fields are kept but never read for identifiers or times.</p>
    <div className="journey-buttons"><button type="button" className="outline" onClick={() => example("portal")}>Fill portal-shaped example</button><button type="button" className="outline" onClick={() => example("hub")}>Fill hub-shaped example</button></div>
    <label>Export (JSON)<textarea value={exp} onChange={e => setExp(e.target.value)} rows={5} required spellCheck={false} /></label>
    <label>Field mapping (JSON)<textarea value={map} onChange={e => setMap(e.target.value)} rows={5} required spellCheck={false} /></label>
    <button disabled={busy}>Validate and import</button>{ok && <small role="status"> {ok}</small>}</form>;
}

export function DocumentJourney({ cid, me, refreshKey }: { cid: string; me: Row; refreshKey?: string }) {
  const [d, setD] = useState<Row | null>(null), [error, setError] = useState(""), [contacts, setContacts] = useState<Row[]>([]), [planOpen, setPlanOpen] = useState(false);
  const load = useCallback(async () => { try { setD(await api(`/cases/${encodeURIComponent(cid)}/journey`)); setError(""); } catch (e) { setError((e as Error).message); } }, [cid]);
  useEffect(() => { void load(); }, [load, refreshKey]);
  const loadContacts = useCallback(() => { if (["owner", "reviewer"].includes(me.role) && contacts.length === 0) api("/contacts").then(setContacts).catch(() => setContacts([])); }, [me.role, contacts.length]);
  if (!d) return <section className="panel journey-panel" aria-busy="true">{error ? <p role="alert" className="error">{error}</p> : <p role="status">Loading document journey…</p>}</section>;
  const j = d.journey, s = d.subject, n = j ? j.stages.filter((x: Row) => x.assessment === "verified").length : 0;
  return <section className="panel journey-panel" aria-label="Document journey">
    <header><h3>Document journey</h3><small>{j ? `${n} of 5 stages verified · ${plural(d.exports.length, "export")} imported` : "Define the document to begin"}</small></header>
    {error && <p role="alert" className="error">{error}</p>}
    {s && <p className="journey-subject"><b>{s.document_system}</b> {s.document_ref} version {s.document_version} → <b>{s.destination_system}</b> binder {s.binder_ref}</p>}
    {j && <><ul className="journey-findings">{j.findings.map((f: string, i: number) => <li key={i}>{f}</li>)}</ul>
      <p className="subtle">{j.interpretation}</p>
      <div className="journey-stages">{j.stages.map((st: Row) => <Stage key={st.stage} s={st} cid={cid} me={d} contacts={contacts} onOpen={loadContacts} reload={load} setError={setError} />)}</div></>}
    {d.can_write ? <details className="journey-section"><summary>{s ? "Document and intended binder" : "Define the document and intended binder"}</summary><Subject cid={cid} d={d} reload={load} setError={setError} /></details>
      : !s && <p className="subtle">A reviewer or owner needs to define the document and intended binder.</p>}
    {j && <>
      <details className="journey-section" onToggle={e => setPlanOpen((e.currentTarget as HTMLDetailsElement).open || planOpen)}><summary>Collection plan · suggested request order · {d.plan_items.length} drafted</summary>
        <SuggestedOrder cid={cid} active={planOpen} refreshKey={j.fingerprint + d.plan_items.length} onChanged={load} renderDraft={(c, pid) => <Gap cid={cid} stage={c.stage} gap={c} contacts={contacts} onOpen={loadContacts} prioritizationId={pid} reload={load} setError={setError} />} />
        <h4>Drafted requests</h4>
        {d.plan_items.length === 0 ? <p className="subtle">None yet. Open a stage with unknown or conflicting evidence and plan a request.</p> : <ul className="journey-records">{d.plan_items.map((p: Row) => <li key={p.id} className="journey-record"><div>{STAGE_LABEL[p.stage]} · {p.question}</div><div className="subtle">Contact: {p.contact_name || "none selected"} · request {p.request_status} · would settle: {p.would_settle}</div></li>)}</ul>}</details>
      <Outcomes cid={cid} d={d} reload={load} setError={setError} />
      {d.can_write && <Replay cid={cid} />}
      {d.links.length > 0 && <details className="journey-section"><summary>Reviewer-confirmed links · {d.links.filter((l: Row) => !l.revoked_at).length} active</summary><ul className="journey-records">{d.links.map((l: Row) => <li key={l.id} className="journey-record"><div>{l.kind}: {l.from_system} {l.from_ref} → {l.to_system} {l.to_ref}{l.revoked_at ? " (revoked)" : !l.applies_to_current_definition ? " (no longer applies to the current definition)" : ""}</div><div className="subtle">{l.rationale} Evidence: {l.evidence}{l.snapshot_decision_id ? " · adopted from an existing confirmed link" : ""} · {l.actor_name}, {stamp(l.created_at)}</div>{d.can_write && !l.revoked_at && <RevokeLink cid={cid} id={l.id} reload={load} setError={setError} />}</li>)}</ul></details>}
    </>}
    {d.snapshot_links.length > 0 && <details className="journey-section"><summary>Existing confirmed links · saved snapshots only · {d.snapshot_links.length}</summary><p className="subtle">These join saved snapshot records, which carry no source-system identity. They do not map journey records until a reviewer adopts one while confirming a link above.</p><ul className="journey-records">{d.snapshot_links.map((x: Row) => <li key={x.id} className="journey-record"><div>{x.exact_matches.map((m: Row) => `${m.field} ${m.left}`).join(" · ")}{x.stale ? " (evidence changed; reassess before adopting)" : ""}</div><div className="subtle">{x.reason} · {x.actor}, {stamp(x.at)}</div></li>)}</ul></details>}
    {d.can_import && <details className="journey-section"><summary>Import a synthetic mock-system export</summary><Importer cid={cid} onDone={load} setError={setError} /></details>}
  </section>;
}

function RevokeLink({ cid, id, reload, setError }: { cid: string; id: string; reload: () => void; setError: (s: string) => void }) {
  const [why, setWhy] = useState("");
  const go = async (e: React.FormEvent) => { e.preventDefault(); try { await api(`/cases/${encodeURIComponent(cid)}/journey/links/${id}/revoke`, { reason: why }); reload(); } catch (x) { setError((x as Error).message); } };
  return <details className="journey-inline"><summary>Revoke link</summary><form onSubmit={go}><label>Reason<input value={why} onChange={e => setWhy(e.target.value)} minLength={10} maxLength={1000} required /></label><button className="outline">Revoke</button></form></details>;
}
