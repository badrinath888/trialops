"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {AssessmentDemo} from "./assessment-panel";
import { api, stamp } from "./lib";
type Row = Record<string, any>;
const local = (value = new Date().toISOString()) => {
  const d = new Date(value);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 19);
};
const iso = (value: string) => new Date(value).toISOString();
const average = (values: (number | null)[]) => {
  const known = values.filter(
    (v): v is number => v !== null && Number.isFinite(v),
  );
  return known.length
    ? (known.reduce((a, b) => a + b, 0) / known.length / 60).toFixed(1) + " min"
    : "Not measured";
};
function Messages({ error, message }: { error: string; message: string }) {
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
    </>
  );
}

export function OverviewRelease({ me }: { me: Row }) {
  const [notifications, setNotifications] = useState<Row[] | null>(null),
    [error, setError] = useState("");
  const load = useCallback(
    () =>
      api("/notifications")
        .then(setNotifications)
        .catch((e) => setError(e.message)),
    [],
  );
  useEffect(() => {
    void load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, [load]);
  return (
    <>
      {me.demo && <><SampleWalkthrough /><AssessmentDemo /></>}
      <details className="panel">
        <summary>
          In-app follow-up reminders ·{" "}
          {notifications?.filter((n) => !n.read_at).length || 0} unread
        </summary>
        <Messages error={error} message="" />
        {notifications === null ? (
          <p role="status">Loading reminders…</p>
        ) : notifications.length === 0 ? (
          <p>
            No reminders yet. The durable worker checks unfinished work using
            workspace preferences.
          </p>
        ) : (
          notifications.map((n) => (
            <div className="work-row" key={n.id}>
              <div>
                <Link
                  className="text-link"
                  href={"/workspace/cases/" + n.case_id}
                >
                  {n.title}
                </Link>
                <small>
                  {stamp(n.created_at)} · {n.read_at ? "Read" : "Unread"}
                </small>
              </div>
              {!n.read_at && (
                <button
                  className="outline"
                  onClick={async () => {
                    try {
                      await api("/notifications/" + n.id + "/read", {});
                      await load();
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                >
                  Mark read
                </button>
              )}
            </div>
          ))
        )}
        <button className="outline" onClick={load}>
          Refresh reminders
        </button>
      </details>
      <MeasuredMetrics />
    </>
  );
}

export function MeasuredMetrics() {
  const [open, setOpen] = useState(false),
    [data, setData] = useState<Row | null>(null),
    [error, setError] = useState("");
  const load = () =>
    api("/metrics")
      .then(setData)
      .catch((e) => setError(e.message));
  useEffect(() => {
    if (open) void load();
  }, [open]);
  return (
    <details className="panel" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>Measured workflow activity</summary>
      <Messages error={error} message="" />
      {data ? (
        <>
          <div className="measured-metrics">
            {[
              [
                "Queue duration",
                average(data.jobs.map((j: Row) => j.queue_seconds)),
              ],
              [
                "Investigation execution",
                average(data.runs.map((r: Row) => r.duration_seconds)),
              ],
              [
                "Review turnaround",
                average(data.runs.map((r: Row) => r.review_turnaround_seconds)),
              ],
              [
                "Resolved cycle duration",
                average(
                  data.resolution_cycles
                    .filter((c: Row) => c.resolved_at)
                    .map((c: Row) => c.elapsed_seconds),
                ),
              ],
              [
                "Explicit human effort",
                data.human_effort.length
                  ? data.human_effort.reduce(
                      (sum: number, e: Row) => sum + Number(e.minutes),
                      0,
                    ) + " min"
                  : "Not recorded",
              ],
            ].map(([label, value]) => (
              <div key={label}>
                <small>{label}</small>
                <strong>{value}</strong>
              </div>
            ))}
          </div>
          <p>Elapsed time describes activity. Assumed ROI remains separate.</p>
          <details>
            <summary>Measurement definitions and repeated work</summary>
            {Object.entries(data.definitions).map(([k, v]) => (
              <p key={k}>
                <strong>{k.replaceAll("_", " ")}</strong>: {String(v)}
              </p>
            ))}
            <div
              className="data-table-wrap"
              tabIndex={0}
              role="region"
              aria-label="Measured investigation durations"
            >
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Case</th>
                    <th>Executed</th>
                    <th>Execution</th>
                    <th>Review turnaround</th>
                  </tr>
                </thead>
                <tbody>
                  {data.runs.map((r: Row) => (
                    <tr key={r.id}>
                      <td>
                        <Link href={"/workspace/cases/" + r.case_id}>
                          {r.case_id}
                        </Link>
                      </td>
                      <td>{stamp(r.created_at)}</td>
                      <td>{r.duration_seconds}s</td>
                      <td>
                        {r.review_turnaround_seconds === null
                          ? "Pending"
                          : (r.review_turnaround_seconds / 60).toFixed(1) +
                            " min"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      ) : (
        <p role="status">
          {error
            ? "Activity could not be loaded."
            : "Loading measured activity…"}
        </p>
      )}
      <button className="outline" onClick={load}>
        Refresh activity
      </button>
    </details>
  );
}

function SampleWalkthrough() {
  const [progress, setProgress] = useState<Row | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  useEffect(() => {
    api("/walkthrough")
      .then(setProgress)
      .catch((e) => setError(e.message));
  }, []);
  const steps = [
    {
      title: "Missing certificate",
      body: "Investigate the uploaded certificate. Inspect its cited procedure, pending duration and dated upload record.",
      path: "/workspace/cases/CASE-1",
    },
    {
      title: "Failed synchronization",
      body: "Investigate the failed synchronization job. Read its exact procedure and unsent draft.",
      path: "/workspace/cases/CASE-4",
    },
    {
      title: "Healthy status",
      body: "Investigate the healthy synchronization status. Completed jobs should not trigger a failed-job escalation.",
      path: "/workspace/cases/CASE-6",
    },
    {
      title: "Unsupported request",
      body: "Investigate the cafeteria question. Relevant support should be absent and approval unavailable.",
      path: "/workspace/cases/CASE-7",
    },
    {
      title: "Updated observations",
      body: "Load a newer healthy synthetic observation, then compare it with the original in the synchronization case. Absence alone never establishes resolution.",
      path: "/workspace/cases/CASE-4",
    },
    {
      title: "Human verification and resolution",
      body: "Review and activate the synchronization checks, record a current human observation, complete the checks, record a recommendation decision and resolve separately. Reopen and export its case package to inspect the preserved history.",
      path: "/workspace/cases/CASE-4",
    },
  ];
  async function update(step: number, skipped = false) {
    setBusy(true);
    setError("");
    try {
      setProgress(await api("/walkthrough", { step, skipped }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (!progress)
    return <p role="status">{error || "Loading sample walkthrough…"}</p>;
  if (progress.skipped)
    return (
      <div className="panel">
        <button
          className="outline"
          disabled={busy}
          onClick={() => update(progress.step, false)}
        >
          Resume sample walkthrough
        </button>
        <Messages error={error} message="" />
      </div>
    );
  const step = steps[progress.step];
  return (
    <section
      className="panel walkthrough"
      aria-label="Guided sample walkthrough"
    >
      <div className="section-heading">
        <h2>
          {step
            ? `Sample walkthrough · ${progress.step + 1} of ${steps.length}`
            : "Sample walkthrough reviewed"}
        </h2>
        <button
          className="outline"
          disabled={busy}
          onClick={() => update(progress.step, true)}
        >
          Skip walkthrough
        </button>
      </div>
      <Messages error={error} message={message} />
      {step ? (
        <>
          <h3>{step.title}</h3>
          <p>{step.body}</p>
          <div className="actions">
            <Link className="button" href={step.path}>
              Open this scenario
            </Link>
            {progress.step === 4 && (
              <button
                className="outline"
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  try {
                    await api("/walkthrough/updated-records", {});
                    setMessage(
                      "New synthetic observation saved in this sample workspace.",
                    );
                  } catch (e) {
                    setError((e as Error).message);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Load updated sample records
              </button>
            )}
            <button
              className="outline"
              disabled={busy}
              onClick={() => update(progress.step + 1)}
            >
              I reviewed this step · continue
            </button>
            {progress.step > 0 && (
              <button
                className="outline"
                disabled={busy}
                onClick={() => update(progress.step - 1)}
              >
                Previous step
              </button>
            )}
          </div>
        </>
      ) : (
        <>
          <p>
            Review progress is saved in this sample workspace. Permanent
            accounts use separate data.
          </p>
          <button className="outline" onClick={() => update(0)}>
            Restart walkthrough
          </button>
        </>
      )}
    </section>
  );
}

export function WorkspacePolicies({ me }: { me: Row }) {
  const [policy, setPolicy] = useState<Row | null>(null),
    [prefs, setPrefs] = useState<Row | null>(null),
    [fresh, setFresh] = useState(""),
    [lead, setLead] = useState("24"),
    [frequency, setFrequency] = useState("60"),
    [template, setTemplate] = useState(""),
    [error, setError] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    Promise.all([api("/policies"), api("/notification-preferences")])
      .then(([p, n]) => {
        setPolicy(p);
        setPrefs(n);
        setFresh(p.freshness_hours === null ? "" : String(p.freshness_hours));
        setLead(String(p.reminder_lead_hours));
        setFrequency(String(p.reminder_frequency_minutes));
        setTemplate(p.visit_checklist.join("\n"));
      })
      .catch((e) => setError(e.message));
  }, []);
  async function save(path: string, body: Row) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const d = await api(path, body);
      if (path === "/policies") setPolicy(d);
      else setPrefs(d);
      setMessage("Preferences saved.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel">
      <h2>Evidence and follow-up preferences</h2>
      <Messages error={error} message={message} />
      {prefs && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void save("/notification-preferences", prefs);
          }}
        >
          <h3>Your in-app reminders</h3>
          <label className="check-row">
            <input
              type="checkbox"
              checked={prefs.enabled}
              onChange={(e) =>
                setPrefs({ ...prefs, enabled: e.target.checked })
              }
            />
            <span>Enable in-app follow-up reminders</span>
          </label>
          <div className="reminder-choices">
            {[
              ["request", "Overdue requests"],
              ["check", "Unfinished checks"],
              ["reassessment", "Procedure reassessment"],
              ["deadline", "Approaching case deadlines"],
            ].map(([key, label]) => (
              <label className="check-row" key={key}>
                <input
                  type="checkbox"
                  checked={prefs.kinds.includes(key)}
                  onChange={(e) =>
                    setPrefs({
                      ...prefs,
                      kinds: e.target.checked
                        ? [...prefs.kinds, key]
                        : prefs.kinds.filter((k: string) => k !== key),
                    })
                  }
                />
                <span>{label}</span>
              </label>
            ))}
          </div>
          <button disabled={busy}>Save reminder preferences</button>
        </form>
      )}
      {policy && me.role === "owner" ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void save("/policies", {
              expected_version: policy.version,
              freshness_hours: fresh ? Number(fresh) : null,
              reminder_lead_hours: Number(lead),
              reminder_frequency_minutes: Number(frequency),
              visit_checklist: template
                .split("\n")
                .map((x) => x.trim())
                .filter(Boolean),
            });
          }}
        >
          <h3>Workspace evidence policy</h3>
          <div className="form-grid">
            <label>
              Observation freshness limit (hours)
              <input
                type="number"
                min="0.1"
                step="0.1"
                value={fresh}
                onChange={(e) => setFresh(e.target.value)}
                placeholder="No configured limit"
              />
              <small>
                Leave blank for no age threshold. Warnings do not diagnose a
                condition.
              </small>
            </label>
            <label>
              Reminder lead time (hours)
              <input
                required
                type="number"
                min="0"
                max="168"
                value={lead}
                onChange={(e) => setLead(e.target.value)}
              />
            </label>
            <label>
              Reminder scan frequency (minutes)
              <input
                required
                type="number"
                min="15"
                max="10080"
                value={frequency}
                onChange={(e) => setFrequency(e.target.value)}
              />
            </label>
          </div>
          <label>
            Monitoring-visit checklist template
            <textarea
              rows={4}
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
              placeholder="One workspace-reviewed preparation item per line"
            />
          </label>
          <button disabled={busy}>Save workspace policy</button>
        </form>
      ) : (
        <p>
          A workspace owner configures observation freshness, scan frequency and
          visit checklist templates.
        </p>
      )}
    </section>
  );
}

export function KnowledgeRelease({ me }: { me: Row }) {
  const [impact, setImpact] = useState<Row[] | null>(null),
    [error, setError] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  const load = useCallback(
    () =>
      api("/knowledge/impact")
        .then(setImpact)
        .catch((e) => setError(e.message)),
    [],
  );
  useEffect(() => {
    void load();
  }, [load]);
  return (
    <>
      <details className="panel">
        <summary>
          Procedure changes and reassessment ·{" "}
          {impact?.filter((i) => i.status === "pending").length || 0} pending
        </summary>
        <Messages error={error} message={message} />
        {impact === null ? (
          <p role="status">Loading change impact…</p>
        ) : impact.length === 0 ? (
          <p>No older cited procedure versions need review in open cases.</p>
        ) : (
          impact.map((i: Row) => (
            <Reassessment
              key={
                i.run_id +
                ":" +
                i.article_id +
                ":" +
                i.new_version +
                ":" +
                i.version
              }
              item={i}
              canReview={["owner", "reviewer"].includes(me.role)}
              busy={busy}
              onSave={async (body) => {
                setBusy(true);
                setError("");
                try {
                  await api(
                    `/runs/${i.run_id}/reassessment/${encodeURIComponent(i.article_id)}/${i.new_version}`,
                    body,
                  );
                  await load();
                  setMessage(
                    "Reassessment recorded. Historical approvals remain unchanged.",
                  );
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            />
          ))
        )}
        <button className="outline" onClick={load}>
          Refresh procedure impact
        </button>
      </details>
      {["owner", "reviewer"].includes(me.role) && (
        <EvaluationDashboard me={me} />
      )}
    </>
  );
}
function Reassessment({
  item: i,
  canReview,
  busy,
  onSave,
}: {
  item: Row;
  canReview: boolean;
  busy: boolean;
  onSave: (b: Row) => void;
}) {
  const [status, setStatus] = useState(
      i.status === "pending" ? "needed" : i.status,
    ),
    [notes, setNotes] = useState(i.rationale || "");
  return (
    <details>
      <summary>
        {i.case_title} · {i.procedure_title} v{i.old_version} → v{i.new_version}{" "}
        · {i.status.replaceAll("_", " ")}
      </summary>
      <p>{i.old_content_scope}</p>
      <pre>{i.diff || "No text difference in retained content."}</pre>
      <Link className="text-link" href={"/workspace/cases/" + i.case_id}>
        Open affected case
      </Link>
      {canReview && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            onSave({ expected_version: i.version, status, rationale: notes });
          }}
        >
          <label>
            Reassessment decision
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="needed">Reassessment needed</option>
              <option value="not_needed">Reassessment not needed</option>
            </select>
          </label>
          <label>
            Reassessment rationale
            <textarea
              required
              minLength={10}
              maxLength={2000}
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </label>
          <button disabled={busy}>Record reassessment</button>
        </form>
      )}
    </details>
  );
}
function EvaluationDashboard({ me }: { me: Row }) {
  const [data, setData] = useState<Row | null>(null),
    [mode, setMode] = useState(me.ai_mode || "procedure"),
    [suite, setSuite] = useState("investigation"),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [selected, setSelected] = useState(""),
    [judgment, setJudgment] = useState("");
  const load = useCallback(
    () =>
      api("/evaluations")
        .then(setData)
        .catch((e) => setError(e.message)),
    [],
  );
  useEffect(() => {
    void load();
  }, [load]);
  const running = data?.runs.some((r: Row) =>
    ["queued", "running"].includes(r.status),
  );
  useEffect(() => {
    if (!running) return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [running, load]);
  return (
    <details className="panel evaluation-dashboard">
      <summary>AI evaluation dashboard</summary>
      <Messages error={error} message="" />
      {!data ? (
        <p role="status">Loading evaluation dataset…</p>
      ) : (
        <>
          <p>{suite==="assessments"?data.assessment_dataset.label_provenance:data.dataset.description}</p>
          <small>
            Dataset {suite==="assessments"?data.assessment_dataset.version:data.dataset.version} · {suite==="assessments"?data.assessment_dataset.scenarios.length:data.dataset.scenarios.length}{" "}
            versioned scenarios
          </small>
          <div className="form-grid">
            <label>Evaluation suite<select value={suite} onChange={e=>{setSuite(e.target.value);if(e.target.value==="assessments")setMode("ollama")}}><option value="investigation">Existing investigation scenarios</option><option value="assessments">Connected assessments · independently labeled</option></select></label>
            <label>
              Evaluation mode
              <select value={mode} onChange={(e) => setMode(e.target.value)}>
                <option value="procedure" disabled={suite==="assessments"}>
                  Deterministic procedure matching
                </option>
                <option value="ollama">Configured local Ollama model</option>
              </select>
            </label>
          </div>
          <button
            disabled={busy || running}
            onClick={async () => {
              setBusy(true);
              setError("");
              try {
                await api("/evaluations", { id: crypto.randomUUID(), mode, suite });
                await load();
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            {running
              ? "Evaluation queued or running…"
              : "Run isolated scenario evaluation"}
          </button>
          {data.runs.length === 0 && <p>No evaluation results yet.</p>}
          {data.runs.map((r: Row) => (
            <details key={r.id}>
              <summary>
                {stamp(r.created_at)} · {r.model} · {r.status || "unknown"}
              </summary>
              <small>
                {r.dataset_version} · mode {r.configuration.mode}
              </small>
              {r.error && <p className="error">{r.error}</p>}
              {r.status === "failed" && (
                <button
                  className="outline"
                  disabled={busy}
                  onClick={async () => {
                    try {
                      await api("/evaluations/" + r.id + "/retry", {});
                      await load();
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                >
                  Retry evaluation
                </button>
              )}
              {r.results && (
                <>
                  <div className="measured-metrics">
                    {Object.entries(r.results.counts).map(([label, value]) => (
                      <div key={label}>
                        <small>{label.replaceAll("_", " ")}</small>
                        <strong>{String(value)}</strong>
                      </div>
                    ))}
                  </div>
                  {r.configuration.suite==="assessments"?<><p>{r.results.ground_truth_provenance}</p><p>{r.results.security_tests}</p><details><summary>Per-case labels, linkage and question results</summary><pre>{JSON.stringify(r.results.scenarios,null,2)}</pre></details></>:<div
                    className="data-table-wrap"
                    tabIndex={0}
                    role="region"
                    aria-label="Evaluation scenario results"
                  >
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Scenario</th>
                          <th>Actual status</th>
                          <th>Citations</th>
                          <th>Escalation rule</th>
                          <th>Flags</th>
                          <th>Latency</th>
                          <th>Failure</th>
                        </tr>
                      </thead>
                      <tbody>
                        {r.results.scenarios.map((s: Row) => (
                          <tr key={s.scenario_id}>
                            <td>{s.scenario_id}</td>
                            <td>{s.actual_status || "Not produced"}</td>
                            <td>{s.citation_validity ? "Valid" : "Failed"}</td>
                            <td>
                              {s.escalation_rule_correct ? "Passed" : "Failed"}
                            </td>
                            <td>{s.flag_correct ? "Passed" : "Failed"}</td>
                            <td>{s.latency_seconds}s</td>
                            <td>{s.execution_failure || "None"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>}
                  <details>
                    <summary>Configuration and exact recorded results</summary>
                    <pre>{JSON.stringify(r.results, null, 2)}</pre>
                  </details>
                  <p>Subjective judgment: {r.judgment || "Not recorded"}</p>
                  <button
                    className="outline"
                    onClick={() => {
                      setSelected(r.id);
                      setJudgment(r.judgment || "");
                    }}
                  >
                    Add human evaluation judgment
                  </button>
                </>
              )}
            </details>
          ))}
          {selected && (
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                setBusy(true);
                try {
                  await api("/evaluations/" + selected + "/judgment", {
                    notes: judgment,
                  });
                  await load();
                  setSelected("");
                } catch (err) {
                  setError((err as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              <label>
                Subjective evaluation judgment
                <textarea
                  required
                  minLength={10}
                  maxLength={2000}
                  value={judgment}
                  onChange={(e) => setJudgment(e.target.value)}
                />
              </label>
              <button disabled={busy}>Record human judgment</button>
            </form>
          )}
          <button className="outline" onClick={load}>
            Refresh evaluations
          </button>
        </>
      )}
    </details>
  );
}

export function RecordsRelease({ me }: { me: Row }) {
  const [format, setFormat] = useState("json"),
    [content, setContent] = useState(""),
    [mapping, setMapping] = useState("{}"),
    [preview, setPreview] = useState<Row | null>(null),
    [history, setHistory] = useState<Row[]>([]),
    [error, setError] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false),
    [confirmed, setConfirmed] = useState(false);
  const load = useCallback(
    () =>
      api("/operations/history")
        .then(setHistory)
        .catch((e) => setError(e.message)),
    [],
  );
  useEffect(() => {
    void load();
  }, [load]);
  async function validate() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      setPreview(
        await api("/operations/import-preview", {
          format,
          content,
          mapping: JSON.parse(mapping),
        }),
      );
      setConfirmed(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <details className="panel">
        <summary>
          Immutable observation history · {history.length} snapshots
        </summary>
        <Messages error={error} message={message} />
        {history.length === 0 ? (
          <p>No retained observations.</p>
        ) : (
          history.map((s) => (
            <p key={s.id}>
              <strong>
                {s.study_id} / {s.site_id}
              </strong>{" "}
              · {stamp(s.observed_at)}
              <small> {s.external_id}</small>
            </p>
          ))
        )}
        <p>
          Compare observations in a case's Evidence & follow-up section. Saved
          investigation evidence remains frozen.
        </p>
      </details>
      {me.role === "owner" && (
        <details className="panel bulk-import">
          <summary>Preview CSV/JSON record import</summary>
          <Messages error={error} message={message} />
          <label>
            Import format
            <select
              value={format}
              onChange={(e) => {
                setFormat(e.target.value);
                setPreview(null);
              }}
            >
              <option value="json">Generic JSON rows</option>
              <option value="csv">Generic CSV rows</option>
            </select>
          </label>
          <div className="actions">
            <button
              className="outline"
              disabled={busy}
              onClick={async () => {
                try {
                  const d = await api(
                    "/operations/import-example?format=" + format,
                  );
                  setContent(d.content);
                  setPreview(null);
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            >
              Load generic import example
            </button>
            <label className="file-choice">
              Choose CSV or JSON
              <input
                type="file"
                accept=".csv,.json"
                onChange={async (e) => {
                  const f = e.target.files?.[0];
                  if (!f) return;
                  if (f.size > 100000) {
                    setError("Use a file no larger than 100 KB.");
                    return;
                  }
                  try {
                    setContent(await f.text());
                    setFormat(
                      f.name.toLowerCase().endsWith(".csv") ? "csv" : "json",
                    );
                    setPreview(null);
                  } catch {
                    setError("File could not be read.");
                  }
                }}
              />
            </label>
          </div>
          <label>
            Import rows
            <textarea
              className="code-editor"
              rows={8}
              value={content}
              maxLength={100000}
              onChange={(e) => {
                setContent(e.target.value);
                setPreview(null);
              }}
            />
          </label>
          <details>
            <summary>Field mapping and generic format</summary>
            <p>
              Map your input column names to the generic field names. This
              imports synthetic records; no vendor connection is implied.
            </p>
            <label>
              Field mapping JSON
              <textarea
                rows={3}
                value={mapping}
                onChange={(e) => {
                  setMapping(e.target.value);
                  setPreview(null);
                }}
                placeholder={'{"Study":"study_id","Site":"site_id"}'}
              />
            </label>
            <p>
              Every row includes study_id, site_id, snapshot_id, observed_at
              (with timezone), synthetic=true, kind and stable id.
              Synchronization rows include status, binder IDs and
              last_attempt_at. Document rows include document_id, document_type,
              upload_receipt_id, uploaded_at, status_since, processing_status,
              assigned_study_id and binder_visible. Use the example for optional
              timestamp fields.
            </p>
          </details>
          <button disabled={busy || !content.trim()} onClick={validate}>
            {busy ? "Validating preview…" : "Validate import preview"}
          </button>
          {preview && (
            <div>
              <p>{preview.message}</p>
              <h3>
                {preview.accepted.length} accepted rows ·{" "}
                {preview.rejected.length} rejected rows
              </h3>
              <details>
                <summary>Accepted rows</summary>
                {preview.accepted.map((r: Row) => (
                  <p key={r.row}>
                    Row {r.row} · {r.study_id}/{r.site_id} · {r.kind} ·{" "}
                    {r.record_id}
                  </p>
                ))}
              </details>
              <details open={preview.rejected.length > 0}>
                <summary>Rejected rows</summary>
                {preview.rejected.map((r: Row) => (
                  <p key={r.row}>
                    Row {r.row} · {r.reason}
                  </p>
                ))}
              </details>
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(e) => setConfirmed(e.target.checked)}
                />
                <span>
                  I reviewed the accepted and rejected rows. Commit accepted
                  snapshots only.
                </span>
              </label>
              <button
                disabled={busy || !confirmed || !preview.accepted.length}
                onClick={async () => {
                  setBusy(true);
                  setError("");
                  try {
                    const d = await api(
                      "/operations/import-preview/" + preview.id + "/commit",
                      { confirmed: true },
                    );
                    await load();
                    setMessage(
                      d.status === "already_committed"
                        ? "This preview was already committed; no duplicates added."
                        : "Accepted snapshots imported. Original observations preserved.",
                    );
                    setPreview(null);
                  } catch (e) {
                    setError((e as Error).message);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Commit accepted snapshots
              </button>
            </div>
          )}
        </details>
      )}
      <MonitoringVisits me={me} />
    </>
  );
}

function MonitoringVisits({ me }: { me: Row }) {
  const [visits, setVisits] = useState<Row[]>([]),
    [catalog, setCatalog] = useState<Row>({ studies: [], sites: [] }),
    [study, setStudy] = useState(""),
    [site, setSite] = useState(""),
    [date, setDate] = useState(""),
    [title, setTitle] = useState(""),
    [selected, setSelected] = useState<Row | null>(null),
    [newText, setNewText] = useState(""),
    [error, setError] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false),
    [visitId, setVisitId] = useState("");
  const canReview = ["owner", "reviewer"].includes(me.role);
  const load = useCallback(async () => {
    const [v, c] = await Promise.all([api("/visits"), api("/catalog")]);
    setVisits(v);
    setCatalog(c);
  }, []);
  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, [load]);
  async function open(id: string) {
    try {
      setSelected(await api("/visits/" + id));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function changeItem(index: number, key: string, value: string) {
    if (selected)
      setSelected({
        ...selected,
        visit: {
          ...selected.visit,
          checklist: selected.visit.checklist.map((i: Row, n: number) =>
            n === index ? { ...i, [key]: value } : i,
          ),
        },
      });
  }
  return (
    <details className="panel monitoring-visits">
      <summary>Monitoring-visit preparation</summary>
      <Messages error={error} message={message} />
      {canReview && (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            const id = visitId || crypto.randomUUID();
            setVisitId(id);
            try {
              const v = await api("/visits", {
                id,
                study_id: study,
                site_id: site,
                visit_at: iso(date),
                title,
              });
              await load();
              await open(v.id);
              setMessage("Dated preparation view created.");
              setTitle("");
              setVisitId("");
            } catch (err) {
              setError((err as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <h3>Create a dated preparation view</h3>
          <label>
            Preparation title
            <input
              required
              minLength={5}
              maxLength={200}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          <div className="form-grid">
            <label>
              Visit study
              <select
                required
                value={study}
                onChange={(e) => {
                  setStudy(e.target.value);
                  setSite("");
                }}
              >
                <option value="">Choose study</option>
                {catalog.studies.map((s: Row) => (
                  <option key={s.id} value={s.id}>
                    {s.id} · {s.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Visit site
              <select
                required
                value={site}
                onChange={(e) => setSite(e.target.value)}
              >
                <option value="">Choose site</option>
                {catalog.sites
                  .filter((s: Row) => s.study_id === study)
                  .map((s: Row) => (
                    <option key={s.id} value={s.id}>
                      {s.id} · {s.name}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Visit date
              <input
                required
                type="datetime-local"
                step="1"
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
            </label>
          </div>
          <button disabled={busy}>Create preparation view</button>
        </form>
      )}
      {visits.length === 0 && (
        <p>
          No monitoring visits. A reviewer can create a dated study/site view.
        </p>
      )}
      {visits.map((v) => (
        <div className="work-row" key={v.id}>
          <div>
            <strong>{v.title}</strong>
            <small>
              {v.study_id}/{v.site_id} · {stamp(v.visit_at)}
            </small>
          </div>
          <button className="outline" onClick={() => open(v.id)}>
            Open preparation
          </button>
        </div>
      ))}
      {selected && (
        <section>
          <h3>{selected.visit.title}</h3>
          <p>
            {stamp(selected.visit.visit_at)} · {selected.interpretation}
          </p>
          <a
            className="button outline"
            href={"/api/visits/" + selected.visit.id + "/export.txt"}
            download
          >
            Export preparation summary
          </a>
          <h3>Open issues and owners</h3>
          {selected.open_cases.map((c: Row) => (
            <p key={c.id}>
              <Link className="text-link" href={"/workspace/cases/" + c.id}>
                {c.title}
              </Link>{" "}
              · {c.owner_name || "Unassigned"} · due{" "}
              {c.due_at ? stamp(c.due_at) : "Not set"}
            </p>
          ))}
          <h3>Incomplete investigation checks</h3>
          {selected.checks.flatMap((c: Row) =>
            c.items
              .filter(
                (i: Row) => !["verified", "not_applicable"].includes(i.state),
              )
              .map((i: Row) => (
                <p key={i.id}>
                  {i.text} · {i.state.replaceAll("_", " ")} · deadline{" "}
                  {c.due_at ? stamp(c.due_at) : "Not set"}
                </p>
              )),
          )}
          <h3>Missing information</h3>
          {selected.requests.map((r: Row) => (
            <p key={r.id}>
              {r.title} · {r.effective_status} · {r.owner_name || "Unassigned"}{" "}
              · due {r.due_at ? stamp(r.due_at) : "Not set"}
            </p>
          ))}
          <h3>Visit checklist</h3>
          {selected.visit.checklist.length === 0 && (
            <p>
              No configured visit checks. Add human-reviewed preparation items
              below.
            </p>
          )}
          {selected.visit.checklist.map((i: Row, n: number) => (
            <article className="check-item" key={i.id}>
              <p>{i.text}</p>
              <div className="form-grid">
                <label>
                  Preparation check state
                  <select
                    disabled={!canReview}
                    value={i.state}
                    onChange={(e) => changeItem(n, "state", e.target.value)}
                  >
                    {[
                      "not_checked",
                      "verified",
                      "needs_follow_up",
                      "not_applicable",
                    ].map((s) => (
                      <option key={s} value={s}>
                        {s.replaceAll("_", " ")}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Preparation check notes
                  <textarea
                    disabled={!canReview}
                    value={i.notes}
                    onChange={(e) => changeItem(n, "notes", e.target.value)}
                  />
                </label>
              </div>
            </article>
          ))}
          {canReview && (
            <>
              <label>
                Add a preparation check
                <input
                  value={newText}
                  maxLength={2000}
                  onChange={(e) => setNewText(e.target.value)}
                />
              </label>
              <button
                className="outline"
                disabled={!newText.trim()}
                onClick={() => {
                  setSelected({
                    ...selected,
                    visit: {
                      ...selected.visit,
                      checklist: [
                        ...selected.visit.checklist,
                        {
                          id: crypto.randomUUID(),
                          text: newText,
                          state: "not_checked",
                          notes: "",
                        },
                      ],
                    },
                  });
                  setNewText("");
                }}
              >
                Add visit check
              </button>
              <label>
                Preparation visit date
                <input
                  type="datetime-local"
                  step="1"
                  value={local(selected.visit.visit_at)}
                  onChange={(e) =>
                    setSelected({
                      ...selected,
                      visit: {
                        ...selected.visit,
                        visit_at: iso(e.target.value),
                      },
                    })
                  }
                />
              </label>
              <button
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  try {
                    const clean = selected.visit.checklist.map((i: Row) => ({
                      id: i.id,
                      text: i.text,
                      state: i.state,
                      notes: i.notes,
                    }));
                    await api("/visits/" + selected.visit.id, {
                      expected_version: selected.visit.version,
                      visit_at: selected.visit.visit_at,
                      checklist: clean,
                    });
                    await open(selected.visit.id);
                    await load();
                    setMessage("Preparation checklist saved.");
                  } catch (e) {
                    setError((e as Error).message);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Save preparation checklist
              </button>
            </>
          )}
        </section>
      )}
    </details>
  );
}
