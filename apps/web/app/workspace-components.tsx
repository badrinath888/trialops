"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, stamp } from "./lib";
export type DisplayPreferences = { density: "compact" | "comfortable"; startPage: "overview" | "cases" };
const defaults: DisplayPreferences = { density: "compact", startPage: "overview" };
export function preferenceKey(userId: string) { return "trialops:display:v1:" + userId; }
export function readPreferences(userId: string): DisplayPreferences {
  try { const value = JSON.parse(localStorage.getItem(preferenceKey(userId)) || "{}"); return { density: value.density === "comfortable" ? "comfortable" : "compact", startPage: value.startPage === "cases" ? "cases" : "overview" }; } catch { return defaults; }
}
export function savePreferences(userId: string, prefs: DisplayPreferences) {
  localStorage.setItem(preferenceKey(userId), JSON.stringify(prefs));
  window.dispatchEvent(new Event("trialops-preferences"));
}
export function usePreferences(userId?: string) {
  const [prefs, setPrefs] = useState<DisplayPreferences>(defaults);
  useEffect(() => { if (!userId) return; const update = () => setPrefs(readPreferences(userId)); update(); window.addEventListener("trialops-preferences", update); window.addEventListener("storage", update); return () => { window.removeEventListener("trialops-preferences", update); window.removeEventListener("storage", update); }; }, [userId]);
  return prefs;
}
export function DataTable<T>({ label, columns, rows, rowKey, empty }: { label: string; columns: { label: string; render: (row: T) => React.ReactNode }[]; rows: T[]; rowKey: (row: T) => string; empty?: React.ReactNode }) {
  return <div className="data-table-wrap"><table className="data-table" aria-label={label}><thead><tr>{columns.map(c => <th key={c.label} scope="col">{c.label}</th>)}</tr></thead><tbody>{rows.length ? rows.map(row => <tr key={rowKey(row)}>{columns.map(c => <td key={c.label}>{c.render(row)}</td>)}</tr>) : <tr><td colSpan={columns.length}>{empty || "No matching records."}</td></tr>}</tbody></table></div>;
}
export function CasePreview({ caseId, onClose }: { caseId: string; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null), invoker = useRef<HTMLElement | null>(null);
  const [data, setData] = useState<Record<string, any> | null>(null), [error, setError] = useState("");
  useEffect(() => { invoker.current = document.activeElement as HTMLElement; dialog.current?.showModal(); return () => { if (invoker.current?.isConnected) invoker.current.focus(); }; }, []);
  useEffect(() => { let active = true; setData(null); setError(""); api("/cases/" + encodeURIComponent(caseId)).then(r => { if (active) setData(r); }).catch(e => { if (active) setError(e.message); }); return () => { active = false; }; }, [caseId]);
  const c = data?.case;
  return <dialog ref={dialog} className="case-preview" aria-labelledby="case-preview-title" onClose={onClose} onKeyDown={event=>{if(event.key!=="Tab")return;const elements=Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex="0"]')).filter(e=>e.getClientRects().length);const first=elements[0],last=elements.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}}}>
    <div className="section-heading"><span className="subtle">{caseId}</span><button className="outline" onClick={() => dialog.current?.close()}>Close preview</button></div>
    <h2 id="case-preview-title">{c?.title || "Opening case…"}</h2>
    {error && <p role="alert" className="error">{error}</p>}
    {!c && !error && <p role="status">Loading case details…</p>}
    {c && <><p className="preserve">{c.description}</p><dl className="preview-fields"><div><dt>Study / site</dt><dd>{c.study_id} / {c.site_id}</dd></div><div><dt>Status</dt><dd>{c.status}</dd></div><div><dt>Priority</dt><dd>{c.priority}</dd></div><div><dt>Follow-up</dt><dd>{c.due_at ? stamp(c.due_at) : "Not set"}</dd></div></dl>
      <p className="subtle">{data.runs.length} saved investigations. {data.job && ["queued", "running"].includes(data.job.status) ? "An investigation is in progress." : ""}</p>
      <Link className="button" href={"/workspace/cases/" + encodeURIComponent(caseId)}>Open full case →</Link></>}
  </dialog>;
}
