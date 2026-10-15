"use client";
import { useCallback, useEffect, useState } from "react";
import { api, plural, stamp } from "./lib";
type Row = Record<string, any>;
const uid = () => crypto.randomUUID();
const STATE: Record<string, string> = { ready: "Ready", blocked: "Blocked", waiting: "Waiting", received: "Response received" };
const EFFORT: Record<string, string> = { low: "Low", medium: "Medium", high: "High", unknown: "Not estimated" };

function Inputs({ cid, c, others, checks, reload, setError }: { cid: string; c: Row; others: Row[]; checks: Row[]; reload: () => void; setError: (s: string) => void }) {
  const [effort, setEffort] = useState(c.effort), [note, setNote] = useState(c.effort_note || ""), [busy, setBusy] = useState(false);
  const [pre, setPre] = useState<string[]>(c.prerequisites.map((p: Row) => p.kind + "|" + p.key));
  const [map, setMap] = useState<string[]>(c.mapped), [why, setWhy] = useState(""), [preWhy, setPreWhy] = useState("");
  const kept = c.prerequisites.map((p: Row) => p.kind + "|" + p.key), removing = kept.some((v: string) => !pre.includes(v));
  const P = `/cases/${encodeURIComponent(cid)}/journey/priority`;
  const run = async (fn: () => Promise<unknown>) => { setBusy(true); setError(""); try { await fn(); reload(); } catch (x) { setError((x as Error).message); } finally { setBusy(false); } };
  const saveInputs = (e: React.FormEvent) => { e.preventDefault(); void run(() => api(P + "/inputs", { id: uid(), gap_key: c.key, expected_rev: c.input_rev, effort, effort_note: note, prerequisites: pre.map(v => ({ kind: v.split("|")[0], key: v.slice(v.indexOf("|") + 1) })), change_reason: preWhy })).then(() => setPreWhy("")); };
  const saveMap = (e: React.FormEvent) => { e.preventDefault(); void run(async () => { for (const k of map.filter(x => !c.mapped.includes(x))) await api(P + "/mappings", { id: uid(), gap_key: c.key, check_key: k, action: "add", reason: why }); for (const k of c.mapped.filter((x: string) => !map.includes(x))) await api(P + "/mappings", { id: uid(), gap_key: c.key, check_key: k, action: "remove", reason: why }); setWhy(""); }); };
  const toggle = (list: string[], set: (v: string[]) => void, v: string) => set(list.includes(v) ? list.filter(x => x !== v) : [...list, v]);
  const changed = map.length !== c.mapped.length || map.some(x => !c.mapped.includes(x));
  return <details className="prio-edit"><summary>Mappings, effort and prerequisites · {c.description}</summary>
    <form onSubmit={saveInputs}>
      <div className="journey-grid"><label>Effort (your estimate; unknown stays unknown)<select value={effort} onChange={e => setEffort(e.target.value)}>{Object.keys(EFFORT).map(k => <option key={k} value={k}>{EFFORT[k]}</option>)}</select></label>
        <label>Short explanation<input value={note} onChange={e => setNote(e.target.value)} maxLength={200} /></label></div>
      <fieldset><legend>Prerequisites (this request waits until they are met by reviewed evidence)</legend>
        {others.map(o => <label key={o.key} className="check"><input type="checkbox" checked={pre.includes("gap|" + o.key)} onChange={() => toggle(pre, setPre, "gap|" + o.key)} /> Request: {o.description}</label>)}
        {checks.map(k => <label key={k.key} className="check"><input type="checkbox" checked={pre.includes("check|" + k.key)} onChange={() => toggle(pre, setPre, "check|" + k.key)} /> Check: {k.label}{k.resolved ? " (resolved)" : ""}</label>)}
        {c.prerequisites.filter((p: Row) => p.state === "unmatched").map((p: Row) => <label key={p.kind + p.key} className="check"><input type="checkbox" checked={pre.includes(p.kind + "|" + p.key)} onChange={() => toggle(pre, setPre, p.kind + "|" + p.key)} /> No longer matches (still blocking): {p.kind} {p.key}</label>)}</fieldset>
      {removing && <label>Reason for removing or replacing a prerequisite (reviewer or owner)<input value={preWhy} onChange={e => setPreWhy(e.target.value)} minLength={10} maxLength={1000} required /></label>}
      <button disabled={busy}>Save effort and prerequisites</button></form>
    <form onSubmit={saveMap}>
      <fieldset><legend>Checks this request could help assess (rule-based; you can correct it with a reason)</legend>
        {checks.map(k => <label key={k.key} className="check"><input type="checkbox" checked={map.includes(k.key)} onChange={() => toggle(map, setMap, k.key)} /> {k.label}{k.resolved ? " (resolved: not counted)" : !k.applicable ? " (not applicable: not counted)" : ""}</label>)}</fieldset>
      <label>Reason for the correction<input value={why} onChange={e => setWhy(e.target.value)} minLength={10} maxLength={1000} required={changed} /></label>
      <button disabled={busy || !changed}>Save mapping correction</button></form>
  </details>;
}

export function SuggestedOrder({ cid, active, refreshKey, renderDraft, onChanged }: { cid: string; active: boolean; refreshKey: string; renderDraft: (c: Row, prioritizationId: string | null) => React.ReactNode; onChanged: () => void }) {
  const [d, setD] = useState<Row | null>(null), [error, setError] = useState(""), [order, setOrder] = useState<string[]>([]), [why, setWhy] = useState(""), [busy, setBusy] = useState(false);
  const P = `/cases/${encodeURIComponent(cid)}/journey/priority`;
  const load = useCallback(async () => { try { const r = await api(P); setD(r); setError(""); } catch (e) { setError((e as Error).message); } }, [P]);
  useEffect(() => { if (active) void load(); }, [active, load, refreshKey]);
  const hash = d?.hash;
  useEffect(() => { if (d?.candidates) setOrder(d.candidates.map((c: Row) => c.key)); }, [hash]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!active && !d) return null;
  if (!d) return error ? <p role="alert" className="error">{error}</p> : <p role="status">Loading suggested order…</p>;
  if (!d.available) return <p className="subtle">Define the document and intended binder to see a suggested request order.</p>;
  const act = async (fn: () => Promise<unknown>) => { setBusy(true); setError(""); try { await fn(); await load(); onChanged(); } catch (x) { setError((x as Error).message); } finally { setBusy(false); } };
  const saved = d.saved, cur = saved && !saved.stale, byKey: Record<string, Row> = Object.fromEntries([...d.candidates, ...d.waiting].map((c: Row) => [c.key, c]));
  const reviewerOrder: string[] | null = cur && saved.override && saved.override.order.every((k: string) => byKey[k]) ? saved.override.order : null;
  const shown: Row[] = (reviewerOrder || d.candidates.map((c: Row) => c.key)).map((k: string) => byKey[k]);
  const move = (i: number, by: number) => { const o = [...order]; [o[i], o[i + by]] = [o[i + by], o[i]]; setOrder(o); };
  const names = (c: Row) => c.unresolved.map((k: string) => d.checks.find((x: Row) => x.key === k)?.label).filter(Boolean);
  const differs = order.join() !== d.candidates.map((c: Row) => c.key).join();
  return <div className="prio">
    <h4>Suggested request order <small>rule {d.rule_version} · a fixed ordering, not an optimal or predicted ranking</small></h4>
    {error && <p role="alert" className="error">{error}</p>}
    <p className="subtle">{d.rule}</p>
    {saved?.stale && <p className="journey-warn" role="status">The saved order is stale: evidence, outcomes or dependencies changed since version {saved.rev}. {d.can_write ? <button type="button" className="outline" disabled={busy} onClick={() => act(() => api(P + "/save", { id: uid(), expected_rev: saved.rev }))}>Refresh saved order</button> : null}</p>}
    {cur && <p className="subtle" role="status">Saved as version {saved.rev} by {saved.actor_name}, {stamp(saved.created_at)}.{saved.override ? ` Reviewer order in effect: “${saved.override.reason}” (${saved.override.actor}). The calculated order is kept alongside.` : " No reviewer override."}</p>}
    {!saved && d.can_write && <p className="subtle">Not saved yet. <button type="button" className="outline" disabled={busy} onClick={() => act(() => api(P + "/save", { id: uid(), expected_rev: 0 }))}>Save this suggested order</button></p>}
    {shown.length === 0 ? <p className="subtle">No open request candidates: every journey gap has a sent request or none is unresolved.</p> :
      <ol className="prio-list">{shown.map((c, i) => <li key={c.key} className={"prio-item s-" + c.state}>
        <div className="prio-head"><span className="prio-rank">{reviewerOrder ? `${i + 1}` : c.rank}</span><b>{c.description}</b><span className="prio-state">{STATE[c.state]}{c.existing ? " · draft exists" : ""}</span></div>
        <div className="subtle">{reviewerOrder && <b>Reviewer order #{i + 1}; calculated #{c.rank}. </b>}{c.explanation}{c.effort_note ? ` Effort note: ${c.effort_note}.` : ""}</div>
        {c.prerequisites.filter((p: Row) => p.state !== "met").map((p: Row) => <div key={p.kind + p.key} className="journey-warn">Prerequisite {p.state === "unmet" ? "not met" : "no longer matches a current gap or check; still blocking until a reviewer removes or replaces it"}: {p.kind === "gap" ? byKey[p.key]?.description || p.key : d.checks.find((x: Row) => x.key === p.key)?.label || p.key}</div>)}
        {c.existing ? <div className="subtle">Existing {c.existing.request_status === "draft" ? "draft request (unsent)" : c.existing.request_status + " request"}: “{c.existing.question.slice(0, 90)}” <a href="#case-workflow">Open existing draft</a> (edit it under Missing-information requests)</div> : d.can_write && renderDraft(c, cur ? saved.id : null)}
      </li>)}</ol>}
    {d.waiting.length > 0 && <><h5>Waiting</h5><ul className="prio-list">{d.waiting.map((c: Row) => <li key={c.key} className="prio-item s-waiting"><div className="prio-head"><b>{c.description}</b><span className="prio-state">{STATE[c.state]}</span></div><div className="subtle">{c.explanation} <a href="#case-workflow">Open request</a></div></li>)}</ul></>}
    {d.can_write && d.candidates.length > 1 && <details className="prio-edit"><summary>Reviewer order (override the calculated order with a reason)</summary>
      {!cur ? <p className="subtle">Save the current suggested order first; a stale or unsaved order cannot be overridden.</p> :
        <form onSubmit={e => { e.preventDefault(); void act(() => api(P + "/override", { id: uid(), expected_rev: saved.rev, order, reason: why }).then(() => setWhy(""))); }}>
          <ol className="prio-list">{order.map((k, i) => <li key={k} className="prio-move"><span>{byKey[k].description}</span>
            <button type="button" className="text-button" disabled={i === 0} aria-label={`Move up: ${byKey[k].description}`} onClick={() => move(i, -1)}>Move up</button>
            <button type="button" className="text-button" disabled={i === order.length - 1} aria-label={`Move down: ${byKey[k].description}`} onClick={() => move(i, 1)}>Move down</button></li>)}</ol>
          <label>Reason for your order<input value={why} onChange={e => setWhy(e.target.value)} minLength={10} maxLength={1000} required /></label>
          <button disabled={busy || !differs}>Save reviewer order</button></form>}</details>}
    {d.can_write && <details className="prio-edit"><summary>Mappings, effort and prerequisites for each request</summary>
      {[...d.candidates, ...d.waiting].map((c: Row) => <Inputs key={c.key} cid={cid} c={c} others={[...d.candidates, ...d.waiting].filter((o: Row) => o.key !== c.key)} checks={d.checks} reload={() => { void load(); onChanged(); }} setError={setError} />)}
      {d.mappings.length > 0 && <details><summary>Mapping corrections ({d.mappings.length})</summary><ul>{d.mappings.map((m: Row) => <li key={m.id}>{stamp(m.created_at)} · {m.actor_name} · {m.action} {m.check_key} for {m.gap_key} — {m.reason}</li>)}</ul></details>}</details>}
    {d.history.length > 0 && <details className="prio-edit"><summary>Saved versions · {d.history.length}</summary><ul>{d.history.map((h: Row) => <li key={h.id}>Version {h.rev} · {stamp(h.created_at)} · {h.actor_name}{h.stale ? " · stale" : ""}{h.override ? ` · reviewer override: ${h.override.reason}` : " · calculated order"}</li>)}</ul></details>}
    <p className="subtle">Recorded events: {plural(d.activity.drafts_from_suggestion, "draft")} created from a suggestion · {plural(d.activity.order_overrides, "order override")} · {plural(d.activity.responses_reviewed, "response")} reviewed · {plural(d.activity.mapped_checks_now_verified, "mapped check")} now verified. {d.activity.note}</p>
  </div>;
}
