"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, plural, stamp } from "./lib";
import { DataTable } from "./workspace-components";
type Row = Record<string, any>;
const uid = () => crypto.randomUUID();
const d10 = (s?: string | null) => (s ? String(s).slice(0, 10) : "");
const isReviewer = (me: Row) => ["owner", "reviewer"].includes(me.role);
const humanize = (s: string) => s.replace(/_/g, " ");
function useMembers() {
  const [m, setM] = useState<Row[]>([]);
  useEffect(() => { api("/members").then(setM).catch(() => setM([])); }, []);
  return m;
}
function useAct(setError: (s: string) => void) {
  const [busy, setBusy] = useState(false);
  const act = async (fn: () => Promise<unknown>) => { setBusy(true); setError(""); try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  return { busy, act };
}
const Msg = ({ error, ok }: { error?: string; ok?: string }) => <>{error && <p role="alert" className="error">{error}</p>}{ok && <p role="status" className="success">{ok}</p>}</>;
const Status = ({ v }: { v: string }) => <span className={"badge status-" + v}>{humanize(v)}</span>;

/* ------------------------------------------------------------------ 1. recurrence and prevention (case page) */
function PlanEditor({ plan, group, members, onSaved, setError }: { plan: Row; group: Row; members: Row[]; onSaved: () => void; setError: (s: string) => void }) {
  const caseIds = group.members.map((m: Row) => m.case_id).filter((v: string, i: number, a: string[]) => a.indexOf(v) === i);
  const toDraft = (x: Row) => ({ id: x.id, text: x.text, owner_id: x.owner_id || "", due: d10(x.due_at), case_id: x.evidence?.[0]?.case_id || "", note: x.evidence?.[0]?.note || "", done: x.status === "done" });
  const [title, setTitle] = useState(plan.title), [summary, setSummary] = useState(plan.summary), [actions, setActions] = useState<Row[]>(plan.actions.map(toDraft)), [note, setNote] = useState(plan.completion_note || "");
  const { busy, act } = useAct(setError);
  const edit = (i: number, patch: Row) => setActions(actions.map((a, j) => (j === i ? { ...a, ...patch } : a)));
  const save = (status: string) => act(async () => {
    await api("/prevention-plans/" + plan.id, { expected_version: plan.version, title, summary, status, completion_note: note, actions: actions.map(a => ({ id: a.id, text: a.text, owner_id: a.owner_id || null, due_at: a.due ? a.due + "T17:00:00Z" : null, done: a.done, evidence: a.case_id ? [{ case_id: a.case_id, note: a.note }] : [] })) });
    onSaved();
  });
  const locked = plan.status === "completed";
  return <form className="improve-plan" onSubmit={e => e.preventDefault()} aria-label={"Prevention plan " + plan.title}>
    <label>Plan title<input value={title} onChange={e => setTitle(e.target.value)} maxLength={120} disabled={locked}/></label>
    <label>Summary<textarea value={summary} onChange={e => setSummary(e.target.value)} rows={2} maxLength={1000} disabled={locked}/></label>
    {actions.map((a, i) => <fieldset key={a.id} className="improve-action" disabled={locked}>
      <legend>Action {i + 1}</legend>
      <label>What will be done<input value={a.text} onChange={e => edit(i, { text: e.target.value })} maxLength={300}/></label>
      <label>Owner<select value={a.owner_id} onChange={e => edit(i, { owner_id: e.target.value })}><option value="">Choose an owner</option>{members.map(m => <option key={m.id} value={m.id}>{m.name} · {m.role}</option>)}</select></label>
      <label>Deadline<input type="date" value={a.due} onChange={e => edit(i, { due: e.target.value })}/></label>
      <label>Supporting case<select value={a.case_id} onChange={e => edit(i, { case_id: e.target.value })}><option value="">Choose a case</option>{caseIds.map((c: string) => <option key={c}>{c}</option>)}</select></label>
      <label>Evidence note<input value={a.note} onChange={e => edit(i, { note: e.target.value })} maxLength={300}/></label>
      <label className="check"><input type="checkbox" checked={a.done} onChange={e => edit(i, { done: e.target.checked })}/> Done</label>
      <button type="button" className="text-button" onClick={() => setActions(actions.filter((_, j) => j !== i))}>Remove action</button>
    </fieldset>)}
    {!locked && actions.length < 20 && <button type="button" className="outline" onClick={() => setActions([...actions, { id: uid(), text: "", owner_id: "", due: "", case_id: "", note: "", done: false }])}>Add action</button>}
    {!locked && <><label>Outcome note (required to complete)<textarea value={note} onChange={e => setNote(e.target.value)} rows={2} maxLength={1000}/></label>
      <div className="improve-buttons"><button type="button" className="outline" disabled={busy} onClick={() => save(plan.status)}>Save {plan.status}</button>
        {plan.status === "draft" && <button type="button" disabled={busy} onClick={() => save("active")}>Activate plan</button>}
        {plan.status === "active" && <button type="button" disabled={busy} onClick={() => save("completed")}>Complete plan</button>}</div></>}
    {locked && <p className="subtle">Completed {stamp(plan.completed_at)}. This plan is read-only; start a new plan for further work.</p>}
  </form>;
}

function GroupCard({ g, me, members, reload, setError }: { g: Row; me: Row; members: Row[]; reload: () => void; setError: (s: string) => void }) {
  const reviewer = isReviewer(me), { busy, act } = useAct(setError);
  const [planTitle, setPlanTitle] = useState(""), [w, setW] = useState({ label: "", role: "baseline", start: "", end: "", count: "", unit: "" });
  const active = g.members.filter((m: Row) => !m.removed_at), removed = g.members.filter((m: Row) => m.removed_at), c = g.comparison;
  return <details className="improve-group"><summary>{g.group.title} · {plural(active.length, "case")} · <Status v={g.group.status}/></summary>
    <p><b>Observed pattern (reviewer-stated):</b> {g.group.pattern}</p>
    <p className="subtle">Scope: {g.criteria.category} · {g.criteria.study_id} · {g.criteria.site_id || "all sites"}. {g.interpretation}</p>
    <ul className="improve-list">{active.map((m: Row) => <li key={m.id}><Link href={"/workspace/cases/" + encodeURIComponent(m.case_id)}>{m.case_id}</Link> {m.title} <small>added {stamp(m.added_at)}</small></li>)}</ul>
    {removed.length > 0 && <details><summary>{removed.length} removed from group</summary><ul>{removed.map((m: Row) => <li key={m.id}>{m.case_id} — {m.removal_reason} <small>({stamp(m.removed_at)})</small></li>)}</ul></details>}
    <h4>Prevention plans</h4>
    {g.plans.length === 0 && <p className="subtle">No prevention plan yet.</p>}
    {g.plans.map((p: Row) => <details key={p.id}><summary>{p.title} · <Status v={p.status}/> · {p.actions.length} actions</summary>
      {reviewer ? <PlanEditor key={p.id + ":" + p.version} plan={p} group={g} members={members} onSaved={reload} setError={setError}/> :
        <ul>{p.actions.map((a: Row) => <li key={a.id}>{a.text} · {a.owner_name || "no owner"} · due {d10(a.due_at) || "—"} · {a.status}</li>)}</ul>}</details>)}
    {reviewer && <form className="inline-form" onSubmit={e => { e.preventDefault(); void act(async () => { await api("/recurrence/groups/" + g.group.id + "/plans", { id: uid(), title: planTitle, summary: "" }); setPlanTitle(""); reload(); }); }}>
      <label>New plan title<input value={planTitle} onChange={e => setPlanTitle(e.target.value)} minLength={3} maxLength={120} required/></label><button disabled={busy}>Create draft plan</button></form>}
    <h4>Subsequent matching cases</h4>
    {g.windows.length === 0 ? <p className="subtle">No windows defined. Define a baseline and a follow-up window of equal length, with an exposure denominator if one is available.</p> :
      <ul>{g.windows.map((x: Row) => <li key={x.id}><b>{x.label}</b> ({humanize(x.role)}) {d10(x.start_at)} → {d10(x.end_at)} (end exclusive, {plural(x.days, "day")}): <b>{x.matching_cases}</b> matching {x.matching_cases === 1 ? "case" : "cases"}{x.exposure_count ? ` · exposure ${x.exposure_count} ${x.exposure_unit}` : " · exposure not provided"}</li>)}</ul>}
    {c && <p className="subtle" role="status">{c.can_compare ? `Descriptive rates per ${c.unit}: ${c.baseline_rate_per_unit} → ${c.follow_up_rate_per_unit}. ${c.note}` : "No comparison made. " + c.reasons.join(" ")}</p>}
    {reviewer && <form className="inline-form" onSubmit={e => { e.preventDefault(); void act(async () => { await api("/recurrence/groups/" + g.group.id + "/windows", { id: uid(), label: w.label, role: w.role, start_at: w.start + "T00:00:00Z", end_at: w.end + "T00:00:00Z", exposure_count: w.count ? Number(w.count) : null, exposure_unit: w.unit || null }); setW({ label: "", role: "baseline", start: "", end: "", count: "", unit: "" }); reload(); }); }}>
      <label>Window label<input value={w.label} onChange={e => setW({ ...w, label: e.target.value })} required maxLength={80}/></label>
      <label>Role<select value={w.role} onChange={e => setW({ ...w, role: e.target.value })}><option value="baseline">Baseline</option><option value="follow_up">Follow-up</option></select></label>
      <label>Start<input type="date" value={w.start} onChange={e => setW({ ...w, start: e.target.value })} required/></label>
      <label>End (exclusive)<input type="date" value={w.end} onChange={e => setW({ ...w, end: e.target.value })} required/></label>
      <label>Exposure count (optional)<input type="number" min="0" step="any" value={w.count} onChange={e => setW({ ...w, count: e.target.value })}/></label>
      <label>Exposure unit<input value={w.unit} onChange={e => setW({ ...w, unit: e.target.value })} maxLength={40} placeholder="e.g. site visits"/></label>
      <button disabled={busy}>Record window</button></form>}
    <details><summary>History ({g.events.length})</summary><ul>{g.events.map((e: Row) => <li key={e.id}>{stamp(e.created_at)} · {e.actor_name} · {humanize(e.kind)}</li>)}</ul></details>
  </details>;
}

export function RecurrencePanel({ cid, me }: { cid: string; me: Row }) {
  const [sug, setSug] = useState<Row | null>(null), [groups, setGroups] = useState<Row[] | null>(null), [error, setError] = useState(""), [pick, setPick] = useState<string[]>([]), [f, setF] = useState({ title: "", basis: "category_study_site", scope: "site", pattern: "" });
  const members = useMembers(), { busy, act } = useAct(setError), reviewer = isReviewer(me);
  const reload = useCallback(async () => { try { const [s, g] = await Promise.all([api("/recurrence/suggestions?case_id=" + encodeURIComponent(cid)), api("/recurrence/groups?case_id=" + encodeURIComponent(cid))]); setSug(s); setGroups(g); setError(""); } catch (e) { setError((e as Error).message); } }, [cid]);
  useEffect(() => { void reload(); }, [reload]);
  const create = (e: React.FormEvent) => { e.preventDefault(); void act(async () => { await api("/recurrence/groups", { id: uid(), title: f.title, case_ids: [cid, ...pick], basis: f.basis, site_scope: f.scope, pattern: f.pattern }); setPick([]); setF({ ...f, title: "", pattern: "" }); await reload(); }); };
  if (!groups && !error) return <section className="panel improve-panel" aria-busy="true"><p role="status">Loading recurrence…</p></section>;
  const cands = sug?.candidates || [];
  return <section className="panel improve-panel" aria-label="Recurrence and prevention">
    <header><h3>Recurrence &amp; prevention</h3><small>{groups?.length ? `${groups.length} confirmed group${groups.length > 1 ? "s" : ""}` : "Not in a confirmed group"} · {cands.length} candidate case{cands.length === 1 ? "" : "s"} by category/study/site or confirmed link</small></header>
    <Msg error={error}/>
    {groups?.map(g => <GroupCard key={g.group.id + ":" + g.group.version} g={g} me={me} members={members} reload={reload} setError={setError}/>)}
    {reviewer ? <details><summary>Confirm a recurrence group</summary>
      <p className="subtle">{sug?.interpretation}</p>
      {cands.length === 0 ? <p>No other cases share this case's category, study and site.</p> : <form onSubmit={create}>
        <fieldset><legend>Choose cases that belong with {cid} (up to 24)</legend>{cands.map((c: Row) => <label key={c.id} className="check"><input type="checkbox" checked={pick.includes(c.id)} disabled={!pick.includes(c.id) && pick.length >= 24} onChange={e => setPick(e.target.checked ? [...pick, c.id] : pick.filter(x => x !== c.id))}/> {c.id} {c.title} <small>({c.via.join(", ")}; {c.status})</small></label>)}</fieldset>
        <label>Group name<input value={f.title} onChange={e => setF({ ...f, title: e.target.value })} required maxLength={120}/></label>
        <label>Basis<select value={f.basis} onChange={e => setF({ ...f, basis: e.target.value })}><option value="category_study_site">Same category, study and site</option><option value="explicit_links">Reviewer-confirmed links</option></select></label>
        <label>Scope<select value={f.scope} onChange={e => setF({ ...f, scope: e.target.value })}><option value="site">This site only</option><option value="study">Any site in this study</option></select></label>
        <label>What pattern did you observe? (at least 20 characters)<textarea value={f.pattern} onChange={e => setF({ ...f, pattern: e.target.value })} rows={3} minLength={20} maxLength={1000} required/></label>
        <button disabled={busy || pick.length < 1}>Confirm group membership</button></form>}</details>
      : <p className="subtle">Reviewers and owners can confirm groups and edit plans.</p>}
  </section>;
}

/* ------------------------------------------------------------------ 2. document readiness tracker (Operational records) */
export function ReadinessTracker({ me }: { me: Row }) {
  const [cat, setCat] = useState<Row | null>(null), [study, setStudy] = useState(""), [site, setSite] = useState(""), [data, setData] = useState<Row | null>(null), [error, setError] = useState(""), [ok, setOk] = useState(""), [sel, setSel] = useState<Row | null>(null), [rq, setRq] = useState<Row | null>(null), [hist, setHist] = useState<Row[]>([]);
  const { busy, act } = useAct(setError), reviewer = isReviewer(me);
  useEffect(() => { api("/catalog").then(c => { setCat(c); setStudy(c.studies[0]?.id || ""); }).catch(e => setError(e.message)); }, []);
  const load = useCallback(async () => { if (!study) return; try { setData(await api("/readiness?study_id=" + encodeURIComponent(study) + (site ? "&site_id=" + encodeURIComponent(site) : ""))); if (reviewer) setHist(await api("/readiness/history?study_id=" + encodeURIComponent(study))); setError(""); } catch (e) { setError((e as Error).message); } }, [study, site, reviewer]);
  useEffect(() => { setData(null); void load(); }, [load]);
  const sites = (cat?.sites || []).filter((s: Row) => s.study_id === study);
  const done = async (msg: string) => { setOk(msg); setSel(null); setRq(null); await load(); };
  const saveRecord = (e: React.FormEvent) => { e.preventDefault(); void act(async () => { await api("/readiness/records", { requirement_id: sel!.requirement.id, site_id: sel!.site_id, applicable: sel!.applicable, applicability_reason: sel!.reason || "", document_identity: sel!.identity || "", document_version: sel!.docv || "", expiry_date: sel!.expiry || null, as_of: sel!.asof || null, evidence: sel!.ref ? [{ kind: "note", ref: sel!.ref, note: "" }] : [], expected_version: sel!.record?.version ?? 0 }); await done("Record saved and marked awaiting review."); }); };
  const saveReq = (e: React.FormEvent) => { e.preventDefault(); void act(async () => { await api("/readiness/requirements", { id: rq!.id, study_id: study, site_id: rq!.site_id || null, name: rq!.name, guidance: rq!.guidance || "", requires_expiry: !!rq!.requires_expiry, archived: !!rq!.archived, expected_version: rq!.version ?? 0 }); await done("Requirement saved. Records made against an earlier version now need re-review."); }); };
  const edit = (r: Row) => { const rec = r.record; setOk(""); setSel({ ...r, applicable: rec ? rec.applicable : true, reason: rec?.applicability_reason, identity: rec?.document_identity, docv: rec?.document_version, expiry: d10(rec?.expiry_date), asof: d10(rec?.as_of), ref: rec?.evidence?.[0]?.ref }); };
  const counts = data?.counts || {};
  return <section className="panel improve-panel" aria-label="Document readiness tracker">
    <header><h3>Document readiness</h3><small>Required documents by study and site · dated records, not certification</small></header>
    <Msg error={error} ok={ok}/>
    <div className="inline-form"><label>Study<select value={study} onChange={e => { setStudy(e.target.value); setSite(""); }}>{cat?.studies.map((s: Row) => <option key={s.id} value={s.id}>{s.id} · {s.name}</option>)}</select></label>
      <label>Site<select value={site} onChange={e => setSite(e.target.value)}><option value="">All sites</option>{sites.map((s: Row) => <option key={s.id} value={s.id}>{s.id}</option>)}</select></label>
      {reviewer && <button className="outline" onClick={() => { setSel(null); setRq({ id: uid(), name: "", guidance: "", site_id: "", requires_expiry: false, version: 0 }); }}>Define required document</button>}</div>
    {!data ? <p role="status">Loading readiness…</p> : <>
      <p className="improve-counts">{["missing", "expired", "awaiting_review", "reviewed", "not_applicable"].map(k => <span key={k} className={"badge status-" + k}>{humanize(k)} {counts[k] || 0}</span>)}</p>
      <details className="subtle"><summary>How statuses are determined</summary><p>{data.interpretation}</p></details>
      <DataTable<Row> label="Document readiness" rows={data.rows} rowKey={r => r.requirement.id + r.site_id} empty={<div className="empty"><h3>No required documents defined</h3><p>{reviewer ? "Define the documents this study or site must have on file." : "A reviewer can define required documents."}</p></div>} columns={[
        { label: "Required document", render: r => <><strong>{r.requirement.name}</strong>{r.requirement.requires_expiry && <small> · expiry required</small>}<small>{r.requirement.guidance}</small></> },
        { label: "Site", render: r => r.site_id },
        { label: "Status", render: r => <><Status v={r.status}/><small>{r.reason}</small></> },
        { label: "Recorded document", render: r => r.record?.document_identity ? <>{r.record.document_identity} v{r.record.document_version || "?"}<small>expiry {d10(r.record.expiry_date) || "not recorded"} · observed {d10(r.record.as_of)}</small></> : "None recorded" },
        { label: "Action", render: r => reviewer ? <><button className="outline" onClick={() => edit(r)}>Record</button> <button className="text-button" onClick={() => { setSel(null); setRq({ ...r.requirement }); }}>Edit requirement</button></> : "—" },
      ]}/></>}
    {rq && reviewer && <form className="improve-plan" onSubmit={saveReq} aria-label="Required document"><h4>{rq.version ? "Edit" : "Define"} required document</h4>
      <label>Name<input value={rq.name} onChange={e => setRq({ ...rq, name: e.target.value })} required maxLength={120}/></label>
      <label>Guidance<input value={rq.guidance || ""} onChange={e => setRq({ ...rq, guidance: e.target.value })} maxLength={500}/></label>
      <label>Applies to<select value={rq.site_id || ""} onChange={e => setRq({ ...rq, site_id: e.target.value })}><option value="">Every site in {study}</option>{sites.map((s: Row) => <option key={s.id} value={s.id}>{s.id} only</option>)}</select></label>
      <label className="check"><input type="checkbox" checked={!!rq.requires_expiry} onChange={e => setRq({ ...rq, requires_expiry: e.target.checked })}/> Document has an expiry date</label>
      {!!rq.version && <label className="check"><input type="checkbox" checked={!!rq.archived} onChange={e => setRq({ ...rq, archived: e.target.checked })}/> Archive requirement</label>}
      <p className="subtle">Saving a change marks existing records for this requirement as needing re-review.</p>
      <div className="improve-buttons"><button disabled={busy}>Save requirement</button><button type="button" className="outline" onClick={() => setRq(null)}>Cancel</button></div></form>}
    {sel && reviewer && <form className="improve-plan" onSubmit={saveRecord} aria-label="Document record"><h4>{sel.requirement.name} · {sel.site_id}</h4>
      <label className="check"><input type="checkbox" checked={sel.applicable} onChange={e => setSel({ ...sel, applicable: e.target.checked })}/> Requirement applies at this site</label>
      {!sel.applicable && <label>Why not applicable<input value={sel.reason || ""} onChange={e => setSel({ ...sel, reason: e.target.value })} minLength={5} maxLength={300} required/></label>}
      {sel.applicable && <><label>Document identity<input value={sel.identity || ""} onChange={e => setSel({ ...sel, identity: e.target.value })} maxLength={200}/></label>
        <label>Document version<input value={sel.docv || ""} onChange={e => setSel({ ...sel, docv: e.target.value })} maxLength={60}/></label>
        <label>Expiry date (only if printed on the document)<input type="date" value={sel.expiry || ""} onChange={e => setSel({ ...sel, expiry: e.target.value })}/></label>
        <label>Date you observed it<input type="date" value={sel.asof || ""} max={new Date().toISOString().slice(0, 10)} onChange={e => setSel({ ...sel, asof: e.target.value })}/></label>
        <label>Where it is filed (evidence)<input value={sel.ref || ""} onChange={e => setSel({ ...sel, ref: e.target.value })} minLength={3} maxLength={200} placeholder="e.g. TMF section reference"/></label></>}
      <div className="improve-buttons"><button disabled={busy}>Save record</button>
        {sel.record && sel.record.review_status !== "reviewed" && sel.status === "awaiting_review" && !sel.stale && <button type="button" disabled={busy} onClick={() => void act(async () => { await api("/readiness/records/" + sel.record.id + "/review", { expected_version: sel.record.version, note: "" }); await done("Record marked reviewed as a dated observation."); })}>Mark reviewed</button>}
        <button type="button" className="outline" onClick={() => setSel(null)}>Cancel</button></div></form>}
    {reviewer && hist.length > 0 && <details><summary>Change history ({hist.length})</summary><ul>{hist.slice(0, 30).map(h => <li key={h.id}>{stamp(h.created_at)} · {h.actor_name} · {humanize(h.kind)}</li>)}</ul></details>}
  </section>;
}

/* ------------------------------------------------------------------ 3. procedure-change impact review (Knowledge) */
export function ProcedureImpact({ me }: { me: Row }) {
  const [list, setList] = useState<Row[] | null>(null), [art, setArt] = useState(""), [oldV, setOldV] = useState(0), [newV, setNewV] = useState(0), [d, setD] = useState<Row | null>(null), [error, setError] = useState(""), [ok, setOk] = useState(""), [status, setStatus] = useState("needed"), [why, setWhy] = useState(""), [note, setNote] = useState("");
  const { busy, act } = useAct(setError), reviewer = isReviewer(me);
  useEffect(() => { api("/knowledge").then((r: Row[]) => { setList(r); if (r[0]) setArt(r[0].id); else setList([]); }).catch(e => setError(e.message)); }, []);
  const load = useCallback(async (o?: number, n?: number) => { if (!art) return; try { const r = await api(`/knowledge/${encodeURIComponent(art)}/impact-review` + (o && n ? `?old=${o}&new=${n}` : "")); setD(r); setOldV(r.old_version); setNewV(r.new_version); setStatus(r.review?.status || "needed"); setWhy(""); setError(""); setNote(""); } catch (e) { setD(null); const m = (e as Error).message; if (/two retained versions/i.test(m)) { setError(""); setNote("Only one version of this procedure is saved, so there is nothing to compare yet."); } else setError(m); } }, [art]);
  useEffect(() => { setD(null); setOk(""); setNote(""); void load(); }, [load]);
  const save = (e: React.FormEvent) => { e.preventDefault(); void act(async () => { const r = await api(`/knowledge/${encodeURIComponent(art)}/impact-review`, { old_version: d!.old_version, new_version: d!.new_version, status, rationale: why, comparison_hash: d!.comparison_hash, expected_version: d!.review?.version ?? 0 }); setD(r); setWhy(""); setOk("Review recorded. No check, case or earlier decision was changed."); }); };
  if (list && list.length === 0) return null;
  return <details className="panel improve-panel overview-fold" aria-label="Procedure change impact review">
    <summary><span>Procedure change impact</span></summary>
    <p className="subtle">Compares retained passages (not AI) · you decide whether reassessment is needed</p>
    <Msg error={error} ok={ok}/>
    <div className="inline-form"><label>Procedure<select value={art} onChange={e => setArt(e.target.value)}>{list?.map(a => <option key={a.id} value={a.id}>{a.title} (current v{a.version}{a.archived ? ", archived" : ""})</option>)}</select></label>
      {d && d.versions.length > 1 && <><label>Older version<select value={oldV} onChange={e => void load(Number(e.target.value), newV)}>{d.versions.map((v: Row) => <option key={v.version} value={v.version}>v{v.version}</option>)}</select></label>
        <label>Newer version<select value={newV} onChange={e => void load(oldV, Number(e.target.value))}>{d.versions.map((v: Row) => <option key={v.version} value={v.version}>v{v.version}</option>)}</select></label></>}</div>
    {!d && !error && !note && <p role="status">Loading comparison…</p>}
    {!d && note && <p className="subtle" role="status">{note}</p>}
    {d && <>
      {d.archived && <p className="subtle">This procedure is archived. Existing references stay as cited.</p>}
      {d.superseded_by && <p className="subtle" role="status">A newer version (v{d.superseded_by}) exists; this comparison remains valid for v{d.old_version} → v{d.new_version}.</p>}
      <p className="subtle">{d.method} {d.preserved}</p>
      <h4>Changed passages ({d.total_changes})</h4>
      {d.changes.length === 0 ? <p>No passage differences between these versions.</p> : d.changes.map((c: Row, i: number) => <article key={i} className="work-item impact-change"><strong>{humanize(c.change)} · {c.section_new || c.section_old}</strong>
        {c.old_text && <p><small>v{d.old_version}</small><br/><del>{c.old_text}</del></p>}{c.new_text && <p><small>v{d.new_version}</small><br/><ins>{c.new_text}</ins></p>}</article>)}
      <h4>Affected references</h4>
      <p>{d.affected_checks.length} active or draft check{d.affected_checks.length === 1 ? "" : "s"} · {d.affected_cases.length} case run{d.affected_cases.length === 1 ? "" : "s"} citing v{d.old_version}</p>
      <ul className="improve-list">{d.affected_cases.map((c: Row) => <li key={c.run_id}><Link href={"/workspace/cases/" + encodeURIComponent(c.case_id)}>{c.case_id}</Link> {c.case_title} <small>({c.case_status}) cites {c.cited_passages.map((p: Row) => p.section || p.source_id).join(", ")} · earlier decision: {c.past_decision || "none"}{c.reassessment ? ` · reassessment ${c.reassessment}` : ""}</small></li>)}</ul>
      {d.review && <p role="status"><b>Reviewed:</b> reassessment {d.review.status === "needed" ? "needed" : "not needed"} — {d.review.rationale} <small>({d.review.reviewer_name || "reviewer"}, {stamp(d.review.reviewed_at)})</small></p>}
      {reviewer ? <form onSubmit={save} className="improve-plan"><fieldset><legend>Is reassessment needed?</legend><label className="check"><input type="radio" checked={status === "needed"} onChange={() => setStatus("needed")}/> Reassessment needed</label><label className="check"><input type="radio" checked={status === "not_needed"} onChange={() => setStatus("not_needed")}/> Not needed</label></fieldset>
        <label>Why (at least 10 characters)<textarea value={why} onChange={e => setWhy(e.target.value)} rows={2} minLength={10} maxLength={1000} required/></label>
        <button disabled={busy}>{d.review ? "Update review" : "Record review"}</button></form> : <p className="subtle">Reviewers and owners record the reassessment decision.</p>}</>}
  </details>;
}

/* ------------------------------------------------------------------ 4. bulk owner / deadline changes (Cases table) */
export function BulkBar({ me, selected, onClear, onDone }: { me: Row; selected: string[]; onClear: () => void; onDone: () => void }) {
  const members = useMembers(), [setOwner, setSetOwner] = useState(false), [owner, setOwnerId] = useState(""), [setDue, setSetDue] = useState(false), [due, setDueDate] = useState(""), [prev, setPrev] = useState<Row | null>(null), [result, setResult] = useState<Row | null>(null), [error, setError] = useState(""), [reqId, setReqId] = useState(uid());
  const { busy, act } = useAct(setError);
  const body = () => ({ request_id: reqId, case_ids: selected, set_owner: setOwner, owner_id: setOwner && owner ? owner : null, set_due: setDue, due_at: setDue && due ? due + "T17:00:00Z" : null });
  const nameOf = (id?: string | null) => (id ? members.find(m => m.id === id)?.name || "member" : "Unassigned");
  const preview = () => act(async () => { setResult(null); setPrev(await api("/cases/bulk/preview", body())); });
  const apply = () => act(async () => { const expected: Row = {}; prev!.items.forEach((i: Row) => { if (i.updated_at) expected[i.case_id] = i.updated_at; }); setResult(await api("/cases/bulk/apply", { ...body(), expected })); setPrev(null); setReqId(uid()); onDone(); });
  if (!isReviewer(me) || (selected.length === 0 && !result)) return null;
  return <section className="panel bulk-bar" aria-label="Bulk case actions">
    {selected.length > 0 && <><strong>{selected.length} selected</strong> <small>(up to 25) · owner and deadline only; approval, resolution and reopening are never bulk actions</small></>}
    <Msg error={error}/>
    {selected.length > 0 && <div className="inline-form">
      <label className="check"><input type="checkbox" checked={setOwner} onChange={e => { setSetOwner(e.target.checked); setPrev(null); }}/> Change owner</label>
      {setOwner && <label>Owner<select value={owner} onChange={e => { setOwnerId(e.target.value); setPrev(null); }}><option value="">Unassigned</option>{members.map(m => <option key={m.id} value={m.id}>{m.name} · {m.role}</option>)}</select></label>}
      <label className="check"><input type="checkbox" checked={setDue} onChange={e => { setSetDue(e.target.checked); setPrev(null); }}/> Change deadline</label>
      {setDue && <label>Deadline (blank clears it)<input type="date" value={due} onChange={e => { setDueDate(e.target.value); setPrev(null); }}/></label>}
      <button disabled={busy || (!setOwner && !setDue)} onClick={() => void preview()}>Preview changes</button><button className="outline" onClick={onClear}>Clear selection</button></div>}
    {prev && selected.length > 0 && <><table className="data-table" aria-label="Bulk preview"><thead><tr><th scope="col">Case</th><th scope="col">Owner</th><th scope="col">Deadline</th><th scope="col">Result</th></tr></thead><tbody>{prev.items.map((i: Row) => <tr key={i.case_id}><td>{i.case_id}</td><td>{i.ok ? `${nameOf(i.before.owner_id)} → ${nameOf(i.after.owner_id)}` : "—"}</td><td>{i.ok ? `${d10(i.before.due_at) || "none"} → ${d10(i.after.due_at) || "none"}` : "—"}</td><td>{i.ok ? "Will change" : <span className="error-text">{i.reason}</span>}</td></tr>)}</tbody></table>
      <button disabled={busy || prev.will_change === 0} onClick={() => void apply()}>Apply to {prev.will_change} case{prev.will_change === 1 ? "" : "s"}</button> <small>Safe to retry: repeating this submission never applies a change twice.</small></>}
    {result && <div role="status"><button className="text-button" onClick={() => setResult(null)}>Dismiss result</button> <b>Result:</b> {Object.entries(result.counts).map(([k, v]) => `${v} ${k}`).join(" · ")}<ul>{result.results.map((r: Row) => <li key={r.case_id}>{r.case_id}: {r.status}{r.reason ? ` — ${r.reason}` : ""}</li>)}</ul></div>}
  </section>;
}

/* ------------------------------------------------------------------ 5. feedback-to-improvement queue and submitter status */
export function MyFeedback() {
  const [rows, setRows] = useState<Row[] | null>(null), [error, setError] = useState("");
  useEffect(() => { api("/feedback/mine").then(setRows).catch(e => setError(e.message)); }, []);
  if (!rows?.length && !error) return null;
  return <section className="panel improve-panel" aria-label="Your feedback status"><header><h3>Your feedback</h3><small>Only you can see this</small></header><Msg error={error}/>
    {rows?.map(r => <article key={r.id} className="work-item"><p className="preserve">{r.message}</p><small>{stamp(r.created_at)} · <Status v={r.status}/>{r.status_changed_at ? ` since ${stamp(r.status_changed_at)}` : ""}</small>
      {r.public_note && <p>{r.public_note}</p>}{r.improvement_title && <p><small>Tracked improvement: {r.improvement_title} ({humanize(r.improvement_status)})</small></p>}</article>)}</section>;
}

export function FeedbackQueue({ me }: { me: Row }) {
  const [q, setQ] = useState<Row | null>(null), [filter, setFilter] = useState(""), [error, setError] = useState(""), [ok, setOk] = useState(""), [open, setOpen] = useState<Row | null>(null), [imp, setImp] = useState<Row | null>(null);
  const { busy, act } = useAct(setError);
  const load = useCallback(async () => { try { setQ(await api("/feedback/queue")); } catch (e) { setError((e as Error).message); } }, []);
  useEffect(() => { void load(); }, [load]);
  if (me.role !== "owner") return null;
  const items = (q?.items || []).filter((i: Row) => !filter || i.status === filter);
  const saveTriage = (e: React.FormEvent) => { e.preventDefault(); void act(async () => { await api(`/feedback/${open!.id}/triage`, { expected_version: open!.version, status: open!.status, owner_id: open!.owner_id || null, internal_note: open!.internal_note, public_note: open!.public_note, confidential: !!open!.confidential, improvement_id: open!.improvement_id || null, related_feedback: open!.related_feedback || [] }); setOpen(null); setOk("Triage saved. Nothing was published or sent."); await load(); }); };
  const saveImp = (e: React.FormEvent) => { e.preventDefault(); void act(async () => { await api("/improvements", { id: imp!.id, title: imp!.title, description: imp!.description || "", status: imp!.status, owner_id: imp!.owner_id || null, explanation: imp!.explanation || "", expected_version: imp!.version ?? 0 }); setImp(null); setOk("Improvement saved."); await load(); }); };
  return <section className="panel improve-panel" aria-label="Feedback queue">
    <header><h3>Feedback queue</h3><small>Maintainers only · submitters see their own status and public note</small></header>
    <Msg error={error} ok={ok}/>
    {!q ? <p role="status">Loading feedback…</p> : <>
      <div className="inline-form"><label>Show<select value={filter} onChange={e => setFilter(e.target.value)}><option value="">All states</option>{q.states.map((s: string) => <option key={s} value={s}>{humanize(s)}</option>)}</select></label>
        <button className="outline" onClick={() => setImp({ id: uid(), title: "", status: "planned", version: 0 })}>New tracked improvement</button></div>
      {items.length === 0 && <div className="empty"><h3>No feedback in this view</h3></div>}
      {items.map((i: Row) => <article key={i.id} className="work-item"><strong>{i.rating} / 5 · <Status v={i.status}/></strong>{i.confidential && <small> · confidential</small>}<p className="preserve">{i.message}</p>
        <small>{i.submitter || "Former member"} · {stamp(i.created_at)}{i.owner_name ? ` · owner ${i.owner_name}` : ""}{i.status_changed_at ? ` · status since ${stamp(i.status_changed_at)}` : ""}</small>
        <div><button className="outline" onClick={() => setOpen({ ...i })}>Triage</button></div></article>)}
      <h4>Tracked improvements ({q.improvements.length})</h4>
      <ul className="improve-list">{q.improvements.map((m: Row) => <li key={m.id}><b>{m.title}</b> <Status v={m.status}/> {m.owner_name && <small>· {m.owner_name}</small>} <button className="text-button" onClick={() => setImp({ ...m })}>Edit</button></li>)}</ul></>}
    {open && <form className="improve-plan" onSubmit={saveTriage} aria-label="Triage feedback"><h4>Triage</h4>
      <label>State<select value={open.status} onChange={e => setOpen({ ...open, status: e.target.value })}>{q!.states.map((s: string) => <option key={s} value={s}>{humanize(s)}</option>)}</select></label>
      <label>Owner<select value={open.owner_id || ""} onChange={e => setOpen({ ...open, owner_id: e.target.value })}><option value="">No owner</option>{q!.owners.map((o: Row) => <option key={o.id} value={o.id}>{o.name}</option>)}</select></label>
      <label>Tracked improvement<select value={open.improvement_id || ""} onChange={e => setOpen({ ...open, improvement_id: e.target.value })}><option value="">None</option>{q!.improvements.map((m: Row) => <option key={m.id} value={m.id}>{m.title}</option>)}</select></label>
      <label>Related feedback<select multiple value={open.related_feedback || []} onChange={e => setOpen({ ...open, related_feedback: Array.from(e.target.selectedOptions).map(o => o.value) })}>{q!.items.filter((x: Row) => x.id !== open.id).map((x: Row) => <option key={x.id} value={x.id}>{x.message.slice(0, 60)}</option>)}</select></label>
      <label>Internal note (never shown to the submitter)<textarea value={open.internal_note || ""} onChange={e => setOpen({ ...open, internal_note: e.target.value })} rows={2} maxLength={1000}/></label>
      <label>Safe status note for the submitter<textarea value={open.public_note || ""} onChange={e => setOpen({ ...open, public_note: e.target.value })} rows={2} maxLength={500}/></label>
      <label className="check"><input type="checkbox" checked={!!open.confidential} onChange={e => setOpen({ ...open, confidential: e.target.checked })}/> Confidential or security-related: show the submitter only “received” or “reviewing”</label>
      <div className="improve-buttons"><button disabled={busy}>Save triage</button><button type="button" className="outline" onClick={() => setOpen(null)}>Cancel</button></div></form>}
    {imp && <form className="improve-plan" onSubmit={saveImp} aria-label="Tracked improvement"><h4>{imp.version ? "Edit" : "New"} improvement</h4>
      <label>Title<input value={imp.title} onChange={e => setImp({ ...imp, title: e.target.value })} required maxLength={120}/></label>
      <label>Description<textarea value={imp.description || ""} onChange={e => setImp({ ...imp, description: e.target.value })} rows={2} maxLength={1000}/></label>
      <label>State<select value={imp.status} onChange={e => setImp({ ...imp, status: e.target.value })}>{["planned", "in_progress", "completed", "declined"].map(s => <option key={s} value={s}>{humanize(s)}</option>)}</select></label>
      <label>Owner<select value={imp.owner_id || ""} onChange={e => setImp({ ...imp, owner_id: e.target.value })}><option value="">No owner</option>{q?.owners.map((o: Row) => <option key={o.id} value={o.id}>{o.name}</option>)}</select></label>
      <label>Explanation (required to complete or decline)<textarea value={imp.explanation || ""} onChange={e => setImp({ ...imp, explanation: e.target.value })} rows={2} maxLength={1000}/></label>
      <div className="improve-buttons"><button disabled={busy}>Save improvement</button><button type="button" className="outline" onClick={() => setImp(null)}>Cancel</button></div></form>}
  </section>;
}
