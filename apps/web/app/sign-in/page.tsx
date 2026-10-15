"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "../lib";
import { Icon } from "../ui";
import { readPreferences } from "../workspace-components";
export default function SignIn() {
  const [mode, setMode] = useState("login"),
    [name, setName] = useState(""),
    [email, setEmail] = useState(""),
    [password, setPassword] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("mode") === "register")
      setMode("register");
  }, []);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/auth/" + mode, {
        email,
        password,
        ...(mode === "register" ? { name } : {}),
      });
      const me = await api("/auth/me");
      window.location.assign(readPreferences(me.user_id).startPage === "cases" ? "/workspace/cases" : "/workspace");
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }
  return (
    <main id="main-content" className="auth-page auth-split">
      <aside className="auth-story">
      <Link className="wordmark" href="/">
        TrialOps<span>✳</span>
      </Link>
        <h2>From issue<br/>to evidence.</h2><p>A clear workspace for operational questions, documented checks, and your decisions.</p>
        <figure className="flow-example" aria-label="Example workflow: issue, evidence, human review"><figcaption>Example workflow · illustrative, not live activity</figcaption><ol>{[["Issue","Binder sync stalled at a site","Example: submitted"],["Evidence","Procedure and recorded conditions, cited","Example: 2 sources"],["Human review","You decide. Resolve separately.","Example: awaiting review"]].map(([title,text,status],i)=><li key={title}><span className="flow-num" aria-hidden="true">{i+1}</span><div><strong>{title}</strong><small>{text}</small></div><em>{status}</em></li>)}</ol></figure>
        <footer>Evidence first. Human reviewed.</footer>
      </aside>
      <section className="auth-form-area">
      <div className="auth-card">
        <p className="eyebrow">YOUR OPERATIONS WORKSPACE</p>
        <h1>{mode === "login" ? "Welcome back." : "Create your workspace."}</h1>
        <p>
          {mode === "login"
            ? "Sign in to reopen your cases and saved decisions."
            : "Start a workspace for your team."}
        </p>
        <div className="tabs" role="tablist" aria-label="Account access" onKeyDown={e=>{if(!["ArrowLeft","ArrowRight","Home","End"].includes(e.key))return;e.preventDefault();const next=e.key==="Home"?"login":e.key==="End"?"register":mode==="login"?"register":"login";setMode(next);setError("");(e.currentTarget.querySelector(`[data-mode="${next}"]`) as HTMLButtonElement)?.focus();}}>
          <button
            role="tab" id="auth-login" data-mode="login" aria-controls="account-form" aria-selected={mode==="login"} tabIndex={mode==="login"?0:-1}
            className={mode === "login" ? "active" : ""}
            onClick={() => {
              setMode("login");
              setError("");
            }}
          >
            Sign in
          </button>
          <button
            role="tab" id="auth-register" data-mode="register" aria-controls="account-form" aria-selected={mode==="register"} tabIndex={mode==="register"?0:-1}
            className={mode === "register" ? "active" : ""}
            onClick={() => {
              setMode("register");
              setError("");
            }}
          >
            Create workspace
          </button>
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <form onSubmit={submit} id="account-form" role="tabpanel" aria-labelledby={mode==="login"?"auth-login":"auth-register"}>
          {mode === "register" && (
            <label>
              Your name
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={100}
                required
                autoComplete="name"
              />
            </label>
          )}
          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              maxLength={254}
              autoComplete="email"
            />
          </label>
          <label>
            Password
            <input
              type="password"
              aria-label="Password"
              aria-describedby="password-help"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={12}
              maxLength={128}
              required
              autoComplete={
                mode === "login" ? "current-password" : "new-password"
              }
            />
            <small id="password-help">At least 12 characters. Store your password securely.</small>
          </label>
          <button disabled={busy} aria-busy={busy}>
            {busy
              ? (mode === "login" ? "Signing in…" : "Creating workspace…")
              : mode === "login"
                ? "Sign in"
                : "Create workspace"}
          </button>
        </form>
        <p className="auth-recovery"><Link className="text-link" href="/account-access">Forgot password?</Link></p>
        <details className="auth-policy"><summary>Account & data information</summary><p className="subtle">Email identifies your account. Verify it from Settings after signing in. Password recovery requires configured email delivery. Use non-patient operational information. Read the <Link href="/guide#data-policy">data policy</Link> before uploading.</p></details>
        <div className="auth-links"><Link href="/" className="text-link">← Back to home</Link><Link href="/guide" className="text-link">Product guide</Link></div>
      </div>
      </section>
    </main>
  );
}
