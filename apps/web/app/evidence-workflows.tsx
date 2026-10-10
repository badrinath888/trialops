"use client";
import {ContinuityPanel,ContactSelect} from "./five-feature-panels";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {AssessmentPanel} from "./assessment-panel";
import { api, download, stamp } from "./lib";
type Row = Record<string, any>;
const localTime = (value = new Date().toISOString()) => {
  const d = new Date(value);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 19);
};
const utc = (value: string) => (value ? new Date(value).toISOString() : null);
const states = [
  ["not_checked", "Not checked"],
  ["verified", "Verified"],
  ["needs_follow_up", "Needs follow-up"],
  ["not_applicable", "Not applicable"],
];
function Status({
  error,
  message,
  busy,
}: {
  error: string;
  message: string;
  busy: boolean;
}) {
  return (
    <>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {message && (
        <p className="success" role="status">
          {message}
        </p>
      )}
      {busy && (
        <p className="subtle" role="status">
          Saving…
        </p>
      )}
    </>
  );
}
function EvidenceSelect({
  items,
  value,
  onChange,
  label = "Supporting evidence",
}: {
  items: Row[];
  value: string[];
  onChange: (v: string[]) => void;
  label?: string;
}) {
  return (
    <>
      <label>
        {label}
        <select
          aria-label={label}
          multiple
          value={value}
          onChange={(e) =>
            onChange(Array.from(e.target.selectedOptions, (o) => o.value))
          }
        >
          {items.map((i) => (
            <option key={i.id} value={i.id}>
              {i.kind.replaceAll("_", " ")} · {i.summary.slice(0, 90)} ·{" "}
              {stamp(i.observed_at)}
            </option>
          ))}
        </select>
      </label>
      <small>
        Choose recorded observations. Hold Command or Control to select more
        than one.
      </small>
    </>
  );
}

export function CaseWorkflows({
  item,
  runId,
  me,
  refreshKey,
  onChanged,
}: {
  item: Row;
  runId: string;
  me: Row;
  refreshKey: number;
  onChanged: () => void;
}) {
  const cid = item.id,
    canReview = ["owner", "reviewer"].includes(me.role),
    base = "/cases/" + encodeURIComponent(cid);
  const [data, setData] = useState<Row | null>(null),
    [members, setMembers] = useState<Row[]>([]),
    [snapshots, setSnapshots] = useState<Row[]>([]),
    [related, setRelated] = useState<Row>({ suggestions: [], links: [] });
  const [dirty, setDirty] = useState<string[]>([]),
    [tab, setTab] = useState("checks"),
    [error, setError] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  const [title, setTitle] = useState(""),
    [requested, setRequested] = useState(""),
    [requestOwner, setRequestOwner] = useState(""),
    [requestDue, setRequestDue] = useState(""),
    [requestId, setRequestId] = useState("");
  const [requestContact,setRequestContact]=useState(""),[duplicateReason,setDuplicateReason]=useState(""),[matches,setMatches]=useState<Row[]>([]),[reused,setReused]=useState("");
  const [kind, setKind] = useState("human_observation"),
    [reference, setReference] = useState(""),
    [summary, setSummary] = useState(""),
    [observed, setObserved] = useState(localTime()),
    [evidenceId, setEvidenceId] = useState("");
  const [before, setBefore] = useState(""),
    [after, setAfter] = useState(""),
    [linkId, setLinkId] = useState(""),
    [rationale, setRationale] = useState(""),
    [linkConfirmed, setLinkConfirmed] = useState(false);
  const [effortMinutes, setEffortMinutes] = useState(""),
    [activity, setActivity] = useState("follow_up"),
    [effortNotes, setEffortNotes] = useState(""),
    [effortId, setEffortId] = useState("");
  const load = useCallback(async () => {
    const [d, m, s, r] = await Promise.all([
      api(base + "/workflow"),
      api("/members"),
      api(
        "/operations/history?study_id=" +
          encodeURIComponent(item.study_id) +
          "&site_id=" +
          encodeURIComponent(item.site_id),
      ),
      api(base + "/related"),
    ]);
    setData(d);
    setDirty([]);
    setMembers(m);
    setSnapshots(s);
    setRelated(r);
  }, [base, item.study_id, item.site_id]);
  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, [load, refreshKey]);
  async function save(
    path: string,
    body: Row,
    success: string,
    done?: () => void,
  ) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await api(path, body);
      await load();
      onChanged();
      setMessage(success);
      done?.();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const checks = data?.checks.filter((c: Row) => c.run_id === runId) || [];
  function changeCheck(id: string, index: number, key: string, value: any) {
    setDirty((xs) => [...new Set([...xs, id])]);
    setData((current) =>
      current
        ? {
            ...current,
            checks: current.checks.map((c: Row) =>
              c.id === id
                ? {
                    ...c,
                    items: c.items.map((i: Row, n: number) =>
                      n === index ? { ...i, [key]: value } : i,
                    ),
                  }
                : c,
            ),
          }
        : current,
    );
  }
  return (
    <section
      className="panel evidence-workflow"
      aria-label="Case evidence workflow"
    >
      <div className="section-heading">
        <h2>Evidence & follow-up</h2>
        <div className="actions">
          <button
            className="outline"
            disabled={busy}
            onClick={async () => {
              try {
                download(
                  "trialops-case-" + cid + ".json",
                  await api(base + "/package.json"),
                );
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          >
            Case package JSON
          </button>
          <a
            className="button outline"
            href={"/api" + base + "/package.pdf"}
            download
          >
            Case package PDF
          </a>
        </div>
      </div>
      <Status error={error} message={message} busy={busy} />
      <ContinuityPanel item={item} me={me} onChanged={onChanged}/>
      {canReview && <AssessmentPanel cid={cid} kind="linkage" onChanged={onChanged} />}
        <div
        className="workflow-tabs"
        role="group"
        aria-label="Evidence workflow sections"
      >
        {[
          ["checks", "Checks"],
          ["requests", "Information requests"],
          ["evidence", "Supporting observations"],
          ["records", "Comparisons & related cases"],
          ["effort", "Human effort"],
        ].map(([key, label]) => (
          <button
            key={key}
            className="outline"
            aria-pressed={tab === key}
            onClick={() => {
              setTab(key);
              setMessage("");
            }}
          >
            {label}
          </button>
        ))}
      </div>
      {!data ? (
        <p role="status">
          Loading evidence workflow…{" "}
          <button
            className="outline"
            onClick={() => load().catch((e) => setError(e.message))}
          >
            Retry
          </button>
        </p>
      ) : (
        <>
          <div hidden={tab !== "checks"}>
            {!runId ? (
              <p>
                Run an investigation to suggest checks from its cited
                procedures.
              </p>
            ) : checks.length === 0 ? (
              <>
                <p>
                  Create a draft using the exact cited procedure sections. A
                  reviewer activates it after review.
                </p>
                <button
                  disabled={busy}
                  onClick={() =>
                    save(
                      "/runs/" + runId + "/checks",
                      {},
                      "Suggested checks saved as a draft.",
                    )
                  }
                >
                  Suggest investigation checks
                </button>
              </>
            ) : (
              checks.map((check: Row) => (
                <div key={check.id}>
                  <p>
                    <strong>
                      {check.status === "active"
                        ? "Human-reviewed checklist"
                        : "Draft · suggestions for human review"}
                    </strong>
                    {check.activated_at &&
                      " · activated " + stamp(check.activated_at)}
                  </p>
                  <details>
                    <summary>Exact cited procedure versions</summary>
                    {check.sources.map((s: Row) => (
                      <article key={s.id} className="source">
                        <h3>{s.title}</h3>
                        <small>{s.id}</small>
                        <p className="preserve">{s.content}</p>
                      </article>
                    ))}
                  </details>
                  {check.items.map((i: Row, index: number) => (
                    <article className="check-item" key={i.id}>
                      {check.status === "draft" ? (
                        <label>
                          Check {index + 1}
                          <textarea
                            aria-label={"Check " + (index + 1)}
                            rows={3}
                            value={i.text}
                            maxLength={50000}
                            onChange={(e) =>
                              changeCheck(
                                check.id,
                                index,
                                "text",
                                e.target.value,
                              )
                            }
                          />
                        </label>
                      ) : (
                        <p className="preserve">
                          <strong>{index + 1}.</strong> {i.text}
                        </p>
                      )}
                      <small>
                        {i.suggestion
                          ? "Suggested from a cited procedure · human review required"
                          : "Human-authored check"}
                      </small>
                      {check.status === "active" && (
                        <div className="form-grid">
                          <label>
                            Check state
                            <select
                              aria-label="Check state"
                              value={i.state}
                              onChange={(e) =>
                                changeCheck(
                                  check.id,
                                  index,
                                  "state",
                                  e.target.value,
                                )
                              }
                            >
                              {states.map(([v, t]) => (
                                <option key={v} value={v}>
                                  {t}
                                </option>
                              ))}
                            </select>
                          </label>
                          <label>
                            Check notes
                            <textarea
                              aria-label="Check notes"
                              value={i.notes}
                              maxLength={4000}
                              rows={2}
                              onChange={(e) =>
                                changeCheck(
                                  check.id,
                                  index,
                                  "notes",
                                  e.target.value,
                                )
                              }
                            />
                          </label>
                        </div>
                      )}
                      {check.status === "active" && (
                        <EvidenceSelect
                          items={data.evidence}
                          value={i.evidence_refs}
                          onChange={(value) =>
                            changeCheck(check.id, index, "evidence_refs", value)
                          }
                        />
                      )}
                      {i.recorded_at && (
                        <small>
                          Recorded by {i.actor_name} · {stamp(i.recorded_at)}
                        </small>
                      )}
                      {check.status === "draft" && (
                        <button
                          className="outline"
                          disabled={busy || check.items.length === 1}
                          onClick={() => {
                            setDirty((xs) => [...new Set([...xs, check.id])]);
                            setData({
                              ...data,
                              checks: data.checks.map((c: Row) =>
                                c.id === check.id
                                  ? {
                                      ...c,
                                      items: c.items.filter(
                                        (_: Row, n: number) => n !== index,
                                      ),
                                    }
                                  : c,
                              ),
                            });
                          }}
                        >
                          Remove check {index + 1}
                        </button>
                      )}
                    </article>
                  ))}
                  {check.status === "draft" && (
                    <button
                      className="outline"
                      disabled={busy}
                      onClick={() => {
                        setDirty((xs) => [...new Set([...xs, check.id])]);
                        setData({
                          ...data,
                          checks: data.checks.map((c: Row) =>
                            c.id === check.id
                              ? {
                                  ...c,
                                  items: [
                                    ...c.items,
                                    {
                                      id: crypto.randomUUID(),
                                      text: "",
                                      source_id: c.sources[0].id,
                                      suggestion: false,
                                      state: "not_checked",
                                      notes: "",
                                      evidence_refs: [],
                                    },
                                  ],
                                }
                              : c,
                          ),
                        });
                      }}
                    >
                      Add a human-authored check
                    </button>
                  )}
                  <label>
                    Checklist follow-up deadline
                    <input
                      type="datetime-local"
                      step="1"
                      value={check.due_at ? localTime(check.due_at) : ""}
                      onChange={(e) =>
                        setData({
                          ...data,
                          checks: data.checks.map((c: Row) =>
                            c.id === check.id
                              ? { ...c, due_at: utc(e.target.value) }
                              : c,
                          ),
                        })
                      }
                    />
                  </label>
                  <div className="actions">
                    <button
                      disabled={
                        busy || check.items.some((i: Row) => !i.text.trim())
                      }
                      onClick={() =>
                        save(
                          base + "/checks/" + check.id,
                          {
                            expected_version: check.version,
                            items: check.items,
                            due_at: check.due_at,
                          },
                          "Checklist saved.",
                        )
                      }
                    >
                      Save checklist
                    </button>
                    {check.status === "draft" && canReview && (
                      <button
                        className="outline"
                        disabled={busy || dirty.includes(check.id)}
                        onClick={() =>
                          save(
                            base + "/checks/" + check.id + "/activate",
                            { expected_version: check.version },
                            "Reviewed checklist activated.",
                          )
                        }
                      >
                        Activate reviewed checklist
                      </button>
                    )}
                  </div>
                  <small>
                    Save edits before activation. Changing an active checklist's
                    structure requires reviewer approval and reactivation.
                  </small>
                </div>
              ))
            )}
          </div>
          <div hidden={tab !== "requests"}>
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                if(busy)return;setBusy(true);
                try {const m=await api(base+"/request-matches",{items:requested.split("\n").map(v=>v.trim()).filter(Boolean)});setMatches(m);if(m.length&&duplicateReason.trim().length<10){setBusy(false);return;}}catch(e){setError((e as Error).message);setBusy(false);return;}
                const id = requestId || crypto.randomUUID();
                setRequestId(id);
                void save(
                  base + "/requests",
                  {
                    id,
                    run_id: runId,
                    title,contact_id:requestContact||null,duplicate_reason:duplicateReason,
                    items: requested
                      .split("\n")
                      .map((x) => x.trim())
                      .filter(Boolean),
                    owner_id: requestOwner || null,
                    due_at: utc(requestDue),
                  },
                  "Information request draft saved. No message sent.",
                  () => {
                    setTitle("");
                    setRequested("");
                    setRequestId("");setMatches([]);setDuplicateReason("");setRequestContact("");setReused("");
                  },
                );
              }}
            >
              <h3>Draft an information request</h3>
              <ContactSelect item={item} value={requestContact} onChange={setRequestContact}/>
              {matches.length>0&&<div className="notice"><strong>Open request asks for the same evidence</strong>{matches.map(m=><p key={m.id}>{m.title} · <a href={"/workspace/cases/"+encodeURIComponent(m.case_id)}>Open existing request case {m.case_id}</a><br/>{m.explanation}<br/>{m.matched_items.join('; ')}<button type="button" className="outline" onClick={()=>{setReused(m.id);setRequested('');setMatches([]);setDuplicateReason('');setMessage('Existing request reused. No new request or message created.')}}>Reuse existing request</button></p>)}<label>Reason to proceed with a separate request<textarea minLength={10} maxLength={2000} value={duplicateReason} onChange={e=>setDuplicateReason(e.target.value)}/></label></div>}
              {reused&&<p role="status">Reusing request {reused}; see Saved requests or its case. No duplicate created.</p>}
              <label>
                Request title
                <input
                  required
                  minLength={5}
                  maxLength={200}
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </label>
              <label>
                Requested items
                <textarea
                  required
                  rows={3}
                  value={requested}
                  onChange={(e) => setRequested(e.target.value)}
                  placeholder="One item per line"
                />
              </label>
              <div className="form-grid">
                <label>
                  Request owner
                  <select
                    value={requestOwner}
                    onChange={(e) => setRequestOwner(e.target.value)}
                  >
                    <option value="">Unassigned</option>
                    {members.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Request due date
                  <input
                    type="datetime-local"
                    step="1"
                    value={requestDue}
                    onChange={(e) => setRequestDue(e.target.value)}
                  />
                </label>
              </div>
              <button disabled={busy || !runId}>Save request draft</button>
              {!runId && <small>Choose a saved investigation first.</small>}
            </form>
            <h3>Saved requests</h3>
            {data.requests.length === 0 ? (
              <p>No information requests.</p>
            ) : (
              data.requests.map((r: Row) => (
                <RequestEditor
                  key={r.id + ":" + r.version}
                  request={r}
                  caseItem={item}
                  evidence={data.evidence}
                  members={members}
                  busy={busy}
                  onSave={(body) =>
                    save(
                      base + "/requests/" + r.id,
                      body,
                      "Request updated. No message sent.",
                    )
                  }
                  onError={setError}
                />
              ))
            )}
          </div>
          <div hidden={tab !== "evidence"}>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const id = evidenceId || crypto.randomUUID();
                setEvidenceId(id);
                void save(
                  base + "/evidence",
                  {
                    id,
                    kind,
                    reference_id: reference || null,
                    summary,
                    observed_at: utc(observed),
                  },
                  "Supporting observation recorded.",
                  () => {
                    setSummary("");
                    setEvidenceId("");
                    setObserved(localTime());
                  },
                );
              }}
            >
              <h3>Record a supporting observation</h3>
              <div className="form-grid">
                <label>
                  Observation type
                  <select
                    value={kind}
                    onChange={(e) => {
                      setKind(e.target.value);
                      setReference("");
                    }}
                  >
                    <option value="human_observation">
                      Human verification observation
                    </option>
                    <option value="snapshot">Historical snapshot</option>
                    <option value="request_response">
                      Information response
                    </option>
                  </select>
                </label>
                <label>
                  Observation time
                  <input
                    required
                    type="datetime-local"
                    step="1"
                    value={observed}
                    disabled={kind === "snapshot"}
                    onChange={(e) => setObserved(e.target.value)}
                  />
                </label>
              </div>
              {kind !== "human_observation" && (
                <label>
                  {kind === "snapshot"
                    ? "Referenced snapshot"
                    : "Referenced request"}
                  <select
                    required
                    value={reference}
                    onChange={(e) => {
                      setReference(e.target.value);
                      if (kind === "snapshot") {
                        const s = snapshots.find(
                          (x) => x.id === e.target.value,
                        );
                        if (s) setObserved(localTime(s.observed_at));
                      }
                    }}
                  >
                    <option value="">Choose a reference</option>
                    {(kind === "snapshot" ? snapshots : data.requests).map(
                      (x: Row) => (
                        <option key={x.id} value={x.id}>
                          {x.title || x.external_id}{" "}
                          {x.observed_at && stamp(x.observed_at)}
                        </option>
                      ),
                    )}
                  </select>
                </label>
              )}
              <label>
                Observation and evidence summary
                <textarea
                  required
                  minLength={10}
                  maxLength={4000}
                  rows={3}
                  value={summary}
                  onChange={(e) => setSummary(e.target.value)}
                  placeholder="Describe what you personally checked, where you checked it, and what you observed."
                />
              </label>
              <button disabled={busy}>Record observation</button>
            </form>
            {data.evidence.map((e: Row) => (
              <article className="work-row" key={e.id}>
                <div>
                  <strong>{e.summary}</strong>
                  <small>
                    {e.kind.replaceAll("_", " ")} · {e.actor_name} · observed{" "}
                    {stamp(e.observed_at)}
                  </small>
                </div>
              </article>
            ))}
            {data.evidence.length === 0 && (
              <p>No supporting observations yet.</p>
            )}
          </div>
          <div hidden={tab !== "records"}>
            <h3>Observation flags</h3>
            {data.flags.length === 0 ? (
              <p>No record flags under the configured workspace policy.</p>
            ) : (
              data.flags.map((f: Row, n: number) => (
                <details key={n}>
                  <summary>
                    {f.type.replaceAll("_", " ")} · {f.explanation}
                  </summary>
                  <pre>{JSON.stringify(f, null, 2)}</pre>
                </details>
              ))
            )}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void save(
                  base + "/comparisons",
                  { before_id: before, after_id: after },
                  "Observation comparison saved.",
                );
              }}
            >
              <h3>Compare recorded observations</h3>
              <div className="form-grid">
                {[
                  ["Earlier snapshot", before, setBefore],
                  ["Later snapshot", after, setAfter],
                ].map(([label, value, setter]) => (
                  <label key={label as string}>
                    {label as string}
                    <select
                      required
                      value={value as string}
                      onChange={(e) =>
                        (setter as (v: string) => void)(e.target.value)
                      }
                    >
                      <option value="">Choose an observation</option>
                      {snapshots.map((s) => (
                        <option key={s.id} value={s.id}>
                          {stamp(s.observed_at)} · {s.external_id}
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
              <button disabled={busy || !before || !after}>
                Compare snapshots
              </button>
            </form>
            {data.comparisons.map((c: Row) => (
              <details key={c.id}>
                <summary>
                  {stamp(c.comparison.before_observed_at)} →{" "}
                  {stamp(c.comparison.after_observed_at)}
                </summary>
                <p>{c.comparison.interpretation}</p>
                {c.comparison.records.map((r: Row) => (
                  <article
                    className="comparison-record"
                    key={r.kind + ":" + r.record_id}
                  >
                    <strong>
                      {r.state} · {r.record_id}
                    </strong>
                    {r.fields.map((f: Row) => (
                      <p key={f.field}>
                        {f.field.replaceAll("_", " ")}:{" "}
                        {String(f.before ?? "Not recorded")} →{" "}
                        {String(f.after ?? "Not recorded")}
                      </p>
                    ))}
                    {r.state === "missing" && (
                      <p>
                        Absent from the later snapshot; resolution is
                        unconfirmed.
                      </p>
                    )}
                  </article>
                ))}
              </details>
            ))}
            <h3>Related cases for human review</h3>
            <p className="subtle">
              Similarity does not establish a shared root cause. Linking cases
              never closes them.
            </p>
            {related.suggestions.map((r: Row) => (
              <article className="related-case" key={r.id}>
                <Link className="text-link" href={"/workspace/cases/" + r.id}>
                  {r.title}
                </Link>
                <small>{r.reason}</small>
                <p>
                  {r.status}
                  {r.resolution && " · Recorded outcome: " + r.resolution}
                </p>
                {r.differences.length > 0 && (
                  <details>
                    <summary>Relevant differences</summary>
                    {r.differences.map((d: string) => (
                      <p key={d}>{d}</p>
                    ))}
                  </details>
                )}
                <button
                  className="outline"
                  disabled={busy}
                  onClick={() => {
                    setLinkId(r.id);
                    setLinkConfirmed(false);
                  }}
                >
                  Review link to {r.id}
                </button>
              </article>
            ))}
            {related.suggestions.length === 0 && <p>No related suggestions.</p>}
            {linkId && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void save(
                    base + "/related",
                    { related_id: linkId, rationale, confirmed: linkConfirmed },
                    "Human-confirmed case link saved.",
                    () => {
                      setLinkId("");
                      setRationale("");
                    },
                  );
                }}
              >
                <label>
                  Reason for linking
                  <textarea
                    required
                    minLength={10}
                    value={rationale}
                    onChange={(e) => setRationale(e.target.value)}
                  />
                </label>
                <label className="check-row">
                  <input
                    type="checkbox"
                    checked={linkConfirmed}
                    onChange={(e) => setLinkConfirmed(e.target.checked)}
                  />
                  <span>I reviewed the differences and confirm this link.</span>
                </label>
                <button disabled={busy || !linkConfirmed}>
                  Confirm related-case link
                </button>
              </form>
            )}
            {related.links.length > 0 && (
              <details>
                <summary>{related.links.length} confirmed links</summary>
                {related.links.map((l: Row) => (
                  <p key={l.case_id + ":" + l.related_id}>
                    {l.case_id} ↔ {l.related_id} · {l.rationale}
                  </p>
                ))}
              </details>
            )}
          </div>
          <div hidden={tab !== "effort"}>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const id = effortId || crypto.randomUUID();
                setEffortId(id);
                void save(
                  base + "/effort",
                  {
                    id,
                    run_id: runId || null,
                    minutes: Number(effortMinutes),
                    activity,
                    notes: effortNotes,
                  },
                  "Human effort recorded.",
                  () => {
                    setEffortMinutes("");
                    setEffortNotes("");
                    setEffortId("");
                  },
                );
              }}
            >
              <h3>Record human effort</h3>
              <p>
                Enter time you actually spent. Queue and execution durations are
                measured separately.
              </p>
              <div className="form-grid">
                <label>
                  Human work minutes
                  <input
                    required
                    type="number"
                    min="0.1"
                    max="1440"
                    step="0.1"
                    value={effortMinutes}
                    onChange={(e) => setEffortMinutes(e.target.value)}
                  />
                </label>
                <label>
                  Work activity
                  <select
                    value={activity}
                    onChange={(e) => setActivity(e.target.value)}
                  >
                    {["investigation", "review", "follow_up", "resolution"].map(
                      (v) => (
                        <option key={v} value={v}>
                          {v.replaceAll("_", " ")}
                        </option>
                      ),
                    )}
                  </select>
                </label>
              </div>
              <label>
                Effort notes
                <textarea
                  required
                  minLength={5}
                  maxLength={2000}
                  value={effortNotes}
                  onChange={(e) => setEffortNotes(e.target.value)}
                />
              </label>
              <button disabled={busy}>Record human effort</button>
            </form>
            {data.effort.map((e: Row) => (
              <p key={e.id}>
                {e.minutes} minutes · {e.activity.replaceAll("_", " ")} ·{" "}
                {e.notes}
              </p>
            ))}
          </div>
        </>
      )}
    </section>
  );
}

function RequestEditor({
  request: r,
  caseItem,
  evidence,
  members,
  busy,
  onSave,
  onError,
}: {
  request: Row;
  caseItem: Row;
  evidence: Row[];
  members: Row[];
  busy: boolean;
  onSave: (v: Row) => void;
  onError: (e: string) => void;
}) {
  const [contactId,setContactId]=useState(r.contact_id||""),[overrideReason,setOverrideReason]=useState(r.duplicate_reason||"");
  const [title, setTitle] = useState(r.title),
    [items, setItems] = useState(r.items.join("\n")),
    [owner, setOwner] = useState(r.owner_id || ""),
    [due, setDue] = useState(r.due_at ? localTime(r.due_at) : ""),
    [status, setStatus] = useState(r.status),
    [response, setResponse] = useState(""),
    [refs, setRefs] = useState<string[]>([]),
    [copyMessage, setCopyMessage] = useState("");
  return (
    <details className="request-detail">
      <summary>
        {r.title} · {r.effective_status}
      </summary>
      <small>
        {r.owner_name || "Unassigned"} ·{" "}
        {r.due_at ? stamp(r.due_at) : "No deadline"}
      </small>
      <div className="actions">
        <button
          className="outline"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(r.copy_text);
              setCopyMessage("Request copied. No message sent.");
            } catch {
              onError("Copy unavailable. Select the request text below.");
            }
          }}
        >
          Copy request text
        </button>
      </div>
      {copyMessage && <p role="status">{copyMessage}</p>}
      <ContactSelect item={caseItem} value={contactId} onChange={setContactId}/>
      {r.status==="draft"&&<label>Reason for separate evidence request<textarea maxLength={2000} value={overrideReason} onChange={e=>setOverrideReason(e.target.value)}/></label>}
      <details>
        <summary>Copyable request text</summary>
        <pre>{r.copy_text}</pre>
      </details>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSave({
            expected_version: r.version,contact_id:contactId||null,duplicate_reason:overrideReason,
            title,
            items: items
              .split("\n")
              .map((x: string) => x.trim())
              .filter(Boolean),
            owner_id: owner || null,
            due_at: utc(due),
            status,
            response,
            evidence_refs: refs,
          });
        }}
      >
        <label>
          Saved request title
          <input
            required
            value={title}
            disabled={r.status !== "draft"}
            onChange={(e) => setTitle(e.target.value)}
          />
        </label>
        <label>
          Saved requested items
          <textarea
            required
            rows={3}
            value={items}
            disabled={r.status !== "draft"}
            onChange={(e) => setItems(e.target.value)}
          />
        </label>
        <div className="form-grid">
          <label>
            Saved request owner
            <select value={owner} onChange={(e) => setOwner(e.target.value)}>
              <option value="">Unassigned</option>
              {members.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Saved request due date
            <input
              type="datetime-local"
              step="1"
              value={due}
              onChange={(e) => setDue(e.target.value)}
            />
          </label>
        </div>
        <label>
          Request status
          <select
            aria-label="Request status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            {["draft", "requested", "received", "cancelled"].map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
          <small>
            “Requested” records your follow-up status; this app sends no
            message.
          </small>
        </label>
        <label>
          Response received
          <textarea
            rows={3}
            maxLength={4000}
            value={response}
            onChange={(e) => setResponse(e.target.value)}
          />
        </label>
        <EvidenceSelect
          items={evidence}
          value={refs}
          onChange={setRefs}
          label="Response evidence references"
        />
        <button disabled={busy}>Save request update</button>
      </form>
      {r.responses.map((x: Row, n: number) => (
        <p key={n}>
          {x.text}
          <small>
            {x.actor_name} · {stamp(x.recorded_at)}
          </small>
        </p>
      ))}
    </details>
  );
}

export function EvidenceResolution({
  cid,
  updatedAt,
  runs,
  refreshKey,
  onResolved,
}: {
  cid: string;
  updatedAt: string;
  runs: Row[];
  refreshKey: number;
  onResolved: () => void;
}) {
  const [data, setData] = useState<Row | null>(null),
    [runId, setRunId] = useState(runs[0]?.id || ""),
    [notes, setNotes] = useState(""),
    [verified, setVerified] = useState(localTime()),
    [refs, setRefs] = useState<string[]>([]),
    [exceptions, setExceptions] = useState(""),
    [confirmed, setConfirmed] = useState(false),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    api("/cases/" + encodeURIComponent(cid) + "/workflow")
      .then((d) => {
        setData(d);
        setVerified(localTime());
      })
      .catch((e) => setError(e.message));
  }, [cid, refreshKey]);
  const checks = data?.checks.filter((c: Row) => c.run_id === runId) || [];
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError("");
        try {
          await api("/cases/" + encodeURIComponent(cid) + "/resolve", {
            run_id: runId,
            notes,
            confirmed,
            verified_at: utc(verified),
            evidence_refs: refs,
            exceptions,
            expected_updated_at: updatedAt,
          });
          onResolved();
        } catch (err) {
          setError((err as Error).message);
        } finally {
          setBusy(false);
        }
      }}
    >
      <Status error={error} message="" busy={busy} />
      <label>
        Approved investigation
        <select value={runId} onChange={(e) => setRunId(e.target.value)}>
          {runs.map((r) => (
            <option key={r.id} value={r.id}>
              {stamp(r.created_at)} · approved
            </option>
          ))}
        </select>
      </label>
      <p>
        {checks.length === 0
          ? "Activate investigation checks in Evidence & follow-up before resolving."
          : checks
              .map(
                (c: Row) =>
                  `${c.items.filter((i: Row) => i.state !== "not_checked").length}/${c.items.length} checks assessed · ${c.status}`,
              )
              .join("; ")}
      </p>
      <AssessmentPanel cid={cid} text={notes} />
      <label>
        Resolution note
        <textarea
          required
          minLength={10}
          maxLength={2000}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
        />
      </label>
      <label>
        Current verification time
        <input
          required
          type="datetime-local"
          step="1"
          value={verified}
          onChange={(e) => setVerified(e.target.value)}
        />
      </label>
      <EvidenceSelect
        items={data?.evidence || []}
        value={refs}
        onChange={setRefs}
        label="Resolution supporting evidence"
      />
      <label>
        Resolution exceptions
        <textarea
          maxLength={4000}
          rows={2}
          value={exceptions}
          onChange={(e) => setExceptions(e.target.value)}
          placeholder="Explain remaining follow-up or not-applicable checks, if any."
        />
      </label>
      <label className="check-row">
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
        />
        <span>
          I verified current status using the recorded human observation.
          Historical snapshots alone do not confirm resolution.
        </span>
      </label>
      <button
        disabled={
          busy || !confirmed || !refs.length || notes.trim().length < 10
        }
      >
        Mark case resolved
      </button>
    </form>
  );
}
