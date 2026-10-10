import hmac, json, logging, os, re, secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    File,
)
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb
from db import connect, query, one, secret
from security import actor, require, digest, password_hash, password_ok, rate
from models import *
from seed import seed, operations
from content import chunks, extract
from operational_evidence import validate_operations
from workflows import save_snapshot, procedure_impact

app = FastAPI(
    title="TrialOps",
    version="2.0.0",
    docs_url="/docs" if os.getenv("ENABLE_API_DOCS") == "true" else None,
    redoc_url=None,
)


@app.middleware("http")
async def protection(request, call_next):
    if request.url.path not in ("/health",):
        key = secret("INTERNAL_KEY")
        if len(key) < 32 or not hmac.compare_digest(
            request.headers.get("x-internal-key", ""), key
        ):
            return JSONResponse(
                {"detail": "Access through the TrialOps web application."},
                status_code=403,
            )
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            length = request.headers.get("content-length")
            if length and (
                not length.isdigit() or int(length) > 2 * 1024 * 1024 + 10000
            ):
                return JSONResponse(
                    {"detail": "Request is too large."}, status_code=413
                )
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
def health():
    one("SELECT 1")
    return {"status": "ok", "version": "2.0.0"}


def session(response, user, workspace, guest=False):
    token = secrets.token_urlsafe(48)
    seconds = 86400 if guest else 7 * 86400
    query(
        "INSERT INTO sessions VALUES(%s,%s,%s,%s) RETURNING token_hash",
        (
            digest(token),
            user,
            workspace,
            datetime.now(timezone.utc) + timedelta(seconds=seconds),
        ),
    )
    response.set_cookie(
        "trialops_session",
        token,
        max_age=seconds,
        httponly=True,
        secure=os.getenv("COOKIE_SECURE") == "true",
        samesite="lax",
        path="/",
    )


def workspace(c, user, name, demo):
    w = uuid4()
    c.execute(
        "INSERT INTO workspaces(id,name,demo,expires_at) VALUES(%s,%s,%s,%s)",
        (
            w,
            name,
            demo,
            datetime.now(timezone.utc) + timedelta(days=1) if demo else None,
        ),
    )
    c.execute("INSERT INTO memberships VALUES(%s,%s,'owner')", (w, user))
    seed(c, w)
    return w


def event(c, a, case, event_type, notes="", run_id=None, payload=None):
    return c.execute(
        """INSERT INTO case_events(workspace_id,case_id,run_id,actor_id,actor_name,event_type,notes,payload)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        (
            a["workspace_id"],
            case,
            run_id,
            a["user_id"],
            a["name"],
            event_type,
            notes,
            Jsonb(payload or {}),
        ),
    ).fetchone()


def get_case(a, case_id, c=None, lock=False):
    sql = "SELECT c.*,u.name AS owner_name FROM cases c LEFT JOIN users u ON u.id=c.owner_id WHERE c.workspace_id=%s AND c.id=%s"
    if lock:
        sql += " FOR UPDATE OF c"
    row = (
        c.execute(sql, (a["workspace_id"], case_id)).fetchone()
        if c
        else one(sql, (a["workspace_id"], case_id))
    )
    if not row:
        raise HTTPException(404, "Case not found in this workspace.")
    return row


def get_run(a, run_id, c=None, lock=False):
    sql = "SELECT r.*,u.name AS reviewer FROM runs r LEFT JOIN users u ON u.id=r.reviewer_id WHERE r.workspace_id=%s AND r.id=%s"
    if lock:
        sql += " FOR UPDATE OF r"
    row = (
        c.execute(sql, (a["workspace_id"], run_id)).fetchone()
        if c
        else one(sql, (a["workspace_id"], run_id))
    )
    if not row:
        raise HTTPException(404, "Investigation not found in this workspace.")
    return row


@app.post("/auth/demo")
def demo(request: Request, response: Response):
    if os.getenv("ENABLE_DEMO", "true") != "true":
        raise HTTPException(403, "Sample workspaces are disabled.")
    rate("demo:" + request.headers.get("x-client-ip", "unknown"), int(os.getenv("DEMO_IP_HOURLY_LIMIT", "10")))
    rate("demo-global", int(os.getenv("DEMO_HOURLY_LIMIT", "100")))
    u = uuid4()
    with connect() as c:
        c.execute(
            "INSERT INTO users(id,email,name,guest) VALUES(%s,%s,'Sample visitor',true)",
            (u, f"{u}@sample.invalid"),
        )
        w = workspace(c, u, "Your sample workspace", True)
    session(response, u, w, True)
    return {"workspace_id": w, "message": "Your isolated sample workspace is ready."}


@app.post("/auth/register", status_code=201)
def register(body: Register, request: Request, response: Response):
    if os.getenv("ENABLE_SIGNUP", "true") != "true":
        raise HTTPException(403, "Account registration is disabled.")
    rate("register:" + request.headers.get("x-client-ip", "unknown"), int(os.getenv("REGISTER_IP_HOURLY_LIMIT", "5")))
    rate("register-global", int(os.getenv("SIGNUP_HOURLY_LIMIT", "50")))
    hashed = password_hash(body.password)
    u = uuid4()
    try:
        with connect() as c:
            c.execute(
                "INSERT INTO users(id,email,name,password_hash) VALUES(%s,%s,%s,%s)",
                (u, body.email, body.name, hashed),
            )
            w = workspace(c, u, body.name + "'s workspace", False)
    except Exception as exc:
        import psycopg

        if isinstance(exc, psycopg.errors.UniqueViolation):
            raise HTTPException(
                409, "That email already has an account. Sign in instead."
            )
        raise
    session(response, u, w)
    return {"workspace_id": w}


@app.post("/auth/login")
def login(body: Credentials, request: Request, response: Response):
    rate("login:" + request.headers.get("x-client-ip", "unknown"), 20, 900)
    rate("login-email:" + body.email, 10, 900)
    user = one("SELECT * FROM users WHERE email=%s AND NOT guest", (body.email,))
    if not password_ok(
        body.password, user["password_hash"] if user else "00" * 16 + ":" + "00" * 32
    ):
        raise HTTPException(401, "Email or password is incorrect.")
    membership = one(
        "SELECT workspace_id FROM memberships WHERE user_id=%s ORDER BY workspace_id LIMIT 1",
        (user["id"],),
    )
    if not membership:
        raise HTTPException(
            403, "No workspace membership. Contact the workspace owner."
        )
    session(response, user["id"], membership["workspace_id"])
    return {"workspace_id": membership["workspace_id"]}


@app.get("/auth/me")
def me(a=Depends(actor)):
    return {
        **a,
        "workspaces": query(
            """SELECT w.id,w.name,m.role FROM workspaces w JOIN memberships m ON m.workspace_id=w.id WHERE m.user_id=%s""",
            (a["user_id"],),
        ),
        "ai_mode": os.getenv("AI_MODE", "procedure"),
        "data_policy": "Operational evaluation only. Do not upload patient or personal health information.",
    }


@app.post("/auth/logout")
def logout(request: Request, response: Response):
    query(
        "DELETE FROM sessions WHERE token_hash=%s RETURNING token_hash",
        (digest(request.cookies.get("trialops_session", "")),),
    )
    response.delete_cookie("trialops_session", path="/")
    return {"status": "signed_out"}


@app.post("/auth/switch")
def switch(body: Switch, request: Request, a=Depends(actor)):
    if not one(
        "SELECT role FROM memberships WHERE workspace_id=%s AND user_id=%s",
        (body.workspace_id, a["user_id"]),
    ):
        raise HTTPException(403, "Workspace membership required.")
    query(
        "UPDATE sessions SET workspace_id=%s WHERE token_hash=%s RETURNING workspace_id",
        (body.workspace_id, digest(request.cookies["trialops_session"])),
    )
    return {"workspace_id": body.workspace_id}


@app.get("/members")
def members(a=Depends(actor)):
    return query(
        "SELECT u.id,u.name,u.email,m.role FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.workspace_id=%s ORDER BY u.name",
        (a["workspace_id"],),
    )


@app.post("/invitations")
def invite(body: Invite, a=Depends(actor)):
    require(a, ("owner",))
    if a["guest"]:
        raise HTTPException(403, "Create a permanent account to invite teammates.")
    rate("invite:" + str(a["workspace_id"]), 20)
    code = secrets.token_urlsafe(32)
    query(
        "INSERT INTO invitations VALUES(%s,%s,%s,now()+interval '1 day',NULL) RETURNING role",
        (digest(code), a["workspace_id"], body.role),
    )
    return {
        "code": code,
        "role": body.role,
        "expires_in_hours": 24,
        "message": "Share this code directly with your teammate. No message was sent.",
    }


@app.post("/invitations/accept")
def accept(body: InviteAccept, a=Depends(actor)):
    if a["guest"]:
        raise HTTPException(403, "Sign in to a permanent account first.")
    with connect() as c:
        invitation = c.execute(
            "SELECT * FROM invitations WHERE token_hash=%s AND used_at IS NULL AND expires_at>now() FOR UPDATE",
            (digest(body.code),),
        ).fetchone()
        if not invitation:
            raise HTTPException(422, "Invitation is invalid, expired, or already used.")
        c.execute(
            "INSERT INTO memberships VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
            (invitation["workspace_id"], a["user_id"], invitation["role"]),
        )
        c.execute(
            "UPDATE invitations SET used_at=now() WHERE token_hash=%s",
            (digest(body.code),),
        )
    return {"workspace_id": invitation["workspace_id"]}


@app.get("/catalog")
def catalog(a=Depends(actor)):
    return {
        "studies": query(
            "SELECT id,name FROM studies WHERE workspace_id=%s ORDER BY id",
            (a["workspace_id"],),
        ),
        "sites": query(
            "SELECT id,name,study_id FROM sites WHERE workspace_id=%s ORDER BY id",
            (a["workspace_id"],),
        ),
    }


@app.post("/catalog/studies", status_code=201)
def add_study(body: Study, a=Depends(actor)):
    require(a, ("owner",))
    rate("catalog:" + str(a["workspace_id"]), 30)
    with connect() as c:
        c.execute(
            "SELECT id FROM workspaces WHERE id=%s FOR UPDATE", (a["workspace_id"],)
        )
        if (
            c.execute(
                "SELECT count(*) AS n FROM studies WHERE workspace_id=%s",
                (a["workspace_id"],),
            ).fetchone()["n"]
            >= 50
        ):
            raise HTTPException(422, "Workspace study limit reached (50).")
        if c.execute(
            "SELECT id FROM studies WHERE workspace_id=%s AND id=%s",
            (a["workspace_id"], body.id),
        ).fetchone():
            raise HTTPException(409, "That study ID is already in this workspace.")
        return c.execute(
            "INSERT INTO studies VALUES(%s,%s,%s) RETURNING *",
            (a["workspace_id"], body.id, body.name),
        ).fetchone()


@app.post("/catalog/sites", status_code=201)
def add_site(body: Site, a=Depends(actor)):
    require(a, ("owner",))
    rate("catalog:" + str(a["workspace_id"]), 30)
    with connect() as c:
        c.execute(
            "SELECT id FROM workspaces WHERE id=%s FOR UPDATE", (a["workspace_id"],)
        )
        if not c.execute(
            "SELECT id FROM studies WHERE workspace_id=%s AND id=%s",
            (a["workspace_id"], body.study_id),
        ).fetchone():
            raise HTTPException(422, "Choose a study from this workspace.")
        if (
            c.execute(
                "SELECT count(*) AS n FROM sites WHERE workspace_id=%s",
                (a["workspace_id"],),
            ).fetchone()["n"]
            >= 200
        ):
            raise HTTPException(422, "Workspace site limit reached (200).")
        if c.execute(
            "SELECT id FROM sites WHERE workspace_id=%s AND id=%s",
            (a["workspace_id"], body.id),
        ).fetchone():
            raise HTTPException(409, "That site ID is already in this workspace.")
        return c.execute(
            "INSERT INTO sites VALUES(%s,%s,%s,%s) RETURNING *",
            (a["workspace_id"], body.id, body.study_id, body.name),
        ).fetchone()


@app.get("/dashboard")
def dashboard(a=Depends(actor)):
    w = a["workspace_id"]
    counts = one(
        """SELECT count(*) FILTER(WHERE status='open') AS open_cases,count(*) FILTER(WHERE status='resolved') AS resolved_cases,
     count(*) FILTER(WHERE status='open' AND due_at<now()) AS overdue FROM cases WHERE workspace_id=%s""",
        (w,),
    )
    runs = one(
        "SELECT count(*) AS investigations,count(*) FILTER(WHERE decision='approved') AS approved,count(*) FILTER(WHERE decision IS NULL) AS pending FROM runs WHERE workspace_id=%s",
        (w,),
    )
    roi = one(
        """SELECT count(*) AS scenario_count,coalesce(sum(baseline-assisted),0) AS estimated_minutes_saved,
       coalesce(sum((baseline-assisted)*hourly_cost/60-ai_cost),0) AS estimated_net_capacity_value FROM roi_scenarios WHERE workspace_id=%s""",
        (w,),
    )
    overdue = query(
        "SELECT id,title,study_id,site_id,due_at,count(*) OVER() AS total FROM cases WHERE workspace_id=%s AND status='open' AND due_at<now() ORDER BY due_at,id LIMIT 5",
        (w,),
    )
    unassigned = query(
        "SELECT id,title,study_id,site_id,count(*) OVER() AS total FROM cases WHERE workspace_id=%s AND status='open' AND priority='high' AND owner_id IS NULL ORDER BY created_at DESC,id LIMIT 5",
        (w,),
    )
    reviews = query(
        """SELECT r.id,r.case_id,c.title,r.created_at,count(*) OVER() AS total
        FROM runs r JOIN cases c ON c.workspace_id=r.workspace_id AND c.id=r.case_id
        WHERE r.workspace_id=%s AND c.status='open' AND r.decision IS NULL
        AND NOT EXISTS(SELECT 1 FROM runs newer WHERE newer.workspace_id=r.workspace_id AND newer.case_id=r.case_id AND (newer.created_at,newer.id)>(r.created_at,r.id))
        ORDER BY r.created_at,r.id LIMIT 5""",
        (w,),
    )
    attention = {
        name: {"items": rows, "total": rows[0]["total"] if rows else 0}
        for name, rows in [
            ("overdue", overdue),
            ("unassigned", unassigned),
            ("reviews", reviews),
        ]
    }
    recent = query(
        "SELECT id,title,status,priority,study_id,site_id,updated_at FROM cases WHERE workspace_id=%s ORDER BY updated_at DESC,id LIMIT 5",
        (w,),
    )
    return {**counts, **runs, **roi, "attention": attention, "recent_cases": recent}


@app.get("/cases")
def cases(
    status: Literal["open", "resolved"] = "open",
    q: str = Query(default="", max_length=200),
    priority: str = "",
    offset: int = Query(default=0, ge=0),
    view: Literal["all", "mine", "review", "overdue", "unassigned"] = "all",
    a=Depends(actor),
):
    # Numeric aliases refer to a case ID, not a study/site number or CASE-10.
    number = re.fullmatch(r"(?:case[\s-]*)?([0-9]+)", q.strip(), re.IGNORECASE)
    search = (
        "c.id=%s"
        if number
        else "(c.title||' '||c.id||' '||c.study_id||' '||c.site_id) ILIKE %s"
    )
    needle = (
        "CASE-" + (number[1].lstrip("0") or "0") if number else "%" + q.strip() + "%"
    )
    params = (a["workspace_id"], status, needle, priority, priority)
    condition = (
        "c.workspace_id=%s AND c.status=%s AND "
        + search
        + " AND (%s='' OR c.priority=%s)"
    )
    if view == "mine":
        condition += " AND c.owner_id=%s"
        params += (a["user_id"],)
    elif view == "overdue":
        condition += " AND c.status='open' AND c.due_at < now()"
    elif view == "unassigned":
        condition += " AND c.status='open' AND c.priority='high' AND c.owner_id IS NULL"
    elif view == "review":
        condition += """ AND c.status='open' AND EXISTS(
          SELECT 1 FROM runs latest WHERE latest.workspace_id=c.workspace_id AND latest.case_id=c.id AND latest.decision IS NULL
          AND NOT EXISTS(SELECT 1 FROM runs newer WHERE newer.workspace_id=latest.workspace_id AND newer.case_id=latest.case_id
          AND (newer.created_at,newer.id)>(latest.created_at,latest.id)))"""
    total = one("SELECT count(*) AS n FROM cases c WHERE " + condition, params)["n"]
    rows = query(
        """SELECT c.*,u.name AS owner_name,
          (SELECT COALESCE(r.decision,'pending') FROM runs r
           WHERE r.workspace_id=c.workspace_id AND r.case_id=c.id
           ORDER BY r.created_at DESC,r.id DESC LIMIT 1) AS review_status
          FROM cases c LEFT JOIN users u ON u.id=c.owner_id WHERE """
        + condition
        + " ORDER BY c.updated_at DESC,c.id LIMIT 25 OFFSET %s",
        (*params, offset),
    )
    return {"items": rows, "total": total, "offset": offset, "limit": 25}


@app.post("/cases", status_code=201)
def create_case(body: NewCase, a=Depends(actor)):
    rate("case:" + str(a["workspace_id"]), 50)
    with connect() as c:
        c.execute(
            "SELECT id FROM workspaces WHERE id=%s FOR UPDATE", (a["workspace_id"],)
        )
        if body.submission_id:
            old = c.execute(
                "SELECT * FROM cases WHERE workspace_id=%s AND submission_id=%s",
                (a["workspace_id"], body.submission_id),
            ).fetchone()
            if old:
                if any(
                    old[k] != getattr(body, k)
                    for k in (
                        "title",
                        "description",
                        "study_id",
                        "site_id",
                        "category",
                        "priority",
                        "due_at",
                    )
                ):
                    raise HTTPException(
                        409, "Submission identifier contains a different case."
                    )
                return old

        if not c.execute(
            "SELECT id FROM sites WHERE workspace_id=%s AND id=%s AND study_id=%s",
            (a["workspace_id"], body.site_id, body.study_id),
        ).fetchone():
            raise HTTPException(422, "Choose a site belonging to the selected study.")
        if (
            c.execute(
                "SELECT count(*) AS n FROM cases WHERE workspace_id=%s",
                (a["workspace_id"],),
            ).fetchone()["n"]
            >= 500
        ):
            raise HTTPException(422, "Workspace case limit reached (500).")
        cid = "CASE-" + str(uuid4())[:12]
        case = c.execute(
            """INSERT INTO cases(workspace_id,id,study_id,site_id,title,description,category,priority,due_at,submission_id)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (
                a["workspace_id"],
                cid,
                body.study_id,
                body.site_id,
                body.title,
                body.description,
                body.category,
                body.priority,
                body.due_at,
                body.submission_id,
            ),
        ).fetchone()
        event(c, a, cid, "case_created", "Case submitted by " + a["name"])
    return case


@app.get("/cases/{case_id}")
def detail(case_id: str, a=Depends(actor)):
    case = get_case(a, case_id)
    return {
        "case": case,
        "runs": query(
            "SELECT id,decision,model,created_at FROM runs WHERE workspace_id=%s AND case_id=%s ORDER BY created_at DESC LIMIT 100",
            (a["workspace_id"], case_id),
        ),
        "events": query(
            "SELECT * FROM case_events WHERE workspace_id=%s AND case_id=%s ORDER BY id",
            (a["workspace_id"], case_id),
        ),
        "job": one(
            "SELECT * FROM jobs WHERE workspace_id=%s AND target_id=%s AND kind='investigate' ORDER BY created_at DESC LIMIT 1",
            (a["workspace_id"], case_id),
        ),
    }


@app.post("/cases/{case_id}/assignment")
def assignment(case_id: str, body: Assignment, a=Depends(actor)):
    with connect() as c:
        old = get_case(a, case_id, c, True)
        if body.expected_updated_at and body.expected_updated_at != old["updated_at"]:
            raise HTTPException(409, "Assignment changed. Reload before saving.")
        if (
            body.owner_id
            and not c.execute(
                "SELECT role FROM memberships WHERE workspace_id=%s AND user_id=%s",
                (a["workspace_id"], body.owner_id),
            ).fetchone()
        ):
            raise HTTPException(422, "Assignee must be a member of this workspace.")
        c.execute(
            "UPDATE cases SET owner_id=%s,due_at=%s,updated_at=now() WHERE workspace_id=%s AND id=%s",
            (body.owner_id, body.due_at, a["workspace_id"], case_id),
        )
        event(
            c,
            a,
            case_id,
            "case_assignment_updated",
            payload={
                "owner_id": str(body.owner_id) if body.owner_id else None,
                "due_at": str(body.due_at) if body.due_at else None,
            },
        )
    return {"status": "saved"}


@app.post("/cases/{case_id}/notes")
def note(case_id: str, body: Note, a=Depends(actor)):
    with connect() as c:
        get_case(a, case_id, c)
        return event(c, a, case_id, "comment_added", body.notes)


@app.post("/cases/{case_id}/investigate", status_code=202)
def enqueue(case_id: str, a=Depends(actor)):
    rate("investigate:" + str(a["workspace_id"]), 20)
    with connect() as c:
        case = get_case(a, case_id, c, True)
        if case["status"] != "open":
            raise HTTPException(409, "Reopen the case before investigating.")
        existing = c.execute(
            "SELECT * FROM jobs WHERE workspace_id=%s AND kind='investigate' AND target_id=%s AND status IN ('queued','running')",
            (a["workspace_id"], case_id),
        ).fetchone()
        if existing:
            return existing
        return c.execute(
            "INSERT INTO jobs(id,workspace_id,actor_id,kind,target_id) VALUES(%s,%s,%s,'investigate',%s) RETURNING *",
            (uuid4(), a["workspace_id"], a["user_id"], case_id),
        ).fetchone()


@app.get("/jobs/{job_id}")
def job(job_id: UUID, a=Depends(actor)):
    result = one(
        "SELECT * FROM jobs WHERE workspace_id=%s AND id=%s",
        (a["workspace_id"], job_id),
    )
    if not result:
        raise HTTPException(404, "Job not found.")
    return result


@app.get("/runs")
def history(
    q: str = Query(default="", max_length=200),
    decision: str = "",
    offset: int = Query(default=0, ge=0),
    a=Depends(actor),
):
    condition = "r.workspace_id=%s AND (c.title||' '||r.case_id||' '||r.id::text) ILIKE %s AND (%s='' OR coalesce(r.decision,'pending')=%s)"
    params = (a["workspace_id"], "%" + q + "%", decision, decision)
    rows = query(
        "SELECT r.*,c.title FROM runs r JOIN cases c ON c.workspace_id=r.workspace_id AND c.id=r.case_id WHERE "
        + condition
        + " ORDER BY r.created_at DESC LIMIT 25 OFFSET %s",
        (*params, offset),
    )
    count = one(
        "SELECT count(*) AS n FROM runs r JOIN cases c ON c.workspace_id=r.workspace_id AND c.id=r.case_id WHERE "
        + condition,
        params,
    )["n"]
    return {"items": rows, "total": count}


@app.get("/runs/{run_id}")
def saved_run(run_id: UUID, a=Depends(actor)):
    return {
        "run": get_run(a, run_id),
        "events": query(
            "SELECT * FROM case_events WHERE workspace_id=%s AND run_id=%s ORDER BY id",
            (a["workspace_id"], run_id),
        ),
    }


@app.get("/runs/{run_id}/report.pdf")
def investigation_pdf(run_id: UUID, a=Depends(actor)):
    from report import build_report

    # Use the same scoped saved-run access as the JSON investigation endpoint.
    with connect() as c:
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        run = get_run(a, run_id, c)
        case = get_case(a, run["case_id"], c)
        events = c.execute(
            "SELECT * FROM case_events WHERE workspace_id=%s AND run_id=%s ORDER BY id",
            (a["workspace_id"], run_id),
        ).fetchall()
    pdf = build_report(run, events, case)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="trialops-investigation-{run_id}.pdf"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.post("/runs/{run_id}/decision")
def decision(run_id: UUID, body: Decision, a=Depends(actor)):
    require(a)
    with connect() as c:
        initial = get_run(a, run_id, c)
        get_case(a, initial["case_id"], c, True)
        run = get_run(a, run_id, c, True)
        if run["decision"]:
            raise HTTPException(409, "A review decision has already been recorded.")
        if (
            body.decision == "approved"
            and run["result"]["recommendation"]["status"] != "supported"
        ):
            raise HTTPException(
                422, "Insufficient-evidence recommendations cannot be approved."
            )
        c.execute(
            "UPDATE runs SET decision=%s,reviewer_id=%s,review_notes=%s,reviewed_at=now() WHERE workspace_id=%s AND id=%s",
            (body.decision, a["user_id"], body.notes, a["workspace_id"], run_id),
        )
        event(
            c, a, run["case_id"], "recommendation_" + body.decision, body.notes, run_id
        )
    return {"decision": body.decision, "external_actions_executed": []}


@app.post("/cases/{case_id}/resolve")
def resolve(case_id: str, body: Resolve, a=Depends(actor)):
    require(a)
    with connect() as c:
        case = get_case(a, case_id, c, True)
        if case["status"] != "open":
            raise HTTPException(409, "Case is already resolved.")
        if c.execute(
            "SELECT id FROM jobs WHERE workspace_id=%s AND target_id=%s AND kind='investigate' AND status IN ('queued','running')",
            (a["workspace_id"], case_id),
        ).fetchone():
            raise HTTPException(409, "Wait for the active investigation to finish.")
        run = get_run(a, body.run_id, c, True)
        if (
            run["case_id"] != case_id
            or run["decision"] != "approved"
            or run["result"]["recommendation"]["status"] != "supported"
        ):
            raise HTTPException(
                422, "Choose an approved, supported investigation for this case."
            )

        from release_api import refs
        from workflows import STATES

        if body.expected_updated_at != case["updated_at"]:
            raise HTTPException(409, "Case changed. Reload before resolving.")
        now = datetime.now(timezone.utc)
        cycle = c.execute(
            "SELECT created_at FROM case_events WHERE workspace_id=%s AND case_id=%s AND event_type='case_reopened' ORDER BY id DESC LIMIT 1",
            (a["workspace_id"], case_id),
        ).fetchone()
        cycle_start = cycle["created_at"] if cycle else case["created_at"]
        if body.verified_at > now or body.verified_at < cycle_start:
            raise HTTPException(
                422,
                "Verification time must be within the current open case cycle and cannot be in the future.",
            )
        refs(c, a, case_id, body.evidence_refs)
        evidence = c.execute(
            "SELECT * FROM case_evidence WHERE workspace_id=%s AND case_id=%s AND id=ANY(%s)",
            (a["workspace_id"], case_id, body.evidence_refs),
        ).fetchall()
        if not any(
            e["kind"] == "human_observation"
            and cycle_start <= e["observed_at"] <= body.verified_at
            for e in evidence
        ):
            raise HTTPException(
                422,
                "Record a human observation from the current case cycle. Historical snapshots alone cannot verify resolution.",
            )
        checks = c.execute(
            "SELECT * FROM investigation_checks WHERE workspace_id=%s AND case_id=%s AND run_id=%s",
            (a["workspace_id"], case_id, body.run_id),
        ).fetchall()
        if not checks or any(ch["status"] != "active" for ch in checks):
            raise HTTPException(
                422, "Activate the reviewed investigation checks before resolving."
            )
        items = [i for ch in checks for i in ch["items"]]
        if any(i["state"] == "not_checked" for i in items):
            raise HTTPException(
                422, "Complete the unchecked investigation checks before resolving."
            )
        if (
            any(i["state"] in {"needs_follow_up", "not_applicable"} for i in items)
            and len(body.exceptions.strip()) < 10
        ):
            raise HTTPException(
                422,
                "Explain unresolved follow-up or not-applicable exceptions in the resolution.",
            )
        c.execute(
            "UPDATE cases SET status='resolved',resolution=%s,resolved_by=%s,resolved_at=now(),updated_at=now() WHERE workspace_id=%s AND id=%s",
            (body.notes, a["user_id"], a["workspace_id"], case_id),
        )
        event(
            c,
            a,
            case_id,
            "case_resolved",
            body.notes,
            body.run_id,
            {
                "reviewer_id": str(a["user_id"]),
                "reviewer_name": a["name"],
                "verified_at": body.verified_at.isoformat(),
                "exceptions": body.exceptions,
                "evidence": [
                    {
                        **e,
                        "id": str(e["id"]),
                        "workspace_id": str(e["workspace_id"]),
                        "actor_id": str(e["actor_id"]) if e["actor_id"] else None,
                        "observed_at": e["observed_at"].isoformat(),
                        "created_at": e["created_at"].isoformat(),
                    }
                    for e in evidence
                ],
                "checks": [
                    {
                        "id": str(ch["id"]),
                        "version": ch["version"],
                        "sources": ch["sources"],
                        "items": ch["items"],
                    }
                    for ch in checks
                ],
                "historical_evidence_is_current_verification": False,
            },
        )
    return {"status": "resolved", "external_actions_executed": []}


@app.post("/cases/{case_id}/reopen")
def reopen(case_id: str, body: Note, a=Depends(actor)):
    require(a)
    with connect() as c:
        case = get_case(a, case_id, c, True)
        if case["status"] != "resolved":
            raise HTTPException(409, "Only resolved cases can be reopened.")
        c.execute(
            "UPDATE cases SET status='open',resolution=NULL,resolved_by=NULL,resolved_at=NULL,updated_at=now() WHERE workspace_id=%s AND id=%s",
            (a["workspace_id"], case_id),
        )
        event(
            c,
            a,
            case_id,
            "case_reopened",
            body.notes,
            payload={"previous_resolution": case["resolution"]},
        )
    return {"status": "open"}


@app.get("/knowledge")
def knowledge(a=Depends(actor)):
    return query(
        "SELECT * FROM knowledge WHERE workspace_id=%s ORDER BY updated_at DESC,id",
        (a["workspace_id"],),
    )


@app.post("/knowledge/extract")
def upload(file: UploadFile = File(...), a=Depends(actor)):
    require(a, ("owner",))
    rate("upload:" + str(a["workspace_id"]), 20)
    data = file.file.read(2 * 1024 * 1024 + 1)
    return extract(file.filename or "document.txt", data)


def save_knowledge(a, body, article_id=None):
    require(a, ("owner",))
    rate("knowledge:" + str(a["workspace_id"]), 30)
    with connect() as c:
        if article_id:
            old = c.execute(
                "SELECT * FROM knowledge WHERE workspace_id=%s AND id=%s FOR UPDATE",
                (a["workspace_id"], article_id),
            ).fetchone()
            if not old:
                raise HTTPException(404, "Knowledge article not found.")
            if body.expected_version != old["version"]:
                raise HTTPException(
                    409, "This procedure changed. Reload it before saving."
                )
            c.execute(
                "INSERT INTO procedure_versions(workspace_id,article_id,version,title,content,category) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (
                    a["workspace_id"],
                    article_id,
                    old["version"],
                    old["title"],
                    old["content"],
                    old["category"],
                ),
            )
            version = old["version"] + 1
            c.execute(
                "UPDATE knowledge SET title=%s,content=%s,category=%s,version=%s,indexing_status='queued',indexing_error=NULL,updated_at=now() WHERE workspace_id=%s AND id=%s",
                (
                    body.title,
                    body.content,
                    body.category,
                    version,
                    a["workspace_id"],
                    article_id,
                ),
            )
        else:
            if (
                c.execute(
                    "SELECT count(*) AS n FROM knowledge WHERE workspace_id=%s",
                    (a["workspace_id"],),
                ).fetchone()["n"]
                >= 100
            ):
                raise HTTPException(
                    422, "Workspace knowledge limit reached (100 articles)."
                )
            article_id = "KB-" + str(uuid4())[:12]
            version = 1
            c.execute(
                "INSERT INTO knowledge(workspace_id,id,title,content,category) VALUES(%s,%s,%s,%s,%s)",
                (
                    a["workspace_id"],
                    article_id,
                    body.title,
                    body.content,
                    body.category,
                ),
            )
        c.execute(
            "INSERT INTO procedure_versions(workspace_id,article_id,version,title,content,category,actor_id) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (
                a["workspace_id"],
                article_id,
                version,
                body.title,
                body.content,
                body.category,
                a["user_id"],
            ),
        )
        if article_id and version > 1:
            procedure_impact(c, a["workspace_id"], article_id, version)
        for i, text in enumerate(chunks(body.content), 1):
            c.execute(
                "INSERT INTO knowledge_chunks(workspace_id,article_id,version,number,content) VALUES(%s,%s,%s,%s,%s)",
                (a["workspace_id"], article_id, version, i, text),
            )
        c.execute(
            "INSERT INTO jobs(id,workspace_id,actor_id,kind,target_id) VALUES(%s,%s,%s,'index',%s) ON CONFLICT DO NOTHING",
            (uuid4(), a["workspace_id"], a["user_id"], article_id),
        )
    return {"id": article_id, "version": version}


@app.post("/knowledge", status_code=201)
def add_knowledge(body: Knowledge, a=Depends(actor)):
    return save_knowledge(a, body)


@app.post("/knowledge/{article_id}")
def edit_knowledge(article_id: str, body: Knowledge, a=Depends(actor)):
    return save_knowledge(a, body, article_id)


@app.post("/knowledge/{article_id}/archive")
def archive(article_id: str, body: Archive, a=Depends(actor)):
    require(a, ("owner",))
    rows = query(
        "UPDATE knowledge SET archived=%s,updated_at=now() WHERE workspace_id=%s AND id=%s AND version=%s RETURNING id",
        (body.archived, a["workspace_id"], article_id, body.expected_version),
    )
    if not rows:
        raise HTTPException(
            409, "Procedure not found or version changed. Reload and try again."
        )
    return rows[0]


@app.get("/operations")
def records(a=Depends(actor)):
    return query(
        "SELECT * FROM operations WHERE workspace_id=%s ORDER BY study_id,site_id",
        (a["workspace_id"],),
    )


@app.get("/operations/example")
def record_example(a=Depends(actor)):
    return {"study_id": "CT-204", "site_id": "SITE-104", "evidence": operations()}


@app.post("/operations")
def import_records(body: Operations, a=Depends(actor)):
    require(a, ("owner",))
    if len(json.dumps(body.evidence)) > 100000:
        raise HTTPException(413, "Snapshot is too large.")
    for kind in ["synchronization", "document_processing"]:
        group = body.evidence.get(kind)
        if not isinstance(group, dict) or len(group.get("records", [])) > 10:
            raise HTTPException(
                422, "Provide both record groups with at most 10 records each."
            )
    try:
        validate_operations(
            {"study_id": body.study_id, "site_id": body.site_id}, body.evidence
        )
    except Exception:
        raise HTTPException(
            422,
            "Invalid snapshot. Check study/site scope, matching snapshot IDs, statuses, timestamps, and synthetic=true.",
        )
    if not one(
        "SELECT id FROM sites WHERE workspace_id=%s AND study_id=%s AND id=%s",
        (a["workspace_id"], body.study_id, body.site_id),
    ):
        raise HTTPException(422, "Study and site assignment mismatch.")
    with connect() as c:
        c.execute(
            "SELECT id FROM workspaces WHERE id=%s FOR UPDATE", (a["workspace_id"],)
        )
        row, created = save_snapshot(
            c,
            a["workspace_id"],
            body.study_id,
            body.site_id,
            body.evidence,
            a["user_id"],
        )
    return {
        "status": "saved" if created else "already_saved",
        "snapshot_id": row["id"],
        "message": "New investigations use this snapshot. Saved investigations retain their original records.",
    }


@app.post("/intake/classify")
def classify(body: Classification, a=Depends(actor)):
    from tools import terms
    from seed import ARTICLES

    needle = terms(body.title + " " + body.description)
    scored = sorted(
        [(len(needle & terms(x["title"])), x) for x in ARTICLES], key=lambda x: -x[0]
    )
    category = scored[0][1]["category"] if scored[0][0] >= 2 else "unknown"
    urgent = any(
        x in (body.title + " " + body.description).lower()
        for x in ["blocked", "tomorrow", "urgent", "cannot access"]
    )
    return {
        "category": category,
        "priority": "high" if urgent and category != "unknown" else "medium",
        "rationale": "Suggested from operational keywords. Confirm category and urgency before creating the case.",
        "requires_human_review": True,
        "method": "keyword-assisted",
    }


@app.get("/roi")
def scenarios(a=Depends(actor)):
    return query(
        "SELECT s.*,c.title FROM roi_scenarios s JOIN runs r ON r.workspace_id=s.workspace_id AND r.id=s.run_id JOIN cases c ON c.workspace_id=r.workspace_id AND c.id=r.case_id WHERE s.workspace_id=%s ORDER BY s.created_at DESC",
        (a["workspace_id"],),
    )


@app.post("/roi/{run_id}")
def scenario(run_id: UUID, body: Scenario, a=Depends(actor)):
    require(a)
    with connect() as c:
        run = get_run(a, run_id, c, True)
        if (
            run["decision"] != "approved"
            or run["result"]["recommendation"]["status"] != "supported"
        ):
            raise HTTPException(422, "Choose an approved, supported investigation.")
        if c.execute(
            "SELECT run_id FROM roi_scenarios WHERE workspace_id=%s AND run_id=%s",
            (a["workspace_id"], run_id),
        ).fetchone():
            raise HTTPException(409, "This run already has a scenario.")
        c.execute(
            "INSERT INTO roi_scenarios(workspace_id,run_id,baseline,assisted,hourly_cost,ai_cost,actor_id) VALUES(%s,%s,%s,%s,%s,%s,%s)",
            (
                a["workspace_id"],
                run_id,
                body.baseline,
                body.assisted,
                body.hourly_cost,
                body.ai_cost,
                a["user_id"],
            ),
        )
    return {"status": "saved", "measurement_type": "scenario"}


@app.post("/feedback", status_code=201)
def feedback(body: Feedback, a=Depends(actor)):
    rate("feedback:" + str(a["user_id"]), 5)
    return query(
        "INSERT INTO feedback VALUES(%s,%s,%s,%s,%s,now()) RETURNING id",
        (uuid4(), a["workspace_id"], a["user_id"], body.rating, body.message),
    )[0]


@app.get("/feedback")
def feedback_list(a=Depends(actor)):
    require(a, ("owner",))
    return query(
        "SELECT f.id,f.rating,f.message,f.created_at,u.name FROM feedback f LEFT JOIN users u ON u.id=f.actor_id WHERE f.workspace_id=%s ORDER BY f.created_at DESC LIMIT 100",
        (a["workspace_id"],),
    )


@app.get("/export")
def export(a=Depends(actor)):
    require(a, ("owner",))
    w = a["workspace_id"]
    return {
        "version": "2.0.0",
        "exported_at": datetime.now(timezone.utc),
        "workspace": a["workspace_name"],
        "cases": query("SELECT * FROM cases WHERE workspace_id=%s", (w,)),
        "knowledge": query(
            "SELECT id,title,content,category,version,archived FROM knowledge WHERE workspace_id=%s",
            (w,),
        ),
        "runs": query("SELECT * FROM runs WHERE workspace_id=%s", (w,)),
        "events": query(
            "SELECT * FROM case_events WHERE workspace_id=%s ORDER BY id", (w,)
        ),
        "operations": query("SELECT * FROM operations WHERE workspace_id=%s", (w,)),
        "roi": query("SELECT * FROM roi_scenarios WHERE workspace_id=%s", (w,)),
        "workflows": {
            table: query(f"SELECT * FROM {table} WHERE workspace_id=%s", (w,))
            for table in (
                "workspace_policies",
                "procedure_versions",
                "snapshot_history",
                "investigation_checks",
                "information_requests",
                "case_evidence",
                "snapshot_comparisons",
                "case_links",
                "procedure_reassessments",
                "human_effort",
                "monitoring_visits",
                "notification_preferences",
                "notifications",
                "evaluation_runs",
                "walkthrough_progress",
            )
        },
    }


from release_api import router as release_router

app.include_router(release_router)

from assessments import router as assessment_router
app.include_router(assessment_router)
