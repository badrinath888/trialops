"use client";
import {MyWork,NextStep,ResponsePolicy} from "../../user-workflow-panels";
import {WaitingQueue,SupportDirectory,EmailVerification} from "../../five-feature-panels";
import {AssessmentPanel} from "../../assessment-panel";
import {CaseWatch} from "../../case-watch";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { api, ApiError, categories, download, money, stamp } from "../../lib";
import { Icon } from "../../ui";
import JobProgress from "../../job-progress";
import CaseList from "../../case-list";
import {
  CasePreview,
  DataTable,
  usePreferences,
  readPreferences,
  savePreferences,
  DisplayPreferences,
} from "../../workspace-components";

import { CaseWorkflows, EvidenceResolution } from "../../evidence-workflows";
import {
  OverviewRelease,
  KnowledgeRelease,
  RecordsRelease,
  WorkspacePolicies,
} from "../../release-panels";

type Row = Record<string, any>;
function Badge({ value }: { value: string }) {
  return <span className={"badge " + value}>{value.replaceAll("_", " ")}</span>;
}
function Empty({
  title,
  children,
}: {
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <Icon name="folder" size={30} />
      <h3>{title}</h3>
      {children}
    </div>
  );
}
function ErrorBox({ error }: { error: string }) {
  return error ? (
    <p role="alert" className="error">
      {error}
    </p>
  ) : null;
}
function FieldCategory({
  value,
  onChange,
  disabled = false,
}: {
  value: string;
  onChange: (s: string) => void;
  disabled?: boolean;
}) {
  return (
    <select
      aria-label="Category"
      disabled={disabled}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      {categories.map(([v, l]) => (
        <option key={v} value={v}>
          {l}
        </option>
      ))}
    </select>
  );
}
function Heading({
  label,
  title,
  description,
  children,
}: {
  label: string;
  title: string;
  description?: string;
  children?: React.ReactNode;
}) {
  return (
    <header className="view-heading">
      <div>
        <p className="eyebrow">{label}</p>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {children}
    </header>
  );
}
const navigation = [
  ["/workspace", "Overview", "grid"],
  ["/workspace/cases", "Cases", "folder"],
  ["/workspace/new", "Submit issue", "plus"],
  ["/workspace/knowledge", "Knowledge", "file"],
  ["/workspace/history", "Investigations", "history"],
  ["/workspace/operations", "Operational records", "shield"],
  ["/workspace/roi", "ROI scenarios", "chart"],
  ["/workspace/feedback", "Feedback", "spark"],
  ["/workspace/settings", "Settings", "grid"],
];
export default function Workspace() {
  const path = usePathname() || "/workspace",
    router = useRouter();
  const [me, setMe] = useState<Row | null>(null),
    [error, setError] = useState(""),
    [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const lastPath = useRef(path);
  useEffect(() => {
    if (lastPath.current !== path) {
      lastPath.current = path;
      document.getElementById("main-content")?.focus({ preventScroll: true });
    }
  }, [path]);
  useEffect(() => {
    api("/auth/me")
      .then(setMe)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401)
          router.replace("/sign-in");
        else setError(e.message);
      });
  }, [router]);
  const preferences = usePreferences(me?.user_id);
  const parts = path.split("/").filter(Boolean).slice(1);
  const view = parts[0] || "overview",
    id = parts[1] ? decodeURIComponent(parts[1]) : "";
  async function logout() {
    try {
      await api("/auth/logout", {});
      window.location.assign("/");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  if (!me)
    return (
      <main id="main-content" className="auth-page">
        <Link href="/" className="wordmark">
          TrialOps<span>✳</span>
        </Link>
        <h1>Opening your workspace.</h1>
        <ErrorBox error={error} />
        {error && (
          <button onClick={() => window.location.reload()}>Try again</button>
        )}
      </main>
    );
  return (
    <div className={"app-shell density-" + preferences.density}>
      <aside className="sidebar">
        <Link href="/" className="wordmark">
          TrialOps<span>✳</span>
        </Link>
        <div className="workspace-label workspace-header-compact">
          <strong>{me.workspace_name}</strong>
          <small>
            {me.demo ? "Sample workspace · " : ""}
            {me.role === "owner"
              ? "Workspace admin"
              : me.role === "reviewer"
                ? "Reviewer"
                : "Analyst"}
          </small>
        </div>
        <button
          ref={menuButton}
          className="mobile-menu-toggle outline"
          aria-controls="workspace-navigation"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen(!menuOpen)}
        >
          Menu <Icon name="grid" size={14} />
        </button>
        <nav
          id="workspace-navigation"
          className={menuOpen ? "expanded" : ""}
          aria-label="Workspace navigation"
          onKeyDown={(event) => {
            if (event.key === "Escape" && menuOpen) {
              setMenuOpen(false);
              menuButton.current?.focus();
            }
          }}
        >
          {navigation.map(([href, label, icon]) => (
            <Link
              key={href}
              href={href}
              onClick={() => setMenuOpen(false)}
              aria-current={
                (href === "/workspace" ? path === href : path.startsWith(href))
                  ? "page"
                  : undefined
              }
              className={
                (href === "/workspace" ? path === href : path.startsWith(href))
                  ? "active"
                  : ""
              }
            >
              <Icon name={icon} size={18} />
              {label}
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <Link href="/guide">
            <Icon name="file" size={16} />
            Product guide
          </Link>
          <button className="outline" onClick={logout}>
            Sign out
          </button>
          <div className="user-identity">
            <span className="avatar" aria-hidden="true">
              {me.name
                .split(/\s+/)
                .slice(0, 2)
                .map((n: string) => n[0])
                .join("")
                .toUpperCase()}
            </span>
            <span>{me.name}</span>
          </div>
        </div>
      </aside>
      <div className="app-main">
        <div className="app-topbar">
          <div className="mobile-actions">
            <Link href="/workspace/settings">Settings</Link>
            <button className="outline" onClick={logout}>
              Sign out
            </button>
          </div>
        </div>
        {me.demo && (
          <div className="sample-banner">
            Sample workspace · expires after 24 hours.{" "}
            <Link href="/sign-in?mode=register">
              Create a permanent account →
            </Link>
          </div>
        )}
        <main id="main-content" tabIndex={-1} className="app-content">
          <ErrorBox error={error} />
          {view === "overview" ? (
            <>
              <Overview me={me} />
              <OverviewRelease me={me} />
              <WaitingQueue />
            </>
          ) : view === "new" ? (
            <Intake />
          ) : view === "cases" && id ? (
            <CaseDetail key={id} id={id} me={me} />
          ) : view === "cases" ? (
            <CaseList me={me} />
          ) : view === "runs" && id ? (
            <>
              <Link href="/workspace/history" className="text-link">
                ← All investigations
              </Link>
              <RunView key={id} id={id} me={me} />
            </>
          ) : view === "history" ? (
            <HistoryList />
          ) : view === "knowledge" ? (
            <>
              <Knowledge me={me} />
              <KnowledgeRelease me={me} />
            </>
          ) : view === "operations" ? (
            <>
              <Operations me={me} />
              <RecordsRelease me={me} />
            </>
          ) : view === "roi" ? (
            <ROI me={me} />
          ) : view === "feedback" ? (
            <Feedback me={me} />
          ) : view === "settings" ? (
            <><Settings me={me} /><EmailVerification me={me}/><ResponsePolicy me={me}/><SupportDirectory me={me}/></>
          ) : (
            <Empty title="Page not found">
              <Link href="/workspace">Return to overview</Link>
            </Empty>
          )}
        </main>
        <footer className="app-footer">
          TrialOps · <Link href="/guide">Guide & data policy</Link>
        </footer>
      </div>
    </div>
  );
}
function Overview({ me }: { me: Row }) {
  const [data, setData] = useState<Row | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    api("/dashboard")
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);
  const [queue, setQueue] = useState("reviews"),
    [preview, setPreview] = useState("");
  const group = data?.attention?.[queue];
  return (
    <>
      <Heading
        label="OPERATIONS OVERVIEW"
        title="Workspace overview"
        description={`Welcome, ${me.name}. Review what needs attention.`}
      >
        <Link className="button" href="/workspace/new">
          <Icon name="plus" size={17} />
          Submit an issue
        </Link>
      </Heading>
      <ErrorBox error={error} />
      <div className="overview-metrics">
        {([
          ["Open cases", data?.open_cases, "", "View", false],
          ["Awaiting review", data?.attention?.reviews?.total, "?view=review", "Review", true],
          ["Overdue", data?.attention?.overdue?.total, "?view=overdue", "View", true],
        ] as [string, number | undefined, string, string, boolean][]).map(([label, value, query, cta, urgent]) => {
          const body = <><span>{label}</span><strong>{value ?? "—"}</strong></>;
          if (!value) return <div key={label} className="metric quiet">{body}<em>{value === 0 ? "None" : ""}</em></div>;
          return <Link key={label} className={"metric" + (urgent ? " urgent" : "")} href={"/workspace/cases" + query}>{body}<em>{cta} →</em></Link>;
        })}
      </div>
      <MyWork />
      <section className="panel attention-section" aria-label="Attention queue">
        <div className="section-heading">
          <h2>Needs your attention</h2>
          <Link
            className="text-link"
            href={
              "/workspace/cases?view=" +
              (queue === "reviews" ? "review" : queue)
            }
          >
            View all →
          </Link>
        </div>
        <div className="tabs" aria-label="Attention categories">
          {[
            ["reviews", "Review"],
            ["unassigned", "High priority · unassigned"],
            ["overdue", "Overdue"],
          ].map(([key, label]) => (
            <button
              key={key}
              className={queue === key ? "active" : ""}
              aria-pressed={queue === key}
              onClick={() => setQueue(key)}
            >
              {label} · {data?.attention?.[key]?.total ?? "—"}
            </button>
          ))}
        </div>
        {!group ? (
          <p role="status">Loading attention queue…</p>
        ) : !group.items.length ? (
          <p className="queue-empty">
            <Icon name="check" size={18} />
            Nothing waiting here.
          </p>
        ) : (
          group.items.map((item: Row) => (
            <div className="work-row" key={item.id}>
              <div>
                <strong>{item.title}</strong>
                <small>
                  {item.case_id || item.id}
                  {item.due_at ? " · Due " + stamp(item.due_at) : ""}
                </small>
              </div>
              <Link
                className={queue === "reviews" ? "button" : "button outline"}
                href={
                  queue === "reviews"
                    ? "/workspace/runs/" + item.id
                    : "/workspace/cases/" + item.id
                }
              >
                {queue === "reviews" ? "Review findings" : "Open case"}
              </Link>
            </div>
          ))
        )}
        {group?.total > 5 && (
          <small>
            Showing the first 5 of {group.total}. Open the full view for all
            results.
          </small>
        )}
      </section>
      <section className="panel">
        <div className="section-heading">
          <h2>Recently updated</h2>
          <Link className="text-link" href="/workspace/cases">
            All cases →
          </Link>
        </div>
        {!data ? (
          <p role="status">Loading recent cases…</p>
        ) : !data.recent_cases?.length ? (
          <p>No cases yet. Submit an issue to get started.</p>
        ) : (
          data.recent_cases.map((c: Row) => (
            <div className="work-row" key={c.id}>
              <div>
                <Link className="case-title" href={"/workspace/cases/" + c.id}>
                  <strong>{c.title}</strong>
                </Link>
                <div className="case-row-meta">
                  <span className="case-id-chip">{c.id}</span>
                  <small>
                    {c.status} · {c.priority} priority
                  </small>
                </div>
              </div>
              <button
                className="outline"
                aria-label={"Preview " + c.id}
                onClick={() => setPreview(c.id)}
              >
                Preview
              </button>
            </div>
          ))
        )}
      </section>
      {me.demo && (
        <details className="sample-scenarios">
          <summary>Explore sample scenarios</summary>
          <div className="sample-links">
            {[
              ["CASE-1", "Missing certificate"],
              ["CASE-4", "Stalled synchronization"],
              ["CASE-6", "Healthy status check"],
              ["CASE-7", "Unsupported request"],
            ].map(([id, label]) => (
              <Link key={id} href={"/workspace/cases/" + id}>
                {label} →
              </Link>
            ))}
          </div>
        </details>
      )}
      {preview && (
        <CasePreview caseId={preview} onClose={() => setPreview("")} />
      )}
      <div className="getting-started">
        <Icon name="file" size={20} />
        <span>Need a walkthrough? The guide explains each step.</span>
        <Link className="text-link" href="/guide">
          Open guide →
        </Link>
      </div>
    </>
  );
}
function Intake() {
  const submission = useRef<string | null>(null);
  const router = useRouter(),
    [catalog, setCatalog] = useState<Row>({ studies: [], sites: [] }),
    [title, setTitle] = useState(""),
    [description, setDescription] = useState(""),
    [study, setStudy] = useState(""),
    [site, setSite] = useState(""),
    [category, setCategory] = useState("unknown"),
    [priority, setPriority] = useState("medium"),
    [suggestion, setSuggestion] = useState<Row | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    api("/catalog")
      .then(setCatalog)
      .catch((e) => setError(e.message));
  }, []);
  async function suggest() {
    setBusy(true);
    setError("");
    try {
      setSuggestion(await api("/intake/classify", { title, description }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (!submission.current) submission.current = crypto.randomUUID();
      const c = await api("/cases", {
        submission_id: submission.current,
        title,
        description,
        study_id: study,
        site_id: site,
        category,
        priority,
      });
      router.push("/workspace/cases/" + c.id);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }
  return (
    <>
      <Heading
        label="OPERATIONS INTAKE"
        title="Submit an issue"
        description="Tell us what happened."
      />
      <div className="editor-layout intake-layout">
        <form className="panel form-panel" onSubmit={submit}>
          <ErrorBox error={error} />
          <p className="subtle">Use non-patient operational details.</p>
          <h2>
            <span className="step-num">01</span>What happened?
          </h2>
          <label>
            Issue title
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              minLength={5}
              maxLength={200}
              required
              placeholder="For example: Uploaded certificate missing from binder"
            />
          </label>
          <label>
            Describe the issue
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              minLength={10}
              maxLength={4000}
              rows={5}
              required
              placeholder="What did you expect, what happened, and what work is affected?"
            />
          </label>
          <button
            className="outline"
            type="button"
            disabled={
              busy || title.trim().length < 5 || description.trim().length < 10
            }
            onClick={suggest}
          >
            Suggest classification
          </button>
          {suggestion && (
            <div className="suggestion">
              <strong>
                Suggested:{" "}
                {categories.find((x) => x[0] === suggestion.category)?.[1]} ·{" "}
                {suggestion.priority}
              </strong>
              <p>{suggestion.rationale}</p>
              <button
                type="button"
                className="outline"
                onClick={() => {
                  setCategory(suggestion.category);
                  setPriority(suggestion.priority);
                }}
              >
                Use suggestion
              </button>
              <small>
                Keyword-assisted suggestion. You choose the final values.
              </small>
            </div>
          )}
          <h2>
            <span className="step-num">02</span>Study & site
          </h2>
          <div className="form-grid">
            <label>
              Study
              <select
                value={study}
                onChange={(e) => {
                  setStudy(e.target.value);
                  setSite("");
                }}
                required
              >
                <option value="">Select a study</option>
                {catalog.studies.map((s: Row) => (
                  <option key={s.id} value={s.id}>
                    {s.id} · {s.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Research site
              <select
                value={site}
                onChange={(e) => setSite(e.target.value)}
                required
                disabled={!study}
              >
                <option value="">Select a site</option>
                {catalog.sites
                  .filter((s: Row) => s.study_id === study)
                  .map((s: Row) => (
                    <option key={s.id} value={s.id}>
                      {s.id} · {s.name}
                    </option>
                  ))}
              </select>
            </label>
          </div>
          <h2>
            <span className="step-num">03</span>Category & priority
          </h2>
          <div className="form-grid">
            <label>
              Category
              <FieldCategory value={category} onChange={setCategory} />
            </label>
            <label>
              Priority
              <select
                aria-label="Priority"
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
              >
                {["low", "medium", "high"].map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>
            </label>
          </div>
          <button disabled={busy || !study || !site}>
            {busy ? "Saving…" : "Create case"} <Icon name="arrow" size={17} />
          </button>
        </form>
      </div>
    </>
  );
}
function CaseDetail({ id, me }: { id: string; me: Row }) {
  const [workflowRefresh, setWorkflowRefresh] = useState(0);
  const [data, setData] = useState<Row | null>(null),
    [members, setMembers] = useState<Row[]>([]),
    [runId, setRunId] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [note, setNote] = useState(""),
    [resolution, setResolution] = useState(""),
    [owner, setOwner] = useState(""),
    [due, setDue] = useState(""),
    [message, setMessage] = useState("");
  const load = useCallback(async () => {
    const d = await api("/cases/" + encodeURIComponent(id));
    setData(d);
    setRunId((current) => current || d.runs[0]?.id || "");
    return d;
  }, [id]);
  useEffect(() => {
    let active = true;
    Promise.all([api("/cases/" + encodeURIComponent(id)), api("/members")])
      .then(([d, m]) => {
        if (!active) return;
        setData(d);
        setMembers(m);
        setRunId(d.runs[0]?.id || "");
        setOwner(d.case.owner_id || "");
        if (d.case.due_at) {
          const dt = new Date(d.case.due_at);
          setDue(
            new Date(dt.getTime() - dt.getTimezoneOffset() * 60000)
              .toISOString()
              .slice(0, 16),
          );
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [id]);
  const running = data?.job && ["queued", "running"].includes(data.job.status);
  useEffect(() => {
    if (!running) return;
    let active = true;
    const timer = setInterval(
      () =>
        api("/cases/" + encodeURIComponent(id))
          .then((d) => {
            if (!active) return;
            setData(d);
            if (d.job?.status === "completed" && d.job.result_id)
              setRunId(d.job.result_id);
          })
          .catch((e) => {
            if (active) setError(e.message);
          }),
      2000,
    );
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [running, id]);
  async function action(path: string, body: Row, success: string) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await api("/cases/" + encodeURIComponent(id) + path, body);
      await load();
      setMessage(success);
      setNote("");
      setResolution("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function investigate() {
    setBusy(true);
    setError("");
    try {
      await api("/cases/" + encodeURIComponent(id) + "/investigate", {});
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (!data)
    return (
      <>
        <ErrorBox error={error} />
        <Empty title={error ? "Case could not be loaded." : "Opening case…"}>
          <Link href="/workspace/cases">Return to cases</Link>
        </Empty>
      </>
    );
  const c = data.case,
    canReview = ["owner", "reviewer"].includes(me.role),
    approvedRuns = data.runs.filter((r: Row) => r.decision === "approved");
  return (
    <>
      <Link href="/workspace/cases" className="text-link">
        ← Operations inbox
      </Link>
      <Heading label={c.id} title={c.title} description={c.description}>
        <Badge value={c.status} />
      </Heading>
      <div className="context-line">
        <span>{c.study_id}</span>
        <span>{c.site_id}</span>
        <Badge value={c.priority} />
        <span>{c.owner_name || "Unassigned"}</span>
      </div>
      <ErrorBox error={error} />
      {message && (
        <p className="success" role="status">
          {message}
        </p>
      )}
      <NextStep item={c} onInvestigate={investigate} refreshKey={String(data.job?.status)+String(data.runs.length)+String(c.updated_at)}/>
      <CaseWatch cid={c.id} refreshKey={String(workflowRefresh)}/>
      <div id="case-investigate" className="case-actions panel">
        <div>
          <h3>Investigate this issue</h3>
          <p>
            Find procedures and saved site records. You can leave while it runs.
          </p>
        </div>
        <button
          onClick={investigate}
          aria-busy={Boolean(busy || running)}
          disabled={busy || running || c.status !== "open"}
        >
          <Icon name="spark" size={17} />
          {running
            ? "Investigation in progress…"
            : c.status === "resolved"
              ? "Reopen to investigate"
              : "Run investigation"}
        </button>
      </div>
      {running && (
        <JobProgress status={data.job.status} createdAt={data.job.created_at} />
      )}
      {data.job?.status === "failed" && (
        <p className="error" role="alert">
          {data.job.error} Use Run investigation to retry.
        </p>
      )}
      <div className="detail-grid">
        <section id="case-findings" tabIndex={-1}>
          {data.runs.length > 0 && (
            <label className="run-selector">
              Saved investigation
              <select value={runId} onChange={(e) => setRunId(e.target.value)}>
                {data.runs.map((r: Row) => (
                  <option key={r.id} value={r.id}>
                    {stamp(r.created_at)} · {r.decision || "pending"} ·{" "}
                    {r.id.slice(0, 8)}
                  </option>
                ))}
              </select>
            </label>
          )}
          {runId ? (
            <RunView key={runId} id={runId} me={me} embedded onChanged={load} />
          ) : (
            <div className="panel">
              <Empty title="The investigation starts here.">
                <p>
                  Run an investigation to see sources, recorded conditions, and
                  a recommendation for review.
                </p>
              </Empty>
            </div>
          )}
          <CaseWorkflows
            item={c}
            runId={runId}
            me={me}
            refreshKey={workflowRefresh}
            onChanged={() => {
              setWorkflowRefresh((n) => n + 1);
              void load();
            }}
          />
          <section id="case-resolution" tabIndex={-1} className="panel resolution-panel">
            <div className="section-heading">
              <h2>Case status</h2>
              <Badge value={c.status} />
            </div>
            <p>
              Close the case only after completing current checks. Approval
              alone does not resolve it.
            </p>
            {c.resolution && (
              <div className="notice">
                <h3>Recorded resolution</h3>
                <p>{c.resolution}</p>
                <small>{c.resolved_at && stamp(c.resolved_at)}</small>
              </div>
            )}
            {!canReview ? (
              <p className="notice">
                A reviewer or owner must resolve or reopen this case.
              </p>
            ) : c.status === "open" && !approvedRuns.length ? (
              <p className="notice">
                Approve a supported investigation for this case before recording
                resolution.
              </p>
            ) : c.status === "open" ? (
              <EvidenceResolution
                cid={id}
                updatedAt={c.updated_at}
                runs={approvedRuns}
                refreshKey={workflowRefresh}
                onResolved={() => {
                  void load();
                  setMessage("Case marked resolved.");
                }}
              />
            ) : (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void action(
                    "/reopen",
                    { notes: resolution },
                    "Case reopened; the original resolution remains in activity.",
                  );
                }}
              >
                <label>
                  Reason for reopening
                  <textarea
                    value={resolution}
                    onChange={(e) => setResolution(e.target.value)}
                    minLength={10}
                    maxLength={2000}
                    rows={3}
                    required
                  />
                </label>
                <button
                  disabled={busy || running || resolution.trim().length < 10}
                >
                  Reopen case
                </button>
              </form>
            )}
          </section>
        </section>
        <aside>
          <section className="panel">
            <h2>Owner & deadline</h2>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void action(
                  "/assignment",
                  {
                    expected_updated_at: c.updated_at,
                    owner_id: owner || null,
                    due_at: due ? new Date(due).toISOString() : null,
                  },
                  "Assignment saved.",
                );
              }}
            >
              <label>
                Case owner
                <select
                  aria-label="Case owner"
                  value={owner}
                  onChange={(e) => setOwner(e.target.value)}
                >
                  <option value="">Unassigned</option>
                  {members.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name} · {m.role}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Follow-up deadline
                <input
                  type="datetime-local"
                  value={due}
                  onChange={(e) => setDue(e.target.value)}
                />
              </label>
              <button className="outline" disabled={busy}>
                Save assignment
              </button>
            </form>
          </section>
          <details className="panel case-disclosure">
            <summary>Add a note</summary>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void action("/notes", { notes: note }, "Note saved.");
              }}
            >
              <label>
                Operational note
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  minLength={10}
                  maxLength={2000}
                  rows={3}
                  required
                />
              </label>
              <button
                className="outline"
                disabled={busy || note.trim().length < 10}
              >
                Save note
              </button>
            </form>
          </details>
          <details className="panel activity case-disclosure">
            <summary>Case activity</summary>
            {!data.events.length && <p className="subtle">No activity yet.</p>}
            {[...data.events].reverse().map((e: Row) => (
              <details key={e.id}>
                <summary>
                  <strong>{e.event_type.replaceAll("_", " ")}</strong>
                  <small>{stamp(e.created_at)}</small>
                </summary>
                <p>{e.actor_name}</p>
                {e.notes && <p className="preserve">{e.notes}</p>}
                {e.payload?.previous_resolution && (
                  <p>Previous resolution: {e.payload.previous_resolution}</p>
                )}
                {e.run_id && (
                  <Link href={"/workspace/runs/" + e.run_id}>
                    View investigation →
                  </Link>
                )}
              </details>
            ))}
          </details>
        </aside>
      </div>
    </>
  );
}
function RunView({
  id,
  me,
  embedded = false,
  onChanged,
}: {
  id: string;
  me: Row;
  embedded?: boolean;
  onChanged?: () => Promise<unknown>;
}) {
  const [run, setRun] = useState<Row | null>(null),
    [error, setError] = useState(""),
    [notes, setNotes] = useState(""),
    [busy, setBusy] = useState(false),
    [copied, setCopied] = useState(""),
    [tab, setTab] = useState("overview");
  const load = useCallback(async () => {
    const d = await api("/runs/" + id);
    setRun({ ...d.run, events: d.events });
  }, [id]);
  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, [load]);
  async function decide(value: string) {
    setBusy(true);
    setError("");
    try {
      await api("/runs/" + id + "/decision", { decision: value, notes });
      await load();
      await onChanged?.();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function downloadPdf() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/runs/" + id + "/report.pdf", {
        cache: "no-store",
      });
      if (
        !response.ok ||
        !response.headers.get("content-type")?.includes("application/pdf")
      ) {
        const data = await response.json().catch(() => ({}));
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "PDF download failed. Please try again.",
        );
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = "trialops-investigation-" + id.slice(0, 8) + ".pdf";
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function copy(d: Row) {
    try {
      await navigator.clipboard.writeText(d.subject + "\n\n" + d.body);
      setCopied(d.id);
    } catch {
      setError(
        "Copy is unavailable. Select the expanded draft text and copy it manually.",
      );
    }
  }
  if (!run)
    return (
      <div className="panel">
        <ErrorBox error={error} />
        <p role="status">Loading investigation…</p>
      </div>
    );
  const r = run.result,
    rec = r.recommendation,
    canReview = ["owner", "reviewer"].includes(me.role),
    cited = r.sources.filter((s: Row) => rec.evidence_ids.includes(s.id)),
    tabs = [
      ["overview", "Overview"],
      ["evidence", "Evidence"],
      ["records", "Records"],
      ["activity", "Activity"],
    ];
  return (
    <section
      className={"panel run-panel " + (!embedded ? "standalone-run" : "")}
    >
      <div className="section-heading">
        <div>
          <p className="eyebrow">SAVED INVESTIGATION</p>
          <h2>Investigation findings</h2>
        </div>
        <Badge value={run.decision || "pending"} />
      </div>
      <div className="run-toolbar">
        <span className="subtle">
          {stamp(run.created_at)} · {run.duration_seconds.toFixed(1)}s
        </span>
        <div className="actions">
          <button
            className="outline"
            onClick={() =>
              download(
                "trialops-investigation-" + run.id.slice(0, 8) + ".json",
                run,
              )
            }
          >
            Export JSON
          </button>
          <button
            className="outline"
            disabled={busy}
            aria-busy={busy}
            onClick={downloadPdf}
          >
            <Icon name="file" size={16} />
            Download PDF report
          </button>
        </div>
      </div>
      {!embedded && (
        <Link href={"/workspace/cases/" + run.case_id} className="text-link">
          Open case {run.case_id} →
        </Link>
      )}
      <ErrorBox error={error} />
      <div
        className="investigation-tabs"
        role="tablist"
        aria-label="Investigation sections"
      >
        {tabs.map(([key, label], i) => (
          <button
            key={key}
            type="button"
            role="tab"
            id={run.id + "-tab-" + key}
            aria-controls={run.id + "-panel-" + key}
            aria-selected={tab === key}
            tabIndex={tab === key ? 0 : -1}
            onClick={() => setTab(key)}
            onKeyDown={(e) => {
              let next = i;
              if (e.key === "ArrowRight") next = (i + 1) % tabs.length;
              else if (e.key === "ArrowLeft")
                next = (i + tabs.length - 1) % tabs.length;
              else if (e.key === "Home") next = 0;
              else if (e.key === "End") next = tabs.length - 1;
              else return;
              e.preventDefault();
              setTab(tabs[next][0]);
              e.currentTarget.parentElement
                ?.querySelectorAll<HTMLButtonElement>("button")
                [next]?.focus();
            }}
          >
            {label}
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        id={run.id + "-panel-" + tab}
        aria-labelledby={run.id + "-tab-" + tab}
        className="investigation-content"
        key={tab}
      >
        {tab === "overview" && (
          <>
            {rec.status === "insufficient_evidence" ? (
              <div className="notice">
                <strong>No relevant procedure found</strong>
                <p>Insufficient relevant evidence. Approval is unavailable.</p>
                <p>
                  Add a relevant procedure in Knowledge or ask a reviewer for
                  more details.
                </p>
              </div>
            ) : (
              <>
                <div className="section-heading">
                  <h3>What was found</h3>
                  <Badge value="supported" />
                </div>
                {(r.operational_findings?.length || 0) > 0 ? (
                  <p>
                    {r.operational_findings
                      .slice(0, 3)
                      .map((f: Row) => f.facts[0])
                      .join(" ")}
                  </p>
                ) : (
                  <p>
                    {cited.length} relevant{" "}
                    {cited.length === 1 ? "procedure was" : "procedures were"}{" "}
                    found. No matching issue-specific observations are
                    available.
                  </p>
                )}
                <p className="scope-note">
                  <Icon name="shield" size={16} />
                  Historical site-level context. Current status, exact case
                  linkage, and cause remain unconfirmed.
                </p>
                <div className="section-heading">
                  <h3>Checks to perform</h3>
                  <span className="subtle">
                    Open to read the full procedure
                  </span>
                </div>
                {cited.map((source: Row) => (
                  <details className="source cited-check" key={source.id}>
                    <summary>
                      <span>{source.title}</span>
                    </summary>
                    <p className="preserve">{source.content}</p>
                    <small>Source: {source.id}</small>
                  </details>
                ))}
              </>
            )}
            {(r.operational_findings?.length || 0) > 0 && (
              <button className="text-button" onClick={() => setTab("records")}>
                Inspect historical records and timestamps →
              </button>
            )}
            <div className="section-heading">
              <h3>Escalation drafts</h3>
              <span className="subtle">Unsent</span>
            </div>
            {r.escalation_drafts.length ? (
              r.escalation_drafts.map((d: Row) => (
                <article className="compact-draft" key={d.id}>
                  <details>
                    <summary>
                      {d.knowledge_ids?.includes("KB-001")
                        ? "Document processing escalation"
                        : "Synchronization escalation"}
                    </summary>
                    <p className="subtle">{d.subject}</p>
                    <pre>{d.body}</pre>
                  </details>
                  <button className="outline" onClick={() => copy(d)}>
                    {copied === d.id ? "Copied draft" : "Copy draft"}
                  </button>
                </article>
              ))
            ) : (
              <p className="subtle">No recorded condition triggered a draft.</p>
            )}
            <p className="subtle">Copying a draft does not send it.</p>
            {!run.decision ? (
              canReview ? (
                <form
                  className="review-form"
                  onSubmit={(e) => e.preventDefault()}
                >
                  <h3>Review the proposed checks</h3>
                  <p className="subtle">
                    Approval reviews these checks. It does not resolve the case
                    or send a draft.
                  </p>
                  <label>
                    Review notes
                    <textarea
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      minLength={5}
                      maxLength={2000}
                      rows={3}
                      placeholder="Add your reason for approving or rejecting these checks."
                    />
                  </label>
                  <AssessmentPanel cid={run.case_id} text={notes} />
                  <div className="actions">
                    <button
                      disabled={
                        busy ||
                        notes.trim().length < 5 ||
                        rec.status !== "supported"
                      }
                      onClick={() => decide("approved")}
                    >
                      Approve recommendation
                    </button>
                    <button
                      className="outline"
                      disabled={busy || notes.trim().length < 5}
                      onClick={() => decide("rejected")}
                    >
                      Reject
                    </button>
                  </div>
                </form>
              ) : (
                <p className="notice">
                  A reviewer or owner must record this decision.
                </p>
              )
            ) : (
              <div className="notice">
                <strong>
                  {run.decision} by {run.reviewer || "Former member"}
                </strong>
                <p>{run.review_notes}</p>
                <small>{run.reviewed_at && stamp(run.reviewed_at)}</small>
              </div>
            )}
          </>
        )}
        {tab === "evidence" && (
          <>
            <h3>Saved summary</h3>
            <p>{rec.summary}</p>
            <details className="source">
              <summary>Why the cause is unconfirmed</summary>
              <p>{rec.hypothesis}</p>
            </details>
            <h3>Retrieved procedures</h3>
            <p className="subtle">
              Cited procedures support these checks. Candidates were retrieved
              but not selected.
            </p>
            {r.sources.map((source: Row) => (
              <details className="source" key={source.id}>
                <summary>
                  <span>{source.title}</span>
                  <Badge
                    value={
                      rec.evidence_ids.includes(source.id)
                        ? "cited"
                        : "candidate"
                    }
                  />
                </summary>
                <p className="preserve">{source.content}</p>
                <p className="subtle">
                  {source.id} · {source.retrieval_method} · score{" "}
                  {source.similarity}. A score does not establish relevance.
                </p>
              </details>
            ))}
            <details className="source">
              <summary>Complete documented next steps</summary>
              <p className="preserve">{rec.recommended_next_step}</p>
            </details>
          </>
        )}
        {tab === "records" && (
          <>
            <h3>Historical site records</h3>
            <p className="scope-note">
              Saved with this investigation. They do not prove the current
              status or cause of this case.
            </p>
            <div className="snapshot-grid">
              {Object.entries(r.operational_evidence || {}).map(
                ([kind, value]) => {
                  const g = value as Row;
                  return (
                    <article className="snapshot" key={kind}>
                      <h4>
                        {kind === "synchronization"
                          ? "Synchronization jobs"
                          : "Document processing"}
                      </h4>
                      {g.snapshot ? (
                        <>
                          <div className="record-context">
                            <strong>{g.snapshot.study_id}</strong>
                            <strong>{g.snapshot.site_id}</strong>
                          </div>
                          <p>Observed {stamp(g.snapshot.observed_at)}</p>
                          <p>
                            {g.records.length}{" "}
                            {g.records.length === 1 ? "record" : "records"}
                          </p>
                          <details>
                            <summary>View saved record fields</summary>
                            {g.records.map((record: Row) => (
                              <dl className="record-fields" key={record.id}>
                                {Object.entries(record).map(([key, val]) => (
                                  <div key={key}>
                                    <dt>{key.replaceAll("_", " ")}</dt>
                                    <dd>
                                      {typeof val === "boolean"
                                        ? val
                                          ? "Yes"
                                          : "No"
                                        : String(val ?? "Not recorded")}
                                    </dd>
                                  </div>
                                ))}
                              </dl>
                            ))}
                          </details>
                          <details className="technical">
                            <summary>Technical JSON</summary>
                            <pre>{JSON.stringify(g, null, 2)}</pre>
                          </details>
                        </>
                      ) : (
                        <p>No snapshot available for this study and site.</p>
                      )}
                    </article>
                  );
                },
              )}
            </div>
            {(r.operational_findings || []).map((f: Row) => (
              <details className="source" key={f.record_id}>
                <summary>
                  <span>{f.record_id}</span>
                  <span>{f.knowledge_ids.join(", ")}</span>
                </summary>
                <ul>
                  {f.facts.map((fact: string) => (
                    <li key={fact}>{fact}</li>
                  ))}
                </ul>
                <p className="subtle">{f.scope}</p>
              </details>
            ))}
          </>
        )}
        {tab === "activity" && (
          <>
            <h3>Investigation activity</h3>
            {(run.events || []).map((event: Row) => (
              <article className="activity-row" key={event.id}>
                <strong>{event.event_type.replaceAll("_", " ")}</strong>
                <p>
                  {stamp(event.created_at)} · {event.actor_name || "System"}
                </p>
                {event.notes && <p>{event.notes}</p>}
              </article>
            ))}
            <details className="source">
              <summary>Tool trace · {r.tool_calls.length} calls</summary>
              {r.tool_calls.map((t: Row, i: number) => (
                <div className="trace" key={i}>
                  <b>{t.tool}</b>
                  <span>
                    {t.status} · {t.duration_seconds}s
                  </span>
                </div>
              ))}
            </details>
            <p className="subtle">{r.mode_label}</p>
            <details className="technical">
              <summary>Investigation identifiers</summary>
              <p>
                Run {run.id} · Case {run.case_id} · Model {run.model}
              </p>
            </details>
          </>
        )}
      </div>
      {embedded && (
        <Link className="text-link" href={"/workspace/runs/" + run.id}>
          Open saved investigation →
        </Link>
      )}
    </section>
  );
}

function HistoryList() {
  const [data, setData] = useState<Row | null>(null),
    [q, setQ] = useState(""),
    [decision, setDecision] = useState(""),
    [offset, setOffset] = useState(0),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    const t = setTimeout(
      () =>
        api(
          "/runs?" +
            new URLSearchParams({ q, decision, offset: String(offset) }),
        )
          .then((d) => {
            if (active) {
              setData(d);
              setLoading(false);
            }
          })
          .catch((e) => {
            if (active) {
              setError(e.message);
              setData(null);
              setLoading(false);
            }
          }),
      180,
    );
    return () => {
      active = false;
      clearTimeout(t);
    };
  }, [q, decision, offset]);
  return (
    <>
      <Heading
        label="INVESTIGATION HISTORY"
        title="Investigations"
        description="Reopen the procedures and records saved with an investigation."
      >
        <Link className="button" href="/workspace/cases">
          Choose a case to investigate
        </Link>
      </Heading>
      <ErrorBox error={error} />
      <div className="list-controls">
        <input
          aria-label="Search investigations"
          placeholder="Search case, title, or run…"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOffset(0);
          }}
        />
        <select
          aria-label="Review status"
          value={decision}
          onChange={(e) => {
            setDecision(e.target.value);
            setOffset(0);
          }}
        >
          <option value="">All review statuses</option>
          {["pending", "approved", "rejected"].map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
      </div>
      <div className="panel list-panel" aria-busy={loading}>
        {loading ? (
          <p role="status">Loading investigations…</p>
        ) : !data ? (
          <p>
            Investigations could not be loaded. Refresh or change a filter to
            retry.
          </p>
        ) : !data.items.length ? (
          <Empty title="No saved investigations yet.">
            <Link href="/workspace/cases">Choose a case to investigate →</Link>
          </Empty>
        ) : (
          data.items.map((r: Row) => (
            <Link
              className="case-row"
              key={r.id}
              href={"/workspace/runs/" + r.id}
            >
              <div>
                <small>
                  {r.case_id} · {stamp(r.created_at)}
                </small>
                <h3>{r.title}</h3>
              </div>
              <Badge value={r.decision || "pending"} />
            </Link>
          ))
        )}
      </div>
      <div className="pagination">
        <span role="status">
          {loading ? "Updating results…" : `${data?.total ?? 0} investigations`}
        </span>
        <button
          className="outline"
          disabled={loading || !offset}
          onClick={() => setOffset(offset - 25)}
        >
          Previous
        </button>
        <button
          className="outline"
          disabled={loading || !data || offset + 25 >= data.total}
          onClick={() => setOffset(offset + 25)}
        >
          Next
        </button>
      </div>
    </>
  );
}
function Knowledge({ me }: { me: Row }) {
  const [items, setItems] = useState<Row[]>([]),
    [selected, setSelected] = useState<Row | null>(null),
    [title, setTitle] = useState(""),
    [content, setContent] = useState(""),
    [category, setCategory] = useState("unknown"),
    [q, setQ] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [message, setMessage] = useState("");
  const owner = me.role === "owner";
  const [editorOpen, setEditorOpen] = useState(false),
    [editing, setEditing] = useState(false),
    [libraryStatus, setLibraryStatus] = useState("active");
  const fileInput = useRef<HTMLInputElement>(null),
    procedureDetail = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!editorOpen) return;
    const frame = requestAnimationFrame(() => {
      procedureDetail.current?.focus({ preventScroll: true });
      procedureDetail.current?.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
        block: "start",
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [editorOpen, selected?.id, editing]);
  const dirty =
    editing &&
    (title !== (selected?.title || "") ||
      content !== (selected?.content || "") ||
      category !== (selected?.category || "unknown"));
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  const load = useCallback(async () => setItems(await api("/knowledge")), []);
  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, [load]);
  useEffect(() => {
    if (!items.some((x) => x.indexing_status === "queued")) return;
    const t = setInterval(() => load().catch((e) => setError(e.message)), 3000);
    return () => clearInterval(t);
  }, [items, load]);
  function choose(a: Row | null, confirmed = false) {
    if (
      !confirmed &&
      dirty &&
      !window.confirm("Discard the unsaved procedure changes?")
    )
      return false;
    setEditorOpen(true);
    setEditing(!a);
    setSelected(a);
    setTitle(a?.title || "");
    setContent(a?.content || "");
    setCategory(a?.category || "unknown");
    setError("");
    setMessage("");
    return true;
  }
  async function upload(file: File) {
    if (dirty && !window.confirm("Discard the unsaved procedure changes?"))
      return;
    if (file.size > 2 * 1024 * 1024) {
      setError("Upload must be 2 MB or smaller.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const x = await api("/knowledge/extract", form);
      choose(null, true);
      setTitle(x.title);
      setContent(x.content);
      setMessage(
        `${x.characters.toLocaleString()} characters extracted. Review the text before saving.`,
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await api("/knowledge" + (selected ? "/" + selected.id : ""), {
        title,
        content,
        category,
        ...(selected ? { expected_version: selected.version } : {}),
      });
      await load();
      setSelected({
        ...(selected || {}),
        id: r.id,
        title,
        content,
        category,
        version: r.version,
        archived: selected?.archived || false,
      });
      setMessage(
        "Procedure saved. Text search is available; vector indexing runs when a model is enabled.",
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function archive() {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      await api("/knowledge/" + selected.id + "/archive", {
        archived: !selected.archived,
        expected_version: selected.version,
      });
      setSelected({ ...selected, archived: !selected.archived });
      await load();
      setMessage(
        selected.archived
          ? "Procedure restored for new investigations."
          : "Procedure archived. Saved investigations retain their earlier evidence.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const visible = items.filter(
    (a) =>
      (libraryStatus === "all" ||
        (libraryStatus === "archived" ? a.archived : !a.archived)) &&
      (a.title + " " + a.id).toLowerCase().includes(q.toLowerCase()),
  );
  function closeEditor() {
    if (dirty && !window.confirm("Discard the unsaved procedure changes?"))
      return;
    setEditorOpen(false);
    setEditing(false);
    setError("");
  }
  return (
    <>
      <Heading
        label="KNOWLEDGE LIBRARY"
        title="Knowledge library"
        description="Manage the procedures used in investigations."
      >
        {owner && (
          <div className="actions">
            <button className="outline" onClick={() => choose(null)}>
              New procedure
            </button>
            <button onClick={() => fileInput.current?.click()}>
              Upload procedure
            </button>
          </div>
        )}
      </Heading>
      {owner && (
        <>
          <input
            ref={fileInput}
            className="hidden-file-input"
            aria-label="Upload procedure file"
            type="file"
            accept=".txt,.md,.pdf"
            disabled={busy}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void upload(file);
              e.target.value = "";
            }}
          />
          <p className="subtle upload-limits">
            TXT, Markdown, or text-based PDF · up to 2 MB / 30 pages
          </p>
        </>
      )}
      <ErrorBox error={error} />
      {message && (
        <p className="success" role="status">
          {message}
        </p>
      )}
      <div className="case-toolbar">
        <input
          aria-label="Search procedures"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search procedures…"
        />
        <select
          aria-label="Procedure status"
          value={libraryStatus}
          onChange={(e) => setLibraryStatus(e.target.value)}
        >
          <option value="active">Active</option>
          <option value="archived">Archived</option>
          <option value="all">All procedures</option>
        </select>
      </div>
      <div className="panel table-panel">
        <DataTable<Row>
          label="Knowledge procedures"
          rows={visible}
          rowKey={(a) => a.id}
          empty={
            <div className="empty">
              <h3>No matching procedures</h3>
              <p>
                Change the search or status filter
                {owner ? ", or add a procedure." : "."}
              </p>
            </div>
          }
          columns={[
            {
              label: "Procedure",
              render: (a) => (
                <button
                  className="procedure-title"
                  onClick={() => choose(a)}
                  aria-label={a.title + " v" + a.version}
                >
                  <strong>{a.title}</strong>
                  <small>{a.id}</small>
                </button>
              ),
            },
            {
              label: "Category",
              render: (a) => (
                <span>
                  {categories.find((c) => c[0] === a.category)?.[1] ||
                    a.category}
                </span>
              ),
            },
            { label: "Version", head: "head-nudge", render: (a) => <span>v{a.version}</span> },
            {
              label: "Status",
              render: (a) => (
                <>
                  <Badge value={a.archived ? "archived" : "active"} />
                  <small>
                    {a.indexing_error
                      ? "Indexing needs attention"
                      : a.indexing_status === "queued"
                        ? "Indexing queued"
                        : "Search ready"}
                  </small>
                </>
              ),
            },
          ]}
        />
      </div>
      <p className="subtle">
        {visible.length} procedures in this view. Earlier investigations keep
        their saved source version.
      </p>
      {editorOpen && (
        <section
          ref={procedureDetail}
          tabIndex={-1}
          className="panel procedure-detail"
          aria-label="Procedure details"
        >
          <div className="section-heading">
            <h2>
              {selected
                ? editing
                  ? "Edit procedure"
                  : "Review procedure"
                : "Add a procedure"}
            </h2>
            <button className="outline" disabled={busy} onClick={closeEditor}>
              Close procedure
            </button>
          </div>
          {!editing && selected ? (
            <>
              <div className="context-line">
                <span>
                  {selected.id} · v{selected.version}
                </span>
                <Badge value={selected.archived ? "archived" : "active"} />
              </div>
              <h3>{selected.title}</h3>
              <p className="preserve">{selected.content}</p>
              {selected.indexing_error && (
                <p className="notice">{selected.indexing_error}</p>
              )}
              {owner ? (
                <div className="actions">
                  <button disabled={busy} onClick={() => setEditing(true)}>
                    Edit procedure
                  </button>
                  <button className="outline" disabled={busy} onClick={archive}>
                    {selected.archived
                      ? "Restore procedure"
                      : "Archive procedure"}
                  </button>
                </div>
              ) : (
                <p className="subtle">
                  Owners maintain procedures. Your role has read access.
                </p>
              )}
            </>
          ) : (
            <form className="form-panel" onSubmit={save}>
              <label>
                Procedure title
                <input
                  aria-label="Procedure title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  minLength={5}
                  maxLength={200}
                  required
                  disabled={!owner || busy}
                />
              </label>
              <label>
                Category
                <FieldCategory
                  value={category}
                  onChange={setCategory}
                  disabled={!owner || busy}
                />
              </label>
              <label>
                Procedure text
                <textarea
                  aria-label="Procedure text"
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  minLength={30}
                  maxLength={50000}
                  rows={7}
                  required
                  disabled={!owner || busy}
                  placeholder="Paste documented checks and conditions. Do not include patient information."
                />
              </label>
              <small>
                {content.length.toLocaleString()} / 50,000 characters. Editing
                creates a new version.
              </small>
              {owner && (
                <div className="actions">
                  <button
                    disabled={
                      busy ||
                      title.trim().length < 5 ||
                      content.trim().length < 30
                    }
                  >
                    {busy ? "Saving…" : "Save procedure"}
                  </button>
                  {selected && (
                    <button
                      type="button"
                      className="outline"
                      disabled={busy}
                      onClick={archive}
                    >
                      {selected.archived
                        ? "Restore procedure"
                        : "Archive procedure"}
                    </button>
                  )}
                </div>
              )}
            </form>
          )}
        </section>
      )}
    </>
  );
}
function Operations({ me }: { me: Row }) {
  const [items, setItems] = useState<Row[]>([]),
    [text, setText] = useState(""),
    [error, setError] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  const snapshotFile = useRef<HTMLInputElement>(null);
  const [snapshotFileName, setSnapshotFileName] = useState("");
  const load = useCallback(async () => setItems(await api("/operations")), []);
  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, [load]);
  async function example() {
    try {
      const d = await api("/operations/example");
      setText(JSON.stringify(d, null, 2));
      setSnapshotFileName("Example format loaded");
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body = JSON.parse(text);
      const d = await api("/operations", body);
      setMessage(d.message);
      await load();
    } catch (err) {
      setError(
        err instanceof SyntaxError
          ? "Invalid JSON. Check commas, quotes, and brackets."
          : (err as Error).message,
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Heading
        label="OPERATIONAL RECORDS"
        title="Operational records"
        description="Historical site snapshots. Current status and case linkage require verification."
      >
        {me.role === "owner" && (
          <a className="button" href="#snapshot-import">
            Import snapshot
          </a>
        )}
      </Heading>
      <ErrorBox error={error} />
      {message && (
        <p role="status" className="success">
          {message}
        </p>
      )}
      <div className="two-grid">
        {items.map((row) => (
          <article className="panel" key={row.site_id}>
            <h2>
              {row.study_id} · {row.site_id}
            </h2>
            {Object.entries(row.evidence).map(([kind, val]) => {
              const g = val as Row;
              return (
                <div className="record-group" key={kind}>
                  <strong>{kind.replaceAll("_", " ")}</strong>
                  <p>
                    {g.records.length} records ·{" "}
                    {g.snapshot ? stamp(g.snapshot.observed_at) : "No snapshot"}
                  </p>
                  <details>
                    <summary>Inspect records</summary>
                    {g.records.map((record: Row) => (
                      <dl className="record-fields" key={record.id}>
                        {Object.entries(record).map(([key, value]) => (
                          <div key={key}>
                            <dt>{key.replaceAll("_", " ")}</dt>
                            <dd>
                              {typeof value === "boolean"
                                ? value
                                  ? "Yes"
                                  : "No"
                                : String(value ?? "Not recorded")}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    ))}
                    <details className="technical">
                      <summary>Technical JSON</summary>
                      <pre>{JSON.stringify(g, null, 2)}</pre>
                    </details>
                  </details>
                </div>
              );
            })}
          </article>
        ))}
      </div>
      {me.role === "owner" ? (
        <form id="snapshot-import" className="panel form-panel" onSubmit={save}>
          <h2>Import a synthetic snapshot</h2>
          <p>
            Use the example format. Both groups must share a matching snapshot,
            study, site, and observation time. Up to 10 records per group.
            Uploaded timestamps must not exceed the observation time.
          </p>
          <div className="snapshot-file-actions">
            <button
              type="button"
              className="outline"
              disabled={busy}
              onClick={example}
            >
              Load example format
            </button>
            <button
              type="button"
              className="outline"
              disabled={busy}
              onClick={() => snapshotFile.current?.click()}
            >
              Choose JSON file
            </button>
            <input
              ref={snapshotFile}
              className="hidden-file-input"
              aria-label="Snapshot JSON file"
              type="file"
              accept=".json"
              disabled={busy}
              onChange={async (e) => {
                const f = e.target.files?.[0];
                e.target.value = "";
                if (!f) return;
                if (f.size > 100000) {
                  setError("Use a JSON file smaller than 100 KB.");
                  return;
                }
                try {
                  setText(await f.text());
                  setSnapshotFileName(f.name);
                  setError("");
                } catch {
                  setError("The file could not be read. Choose it again.");
                }
              }}
            />
          </div>
          <small className="snapshot-file-status" role="status">
            {snapshotFileName || "No file selected · JSON up to 100 KB"}
          </small>
          <label>
            Snapshot JSON
            <textarea
              className="code-editor"
              rows={8}
              value={text}
              onChange={(e) => setText(e.target.value)}
              maxLength={100000}
              required
            />
          </label>
          <button disabled={busy || !text.trim()}>
            {busy ? "Validating…" : "Validate and save snapshot"}
          </button>
          <p className="subtle">
            New investigations use the saved snapshot. Earlier investigations
            are unchanged.
          </p>
        </form>
      ) : (
        <p className="notice">Only owners can import operational snapshots.</p>
      )}
    </>
  );
}
function ROI({ me }: { me: Row }) {
  const [items, setItems] = useState<Row[]>([]),
    [runs, setRuns] = useState<Row[]>([]),
    [runId, setRunId] = useState(""),
    [baseline, setBaseline] = useState("30"),
    [assisted, setAssisted] = useState("8"),
    [hourly, setHourly] = useState("55"),
    [cost, setCost] = useState("0"),
    [confirmed, setConfirmed] = useState(false),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const load = useCallback(async () => {
    const [s, r] = await Promise.all([
      api("/roi"),
      api("/runs?decision=approved"),
    ]);
    setItems(s);
    let all = r.items;
    for (let offset = 25; offset < r.total; offset += 25) {
      const page = await api("/runs?decision=approved&offset=" + offset);
      all = all.concat(page.items);
    }
    setRuns(all);
    setRunId(
      (current) =>
        current ||
        all.find((x: Row) => !s.some((y: Row) => y.run_id === x.id))?.id ||
        "",
    );
  }, []);
  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, [load]);
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/roi/" + runId, {
        baseline: Number(baseline),
        assisted: Number(assisted),
        hourly_cost: Number(hourly),
        ai_cost: Number(cost),
        confirmed,
      });
      await load();
      setRunId("");
      setConfirmed(false);
      setMessage(
        "Scenario saved. These values are assumptions, not measured savings.",
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const minutes = Number(baseline) - Number(assisted),
    value = (minutes * Number(hourly)) / 60 - Number(cost);
  return (
    <>
      <Heading
        label="VALUE TRACKING"
        title="ROI scenarios"
        description="Scenario capacity value is not cash savings. Hardware, electricity, development, and maintenance costs are excluded."
      />
      <ErrorBox error={error} />
      {message && (
        <p role="status" className="success">
          {message}
        </p>
      )}
      <div className="editor-layout">
        <form className="panel form-panel" onSubmit={save}>
          <h2>Scenario for an approved run</h2>
          <label>
            Approved investigation
            <select
              aria-label="Approved investigation"
              value={runId}
              onChange={(e) => setRunId(e.target.value)}
              required
            >
              <option value="">Select an investigation</option>
              {runs
                .filter((r) => !items.some((x) => x.run_id === r.id))
                .map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.title} · {r.id.slice(0, 8)}
                  </option>
                ))}
            </select>
          </label>
          <div className="form-grid">
            {[
              [
                "Assumed manual baseline (minutes)",
                baseline,
                setBaseline,
                1440,
              ],
              [
                "Assumed AI-assisted human work (minutes)",
                assisted,
                setAssisted,
                1440,
              ],
              ["Assumed loaded hourly cost (USD)", hourly, setHourly, 10000],
              ["Assumed AI cost for this run (USD)", cost, setCost, 10000],
            ].map(([label, v, set, max]) => (
              <label key={label as string}>
                {label as string}
                <input
                  type="number"
                  min={0}
                  max={max as number}
                  step="0.01"
                  required
                  value={v as string}
                  onChange={(e) => (set as (s: string) => void)(e.target.value)}
                />
              </label>
            ))}
          </div>
          <p className="subtle">
            Human-work minutes include investigation and review effort. Do not
            substitute model execution time. Zero AI cost means an assumed zero
            local API charge.
          </p>
          <label className="check-row">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            <span>
              I confirm these are scenario assumptions, not measured savings.
            </span>
          </label>
          <button
            disabled={
              busy ||
              !confirmed ||
              !runId ||
              !["owner", "reviewer"].includes(me.role)
            }
          >
            {busy ? "Saving…" : "Save scenario"}
          </button>
          {!runs.length && (
            <p className="notice">
              Review and approve a supported investigation first.
            </p>
          )}
        </form>
        <aside className="guide-card roi-preview">
          <p className="eyebrow">SCENARIO PREVIEW</p>
          <h3>{Number.isFinite(minutes) ? minutes : "—"}</h3>
          <p>Estimated minutes of capacity freed</p>
          <h3>{Number.isFinite(value) ? money(value) : "—"}</h3>
          <p>Estimated net capacity value</p>
          <p className="notice">Scenario estimate · not cash savings</p>
          <details>
            <summary>How this is calculated</summary>
            <p>
              Baseline minus human effort; minutes ÷ 60 × hourly cost, minus AI
              cost. Negative values are preserved.
            </p>
          </details>
        </aside>
      </div>
      <h2>Recorded scenarios</h2>
      {!items.length ? (
        <Empty title="No scenarios recorded yet." />
      ) : (
        items.map((s) => (
          <article className="panel scenario-record" key={s.run_id}>
            <div>
              <h3>{s.title}</h3>
              <small>{stamp(s.created_at)}</small>
              <details className="technical">
                <summary>Investigation reference</summary>
                <Link
                  className="text-link"
                  href={"/workspace/runs/" + s.run_id}
                >
                  Open saved investigation →
                </Link>
                <p>Run {s.run_id}</p>
              </details>
            </div>
            <div>
              <strong>{Number(s.baseline) - Number(s.assisted)} minutes</strong>
              <span>
                {money(
                  ((Number(s.baseline) - Number(s.assisted)) *
                    Number(s.hourly_cost)) /
                    60 -
                    Number(s.ai_cost),
                )}{" "}
                estimated net capacity
              </span>
            </div>
          </article>
        ))
      )}
    </>
  );
}
function Feedback({ me }: { me: Row }) {
  const [rating, setRating] = useState("4"),
    [message, setMessage] = useState(""),
    [error, setError] = useState(""),
    [success, setSuccess] = useState(""),
    [busy, setBusy] = useState(false),
    [items, setItems] = useState<Row[]>([]);
  const load = useCallback(async () => {
    if (me.role === "owner") setItems(await api("/feedback"));
  }, [me.role]);
  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, [load]);
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/feedback", { rating: Number(rating), message });
      setMessage("");
      setSuccess(
        "Thank you. Your feedback was saved for the deployment operator.",
      );
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Heading
        label="PRODUCT FEEDBACK"
        title="Share feedback"
        description="Help improve the workflow."
      />
      <ErrorBox error={error} />
      {success && (
        <p className="success" role="status">
          {success}
        </p>
      )}
      <form className="panel form-panel narrow" onSubmit={save}>
        <fieldset className="rating-buttons">
          <legend>How was your experience?</legend>
          <div className="rating-options">
            {[1, 2, 3, 4, 5].map((n) => (
              <label key={n}>
                <input
                  type="radio"
                  name="rating"
                  value={n}
                  checked={rating === String(n)}
                  onChange={() => setRating(String(n))}
                  aria-label={n + " out of 5"}
                />
                <span>{n}</span>
              </label>
            ))}
          </div>
          <div className="rating-labels">
            <span>Needs work</span>
            <span>Excellent</span>
          </div>
        </fieldset>
        <label>
          Your feedback
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            rows={5}
            minLength={10}
            maxLength={2000}
            required
            placeholder="What worked? Where did you get stuck? What would make this useful?"
          />
        </label>
        <button disabled={busy || message.trim().length < 10} aria-busy={busy}>
          {busy ? "Saving…" : "Submit feedback"}
        </button>
        <small className="feedback-data-note">
          Feedback is stored in this deployment for up to 30 days. No email or
          external message is sent.
        </small>
      </form>
      {me.role === "owner" && (
        <>
          <h2>Workspace feedback</h2>
          {items.map((x) => (
            <article className="panel" key={x.id}>
              <Badge value={x.rating + " / 5"} />
              <p className="preserve">{x.message}</p>
              <small>
                {x.name || "Former member"} · {stamp(x.created_at)}
              </small>
            </article>
          ))}
        </>
      )}
    </>
  );
}
function Settings({ me }: { me: Row }) {
  const [section, setSection] = useState("preferences");
  const currentPreferences = usePreferences(me.user_id);
  const [display, setDisplay] = useState<DisplayPreferences>(() =>
    readPreferences(me.user_id),
  );
  const [members, setMembers] = useState<Row[]>([]),
    [role, setRole] = useState("reviewer"),
    [code, setCode] = useState(""),
    [accept, setAccept] = useState(""),
    [error, setError] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false),
    [catalog, setCatalog] = useState<Row>({ studies: [], sites: [] }),
    [context, setContext] = useState({
      study_id: "",
      study_name: "",
      site_id: "",
      site_name: "",
      site_study_id: "",
    });
  useEffect(() => {
    api("/members")
      .then(setMembers)
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    api("/catalog")
      .then(setCatalog)
      .catch((e) => setError(e.message));
  }, []);
  async function createContext(kind: "studies" | "sites") {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await api(
        "/catalog/" + kind,
        kind === "studies"
          ? { id: context.study_id, name: context.study_name }
          : {
              id: context.site_id,
              name: context.site_name,
              study_id: context.site_study_id,
            },
      );
      setCatalog(await api("/catalog"));
      setContext((current) =>
        kind === "studies"
          ? { ...current, study_id: "", study_name: "" }
          : { ...current, site_id: "", site_name: "" },
      );
      setMessage(
        kind === "studies"
          ? "Study context created."
          : "Site context created and linked to the selected study.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function invite() {
    setBusy(true);
    setError("");
    try {
      const d = await api("/invitations", { role });
      setCode(d.code);
      setMessage(d.message);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function acceptInvite(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const d = await api("/invitations/accept", { code: accept });
      await api("/auth/switch", { workspace_id: d.workspace_id });
      window.location.assign("/workspace");
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }
  async function change(id: string) {
    try {
      await api("/auth/switch", { workspace_id: id });
      window.location.assign("/workspace");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function exportData() {
    setBusy(true);
    setError("");
    try {
      download("trialops-workspace-export.json", await api("/export"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Heading
        label="WORKSPACE SETTINGS"
        title="Workspace settings"
        description="Your preferences, workspace administration, and data policy."
      />
      <ErrorBox error={error} />
      {message && (
        <p className="success" role="status">
          {message}
        </p>
      )}
      <div className="settings-sections" aria-label="Settings sections">
        {[
          ["preferences", "Preferences"],
          ["team", "Workspace & team"],
          ...(me.role === "owner" ? [["catalog", "Studies & sites"]] : []),
          ["policy", "Data policy"],
        ].map(([key, label]) => (
          <button
            key={key}
            className={section === key ? "" : "outline"}
            aria-pressed={section === key}
            onClick={() => {
              setSection(key);
              setMessage("");
              setError("");
            }}
          >
            {label}
          </button>
        ))}
      </div>
      <section
        className="panel preferences-panel"
        hidden={section !== "preferences"}
      >
        <h2>Your display preferences</h2>
        <p className="subtle">Saved for this account in this browser.</p>
        <div className="preference-row">
          <span>
            <strong>Content spacing</strong>
            <small>Adjust table and list row spacing.</small>
          </span>
          <PreferenceChoices
            name="display-density"
            legend="Content spacing"
            value={display.density}
            options={[
              ["compact", "Compact"],
              ["comfortable", "Comfortable"],
            ]}
            onChange={(value) =>
              setDisplay({
                ...display,
                density: value as DisplayPreferences["density"],
              })
            }
          />
        </div>
        <div className="preference-row">
          <span>
            <strong>Default page after sign-in</strong>
            <small>Choose where to start working.</small>
          </span>
          <PreferenceChoices
            name="display-start-page"
            legend="Default page after sign-in"
            value={display.startPage}
            options={[
              ["overview", "Overview"],
              ["cases", "Cases"],
            ]}
            onChange={(value) =>
              setDisplay({
                ...display,
                startPage: value as DisplayPreferences["startPage"],
              })
            }
          />
        </div>
        <div className="preferences-footer">
          <button
            onClick={() => {
              try {
                savePreferences(me.user_id, display);
                setMessage("Display preferences saved in this browser.");
                setError("");
              } catch {
                setError(
                  "This browser cannot store preferences. Allow local storage and try again.",
                );
              }
            }}
          >
            Save preferences
          </button>
          <small className="applied-preferences">
            Applied: {currentPreferences.density} spacing.
          </small>
        </div>
      </section>
      <div hidden={section !== "team"}>
        <div className="two-grid">
          <section className="panel">
            <h2>Your workspace</h2>
            <label>
              Switch workspace
              <select
                value={me.workspace_id}
                onChange={(e) => change(e.target.value)}
              >
                {me.workspaces.map((w: Row) => (
                  <option key={w.id} value={w.id}>
                    {w.name} · {w.role}
                  </option>
                ))}
              </select>
            </label>
            <p>
              {me.name} · {me.email}
            </p>
            <Badge value={me.role} />
            <p className="subtle">
              Owner: knowledge, snapshots, invitations, reviews, and resolution.
              Reviewer: reviews and resolution. Analyst: intake, investigations,
              assignment, and notes.
            </p>
            {me.role === "owner" && (
              <button className="outline" disabled={busy} onClick={exportData}>
                Export workspace records
              </button>
            )}
          </section>
          <section className="panel">
            <h2>Members</h2>
            {members.map((m) => (
              <div className="member" key={m.id}>
                <div>
                  <strong>{m.name}</strong>
                  <small>{m.email}</small>
                </div>
                <Badge value={m.role} />
              </div>
            ))}
          </section>
        </div>
        {me.guest ? (
          <section className="panel">
            <h2>Keep a permanent workspace.</h2>
            <p>
              Your sample workspace expires after 24 hours. Export it before
              expiry if you want a reference copy. Creating an account starts a
              new workspace; it does not automatically transfer sample data.
            </p>
            <Link className="button" href="/sign-in?mode=register">
              Create account →
            </Link>
          </section>
        ) : (
          <div className="two-grid">
            {me.role === "owner" && (
              <section className="panel">
                <h2>Invite a teammate</h2>
                <label>
                  Invitation role
                  <select
                    aria-label="Invitation role"
                    value={role}
                    onChange={(e) => setRole(e.target.value)}
                  >
                    <option value="reviewer">Reviewer</option>
                    <option value="analyst">Analyst</option>
                  </select>
                </label>
                <button disabled={busy} onClick={invite}>
                  Create invitation code
                </button>
                {code && (
                  <div className="notice">
                    <strong>Share this one-use code directly.</strong>
                    <pre>{code}</pre>
                    <small>
                      Expires in 24 hours. Anyone holding the code can join with
                      the selected role. No invitation email was sent.
                    </small>
                  </div>
                )}
              </section>
            )}
            <form className="panel form-panel" onSubmit={acceptInvite}>
              <h2>Join another workspace</h2>
              <label>
                Invitation code
                <input
                  value={accept}
                  onChange={(e) => setAccept(e.target.value)}
                  maxLength={128}
                  required
                  autoComplete="off"
                />
              </label>
              <button disabled={busy || !accept.trim()}>
                Accept invitation
              </button>
            </form>
          </div>
        )}
      </div>
      <div hidden={section !== "catalog"}>
        {me.role === "owner" && (
          <section className="panel">
            <h2>Study and site contexts</h2>
            <p>
              Add your own synthetic operational contexts. IDs must be unique in
              this workspace and contain 2–50 letters, numbers, underscores, or
              hyphens. Maximum 50 studies and 200 sites.
            </p>
            <div className="two-grid">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void createContext("studies");
                }}
              >
                <h3>Add a study</h3>
                <label>
                  New study ID
                  <input
                    value={context.study_id}
                    onChange={(e) =>
                      setContext({ ...context, study_id: e.target.value })
                    }
                    required
                    minLength={2}
                    maxLength={50}
                    pattern="[A-Za-z0-9][A-Za-z0-9_\-]{1,49}"
                    placeholder="CT-SAMPLE-NEW"
                  />
                </label>
                <label>
                  Study name
                  <input
                    value={context.study_name}
                    onChange={(e) =>
                      setContext({ ...context, study_name: e.target.value })
                    }
                    required
                    minLength={3}
                    maxLength={200}
                  />
                </label>
                <button disabled={busy}>Add study</button>
              </form>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void createContext("sites");
                }}
              >
                <h3>Add a research site</h3>
                <label>
                  New site ID
                  <input
                    value={context.site_id}
                    onChange={(e) =>
                      setContext({ ...context, site_id: e.target.value })
                    }
                    required
                    minLength={2}
                    maxLength={50}
                    pattern="[A-Za-z0-9][A-Za-z0-9_\-]{1,49}"
                    placeholder="SITE-SAMPLE-NEW"
                  />
                </label>
                <label>
                  Site name
                  <input
                    value={context.site_name}
                    onChange={(e) =>
                      setContext({ ...context, site_name: e.target.value })
                    }
                    required
                    minLength={3}
                    maxLength={200}
                  />
                </label>
                <label>
                  Site study
                  <select
                    aria-label="Site study"
                    value={context.site_study_id}
                    onChange={(e) =>
                      setContext({ ...context, site_study_id: e.target.value })
                    }
                    required
                  >
                    <option value="">Select a study</option>
                    {catalog.studies.map((study: Row) => (
                      <option key={study.id} value={study.id}>
                        {study.id} · {study.name}
                      </option>
                    ))}
                  </select>
                </label>
                <button disabled={busy || !context.site_study_id}>
                  Add site
                </button>
              </form>
            </div>
            <details className="catalog-list">
              <summary>
                {catalog.studies.length} studies · {catalog.sites.length} sites
              </summary>
              <div className="catalog-table">
                {catalog.studies.map((study: Row) => (
                  <article key={study.id}>
                    <strong>
                      {study.id} · {study.name}
                    </strong>
                    <div>
                      {catalog.sites
                        .filter((site: Row) => site.study_id === study.id)
                        .map((site: Row) => (
                          <p key={site.id}>
                            {site.id} · {site.name}
                          </p>
                        ))}
                    </div>
                  </article>
                ))}
              </div>
            </details>
          </section>
        )}
      </div>
      <div hidden={section !== "policy"}>
        <div className="policy-cards">
          <details className="panel" open>
            <summary>What you can upload</summary>
            <p>Operational procedures and non-patient sample records.</p>
            <p>Do not upload patient information.</p>
          </details>
          <details className="panel">
            <summary>Review and resolution</summary>
            <p>
              Approval records a review. Resolution is a separate decision.
              Drafts remain unsent.
            </p>
          </details>
          <details className="panel">
            <summary>Workspace data</summary>
            <p>
              Owners can export workspace records. Your deployment operator
              manages retention, backups, and deletion. Email identifies your
              account. Email verification and password recovery require
              configured email delivery.
            </p>
          </details>
          <Link className="button outline" href="/guide#data-policy">
            Open data policy & guide →
          </Link>
        </div>{" "}
      </div>

      <div hidden={section !== "policy"}>
        <WorkspacePolicies me={me} />
      </div>
    </>
  );
}

function PreferenceChoices({
  name,
  legend,
  value,
  options,
  onChange,
}: {
  name: string;
  legend: string;
  value: string;
  options: string[][];
  onChange: (value: string) => void;
}) {
  return (
    <fieldset className="preference-options">
      <legend className="visually-hidden">{legend}</legend>
      {options.map(([key, label]) => (
        <label key={key}>
          <input
            type="radio"
            name={name}
            value={key}
            checked={value === key}
            onChange={() => onChange(key)}
          />
          <span>{label}</span>
        </label>
      ))}
    </fieldset>
  );
}
