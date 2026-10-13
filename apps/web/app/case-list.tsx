"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api, stamp } from "./lib";
import { CasePreview, DataTable } from "./workspace-components";
import { BulkBar } from "./improvement-panels";
type Row = Record<string, any>;
const views = [["all", "All cases"], ["mine", "Assigned to me"], ["review", "Awaiting review"], ["overdue", "Overdue"], ["unassigned", "High priority · unassigned"]];
type SavedView = { name: string; status: string; q: string; priority: string; view: string };
export default function CaseList({ me }: { me: Row }) {
  const router = useRouter(), params = useSearchParams(), serialized = params.toString();
  const parse = () => ({ status: params.get("status") === "resolved" ? "resolved" : "open", q: (params.get("q") || "").slice(0, 200), priority: ["high", "medium", "low"].includes(params.get("priority") || "") ? params.get("priority")! : "", view: views.some(v => v[0] === params.get("view")) ? params.get("view")! : "all", offset: Math.max(0, Math.min(100000, Math.floor(Number(params.get("offset"))) || 0)) });
  const [filters, setFilters] = useState(parse), [data, setData] = useState<Row | null>(null), [error, setError] = useState(""), [loading, setLoading] = useState(true), [preview, setPreview] = useState(""), [saved, setSaved] = useState<SavedView[]>([]), [name, setName] = useState(""), [savingView, setSavingView] = useState(false), [message, setMessage] = useState("");
  const pendingNavigation=useRef<string|null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const canBulk = ["owner", "reviewer"].includes(me.role);
  const storageKey = "trialops:views:v1:" + me.user_id + ":" + me.workspace_id;
  useEffect(() => { if(pendingNavigation.current!==null && serialized!==pendingNavigation.current)return;pendingNavigation.current=null;setFilters(parse()); }, [serialized]); // Also restores browser back/forward filters.
  useEffect(() => { try { const items = JSON.parse(localStorage.getItem(storageKey) || "[]"); if (Array.isArray(items)) setSaved(items.filter(v => typeof v.name === "string" && v.name.length <= 40 && ["open", "resolved"].includes(v.status) && typeof v.q === "string" && v.q.length <= 200 && ["", "high", "medium", "low"].includes(v.priority) && views.some(x => x[0] === v.view)).slice(0, 10)); } catch { setSaved([]); } }, [storageKey]);
  const { status, q, priority, view, offset } = filters;
  function change(patch: Partial<typeof filters>) { const next = { ...filters, offset: 0, ...patch }; setFilters(next); const query = new URLSearchParams({ status: next.status, q: next.q, priority: next.priority, view: next.view, offset: String(next.offset) }); pendingNavigation.current=query.toString(); router.replace("/workspace/cases?" + query, { scroll: false }); setMessage(""); }
  useEffect(() => { let active = true; setLoading(true); setError(""); const timer = setTimeout(() => { api("/cases?" + new URLSearchParams({ status, q, priority, view, offset: String(offset) })).then(r => { if (active) { setData(r); setSelected(s => s.filter(id => r.items.some((i: Row) => i.id === id))); setLoading(false); } }).catch(e => { if (active) { setError(e.message); setData(null); setLoading(false); } }); }, 180); return () => { active = false; clearTimeout(timer); }; }, [status, q, priority, view, offset]);
  function saveView(e: React.FormEvent) { e.preventDefault(); const item = { name: name.trim(), status, q, priority, view }; const next = [...saved.filter(v => v.name !== item.name), item].slice(-10); try { localStorage.setItem(storageKey, JSON.stringify(next)); setSaved(next); setSavingView(false); setName(""); setMessage("Personal view saved in this browser."); } catch { setError("This browser cannot store views. Your filters remain available in the URL."); } }
  function removeView(index: number) { const next = saved.filter((_, i) => i !== index); try { localStorage.setItem(storageKey, JSON.stringify(next)); setSaved(next); setMessage("Personal view removed."); } catch { setError("This browser cannot update saved views."); } }
  return <>
    <header className="view-heading"><div><h1>Cases</h1><p>Find an issue and choose the next step.</p></div><Link href="/workspace/new" className="button">Submit an issue →</Link></header>
    {error && <p role="alert" className="error">{error}</p>}{message && <p role="status" className="success">{message}</p>}
    <div className="case-filter-bar"><label>Case status<select aria-label="Case status" value={status} onChange={e => change({ status: e.target.value })}><option value="open">Open</option><option value="resolved">Resolved</option></select></label><div className="tabs case-views" aria-label="Case views">{views.map(([key, label]) => <button key={key} className={view === key ? "active" : ""} aria-pressed={view === key} onClick={() => change({ view: key })}>{label}</button>)}</div></div>
    <div className="case-toolbar"><input aria-label="Search cases" aria-describedby="case-search-help" placeholder="Search number, title, study, or site…" value={q} maxLength={200} onChange={e => change({ q: e.target.value })}/><select aria-label="Filter priority" value={priority} onChange={e => change({ priority: e.target.value })}><option value="">All priorities</option>{["high", "medium", "low"].map(p => <option key={p}>{p}</option>)}</select><button className="outline" onClick={() => setSavingView(!savingView)}>Save view</button></div>
    <p className="subtle case-search-help" id="case-search-help">Find a case by number: 1, case 1, or CASE-1. Titles, studies, and sites also work.</p>
    {savingView && <form className="saved-view-form" onSubmit={saveView}><label>View name<input required minLength={3} maxLength={40} value={name} onChange={e => setName(e.target.value)}/></label><button disabled={name.trim().length < 3}>Save current filters</button><button type="button" className="outline" onClick={() => setSavingView(false)}>Cancel</button><small>Personal to this account and workspace in this browser.</small></form>}
    {!!saved.length && <details className="saved-views"><summary>Saved views · {saved.length}</summary>{saved.map((v, i) => <div className="saved-view-row" key={v.name}><button className="outline" onClick={() => change({ ...v, offset: 0 })}>{v.name}</button><button className="text-button" aria-label={"Remove view " + v.name} onClick={() => removeView(i)}>Remove</button></div>)}</details>}
    {canBulk && status === "open" && <BulkBar me={me} selected={selected} onClear={() => setSelected([])} onDone={() => { setSelected([]); change({}); }}/>}
    <div className="panel table-panel" aria-busy={loading}>{loading ? <p role="status">Loading cases…</p> : !data ? <p>Cases could not be loaded. Change a filter or refresh to try again.</p> : <DataTable<Row> label="Cases" rows={data.items} rowKey={c => c.id} empty={<div className="empty"><h3>No matching cases</h3><p>Try a different search or submit a new issue.</p></div>} columns={[
      ...(canBulk && status === "open" ? [{ label: "Select", render: (c: Row) => <input type="checkbox" aria-label={"Select " + c.id} checked={selected.includes(c.id)} disabled={!selected.includes(c.id) && selected.length >= 25} onChange={e => setSelected(e.target.checked ? [...selected, c.id] : selected.filter(x => x !== c.id))}/> }] : []),
      { label: "Case", render: c => <Link className="case-title" href={"/workspace/cases/" + encodeURIComponent(c.id)}><strong>{c.title}</strong><span className="case-id-chip">{c.id}</span></Link> },
      { label: "Priority", render: c => <span className={"badge " + c.priority}>{c.priority}</span> },
      { label: "Review", render: c => <span className={"badge " + (c.review_status || "not-investigated")}>{c.review_status === "pending" ? "Awaiting review" : c.review_status === "approved" ? "Approved" : c.review_status === "rejected" ? "Rejected" : "Not investigated"}</span> },
      { label: "Study / site", render: c => <><span>{c.study_id}</span><small>{c.site_id}</small></> },
      { label: "Assigned to / follow-up", render: c => <><span>{c.owner_name || "Unassigned"}</span><small>{c.due_at ? stamp(c.due_at) : "No deadline"}</small></> },
      { label: "Action", render: c => <button className="outline" aria-label={"Preview " + c.id} onClick={() => setPreview(c.id)}>Preview</button> },
    ]}/>}</div>
    <div className="pagination"><span role="status">{loading ? "Updating results…" : `${data?.total ?? 0} ${status} cases${view !== "all" ? " in this view" : ""}`}</span><button className="outline" disabled={!offset || loading} onClick={() => change({ offset: Math.max(0, offset - 25) })}>Previous</button><button className="outline" disabled={!data || loading || offset + 25 >= data.total} onClick={() => change({ offset: offset + 25 })}>Next</button></div>
    {preview && <CasePreview caseId={preview} onClose={() => setPreview("")}/>}
  </>;
}
