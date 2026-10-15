"use client";
import Link from "next/link";
import { useState } from "react";
import { api } from "./lib";
import { Icon } from "./ui";
import WorkflowDemo from "./workflow-demo";
export default function Landing() {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function start() {
    setBusy(true);
    setError("");
    try {
      await api("/auth/demo", {});
      window.location.assign("/workspace");
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }
  return (
    <>
      <nav className="public-nav">
        <Link href="/" className="wordmark">
          TrialOps<span>✳</span>
        </Link>
        <div className="public-links">
          <a href="#how-it-works">How it works</a>
          <a href="#use-cases">Use cases</a>
          <Link href="/guide">Guide</Link>
        </div>
        <Link href="/sign-in" className="quiet-link">
          Sign in
        </Link>
        <button onClick={start} disabled={busy} aria-busy={busy}>
          {busy ? "Preparing…" : "Try sample workspace"}{" "}
          <Icon name="arrow" size={15} />
        </button>
      </nav>
      <main id="main-content">
        <section className="landing-hero">
          <div>
            <p className="eyebrow">FOR CLINICAL OPERATIONS SUPPORT</p>
            <h1>
              Every issue.
              <br />
              <em>Clear evidence.</em>
              <br />A considered next step.
            </h1>
            <p className="hero-lead">
              Bring the issue, find the right procedure, and review the
              evidence. TrialOps keeps the investigation and every human
              decision together.
            </p>
            <div className="actions">
              <button onClick={start} disabled={busy} aria-busy={busy}>
                Explore a sample case <Icon name="arrow" size={17} />
              </button>
              <Link className="button outline" href="/sign-in?mode=register">
                Create a workspace
              </Link>
            </div>
            <p className="subtle">
              No account needed to explore. Your sample workspace is isolated
              and expires after 24 hours.
            </p>
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            <div className="hero-pills">
              <span>
                <Icon name="file" size={15} />
                Cited procedures
              </span>
              <span>
                <Icon name="shield" size={15} />
                Human review
              </span>
              <span>
                <Icon name="history" size={15} />
                Saved decisions
              </span>
            </div>
          </div>
          <div
            className="product-preview"
            aria-label="Illustrative investigation preview"
          >
            <div className="preview-chrome">
              <span>Sample investigation</span>
            </div>
            <div className="preview-body">
              <div className="preview-tag">Illustrative sample · CT-204</div>
              <h2>
                Certificate missing
                <br />
                from the binder.
              </h2>

              <WorkflowDemo />
              <div className="preview-footer">
                <span className="badge pending">Awaiting review</span>

              </div>
            </div>
          </div>
        </section>
        <section className="value-strip">
          <span>Procedures over guesswork.</span>
          <span>Records over assumptions.</span>
          <span>People make the decision.</span>
        </section>
        <section id="how-it-works" className="marketing-section">
          <p className="eyebrow">A COMPLETE SUPPORT WORKFLOW</p>
          <h2>
            From the first question
            <br />
            to the <em>final decision.</em>
          </h2>
          <div className="three-grid">
            {[
              [
                "01",
                "Describe the issue",
                "Choose the study and site, add the operational details, and confirm the category and priority.",
              ],
              [
                "02",
                "Gather the evidence",
                "Retrieve applicable procedures and scoped records. Review citations, unverified conditions, and drafts.",
              ],
              [
                "03",
                "Record what happened",
                "Approve or reject the recommendation. Resolve the case separately and keep a searchable activity trail.",
              ],
            ].map(([n, t, d]) => (
              <article className="feature-card" key={n}>
                <span className="step-num">{n}</span>
                <h3>{t}</h3>
                <p>{d}</p>
              </article>
            ))}
          </div>
        </section>
        <section id="use-cases" className="marketing-section tinted">
          <p className="eyebrow">
            ONE WORKSPACE, DIFFERENT OPERATIONAL QUESTIONS
          </p>
          <h2>
            The work behind
            <br />
            <em>keeping studies moving.</em>
          </h2>
          <div className="three-grid">
            {[
              [
                "file",
                "Documents & certificates",
                "Review upload receipts, processing status, and binder visibility.",
              ],
              [
                "history",
                "Binder synchronization",
                "Compare timestamps and inspect recorded job states.",
              ],
              [
                "shield",
                "Access & signatures",
                "Find the procedures for invitation checks and pending signature requests.",
              ],
            ].map(([i, t, d]) => (
              <article className="feature-card" key={t}>
                <Icon name={i} size={25} />
                <h3>{t}</h3>
                <p>{d}</p>
              </article>
            ))}
          </div>
        </section>
        <section className="marketing-section two-grid">
          <div>
            <p className="eyebrow">KNOWLEDGE YOU CAN MAINTAIN</p>
            <h2>
              Your procedures.
              <br />
              <em>Preserved in context.</em>
            </h2>
            <p>
              Upload a text-based PDF, Markdown, or plain-text procedure. Review
              the extracted text, save a version, and use it in new
              investigations. Earlier investigations keep the evidence they
              actually used.
            </p>
            <Link href="/guide" className="text-link">
              Read the product guide <Icon name="arrow" size={16} />
            </Link>
          </div>
          <div className="principle-card">
            <h3>
              When evidence is missing,
              <br />
              the answer should say so.
            </h3>
            <p>
              Insufficient-evidence recommendations cannot be approved.
              Historical snapshots do not establish a root cause. Drafts remain
              unsent.
            </p>
            <span className="badge">Built into the workflow</span>
          </div>
        </section>
        <section className="marketing-section faq">
          <p className="eyebrow">BEFORE YOU START</p>
          <h2>A few useful answers.</h2>
          {[
            [
              "Can I try it without an account?",
              "Yes. Try sample workspace creates an isolated, temporary workspace with synthetic cases and procedures.",
            ],
            [
              "Is this for patient care?",
              "No. TrialOps supports operational evaluation. Do not enter patient records, personal health information, or use it for clinical decisions.",
            ],
            [
              "Does it use a language model?",
              "Deployments can use a local Ollama model for source selection and semantic retrieval. Procedure mode uses explicit text matching without an LLM; the application displays the mode used.",
            ],
            [
              "Does approving send an escalation?",
              "No. Approval records a review decision. Draft copying, case resolution, and external action are separate concepts; this release does not send messages or modify operational systems.",
            ],
          ].map(([q, a]) => (
            <details key={q}>
              <summary>{q}</summary>
              <p>{a}</p>
            </details>
          ))}
        </section>
        <section className="final-cta">
          <p className="eyebrow">START WITH ONE ISSUE</p>
          <h2>
            Less searching.
            <br />
            <em>More clarity.</em>
          </h2>
          <button onClick={start} disabled={busy} aria-busy={busy}>
            Explore a sample case <Icon name="arrow" size={17} />
          </button>
        </section>
      </main>
      <footer className="public-footer">
        <Link href="/" className="wordmark">
          TrialOps<span>✳</span>
        </Link>
        <Link href="/guide">Guide & data policy</Link>
        <Link href="/sign-in">Sign in</Link>
        <span>Operational evaluation · No patient data</span>
      </footer>
    </>
  );
}
