"""Document journey: deterministic reconciliation of source-scoped synthetic exports, evidence-collection drafts,
expected-outcome verification and decision replay. Identity, versions, destinations, dates and verification status come only from
structured fields, explicit mappings and human-confirmed links. Nothing here calls a model, sends messages, approves, resolves or reopens."""
import hashlib, json, re
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException
from psycopg.types.json import Jsonb
from pydantic import Field, field_validator
from db import connect
from typing import Annotated
from pydantic import StringConstraints
from models import Model
from operational_evidence import instant
from security import actor, rate

router = APIRouter()


def T(lo, hi, pattern=None):
    return Annotated[str, StringConstraints(strip_whitespace=True, min_length=lo, max_length=hi, pattern=pattern)]
STAGES = ("upload_receipt", "processing", "transfer", "destination_filing", "binder_visibility")
LABEL = {"upload_receipt": "Upload receipt", "processing": "Processing", "transfer": "Transfer / synchronization",
         "destination_filing": "Destination filing", "binder_visibility": "Binder visibility"}
ALLOWED = {"upload_receipt": {"received"}, "processing": {"pending", "running", "completed", "failed"},
           "transfer": {"queued", "pending", "running", "completed", "failed"}, "destination_filing": {"pending", "completed", "failed"},
           "binder_visibility": {"visible", "not_visible"}}
VERSION_REQUIRED = DEST_REQUIRED = {"destination_filing", "binder_visibility"}
FIELDS = ("source_ref", "document_ref", "version", "transfer_ref", "binder_ref", "xref_system", "xref_ref", "status", "observed_at")
SYSTEM = re.compile(r"[a-z0-9][a-z0-9_-]{1,59}")
IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}")
OK_BASIS = ("native", "source_declared", "reviewer_link")
NEGATIVE = {"failed", "not_visible"}  # only these explicitly state that a stage did not happen / is not visible
MAX_CANDIDATES = 5
INTERPRETATION = ("Recorded status and evidence assessment are separate: verified means a recorded fact is supported (a verified failure is still a failure). "
                  "Identifiers are source-scoped; identical ID text in two systems, a shared study/site, similar titles or nearby times never establish linkage. "
                  "Absence from an export is not evidence of failure, historical observations do not establish current status, and a failed job does not establish a root cause.")


def canon(v):
    return json.dumps(v, sort_keys=True, default=str, separators=(",", ":"))


def iso(v):
    return instant(v).isoformat() if v else None


# ------------------------------------------------------------------ import: explicit mapping, source provenance, coverage
def dig(row, path):
    cur = row
    for part in str(path).split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    if isinstance(cur, bool) or cur is None or isinstance(cur, (dict, list)):
        return None
    return str(cur).strip() or None


def normalize_export(env, mapping, now=None):
    now = now or datetime.now(timezone.utc)
    if not isinstance(env, dict) or not isinstance(mapping, dict):
        raise ValueError("Export and mapping must be JSON objects")
    system, ref = env.get("source_system"), env.get("export_ref")
    if not isinstance(system, str) or not SYSTEM.fullmatch(system):
        raise ValueError("source_system must be lowercase letters, numbers, hyphens or underscores")
    if not isinstance(ref, str) or not IDENT.fullmatch(ref):
        raise ValueError("export_ref is malformed")
    if env.get("synthetic") is not True:
        raise ValueError("This prototype accepts synthetic mock-system exports only (synthetic must be true)")
    observed = instant(env["observed_at"])
    if observed > now:
        raise ValueError("Export observation cannot be in the future")
    cov = env.get("coverage")
    if not isinstance(cov, dict) or type(cov.get("complete")) is not bool or not isinstance(cov.get("stages"), list) or not cov["stages"] or any(s not in STAGES for s in cov["stages"]):
        raise ValueError("coverage needs complete (true/false) and a stages list drawn from " + ", ".join(STAGES))
    coverage = {"complete": cov["complete"], "stages": sorted(set(cov["stages"])), "from": iso(cov.get("from")), "to": iso(cov.get("to"))}
    rows = env.get("rows")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 200:
        raise ValueError("rows must contain 1–200 records")
    fields = mapping.get("fields")
    if not isinstance(fields, dict) or "source_ref" not in fields or any(k not in FIELDS for k in fields):
        raise ValueError("mapping.fields must name source_ref and may only map: " + ", ".join(FIELDS))
    stage_values = mapping.get("stage_values") or {}
    fixed = mapping.get("stage")
    if bool(fixed) == bool(mapping.get("stage_field")) or (fixed and fixed not in STAGES) or (not fixed and not (isinstance(stage_values, dict) and stage_values and all(v in STAGES for v in stage_values.values()))):
        raise ValueError("Give either a fixed mapping.stage or mapping.stage_field with stage_values onto the five stages")
    status_values = mapping.get("status_values") or {}
    if not isinstance(status_values, dict):
        raise ValueError("status_values must be an object")
    out = []
    for i, row in enumerate(rows):
        try:
            if not isinstance(row, dict) or len(canon(row)) > 4000:
                raise ValueError("row must be an object under 4,000 characters")
            stage = fixed or stage_values.get(dig(row, mapping["stage_field"]))
            if stage not in STAGES:
                raise ValueError("stage value is not mapped")
            if stage not in coverage["stages"]:
                raise ValueError("%s is not declared in this export's coverage" % LABEL[stage])
            rec = {k: (dig(row, fields[k]) if k in fields else None) for k in FIELDS}
            for k in ("source_ref", "document_ref", "transfer_ref", "binder_ref", "xref_ref"):
                if rec[k] is not None and not IDENT.fullmatch(rec[k]):
                    raise ValueError(k + " is not a structured identifier")
            if rec["source_ref"] is None:
                raise ValueError("source_ref is required")
            if rec["version"] is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,29}", rec["version"]):
                raise ValueError("version is malformed")
            if rec["xref_system"] is not None and not SYSTEM.fullmatch(rec["xref_system"]):
                raise ValueError("xref_system is malformed")
            if (rec["xref_system"] is None) != (rec["xref_ref"] is None):
                raise ValueError("xref_system and xref_ref must be given together")
            raw_status, status = rec.pop("status"), None
            if raw_status is not None:
                status = status_values.get(raw_status)
                if status is not None and status not in ALLOWED[stage]:
                    raise ValueError("status maps to '%s', which is not valid for %s" % (status, LABEL[stage]))
            seen = instant(rec["observed_at"]) if rec["observed_at"] else observed
            if seen > observed:
                raise ValueError("record observation is later than the export observation")
            out.append({**rec, "stage": stage, "source_system": system, "status": status, "status_raw": raw_status,
                        "observed_at": seen.isoformat(), "index": i, "raw": row})
        except (ValueError, KeyError, TypeError) as e:
            raise ValueError("Row %d: %s" % (i + 1, e))
    return {"source_system": system, "export_ref": ref, "observed_at": observed.isoformat(), "coverage": coverage, "records": out}


# ------------------------------------------------------------------ deterministic matching
def identity(rec, subj, links):
    system, doc = rec["source_system"], rec["document_ref"]
    target = (subj["document_system"], subj["document_ref"])
    if doc and (system, doc) == target:
        return "native", None
    if rec["xref_system"] and (rec["xref_system"], rec["xref_ref"]) == target:
        return "source_declared", None
    for l in links:
        if l["revoked_at"] or (l["to_system"], l["to_ref"]) != target:
            continue
        if l["kind"] == "document" and doc and (l["from_system"], l["from_ref"]) == (system, doc):
            return "reviewer_link", l
        if l["kind"] == "record" and not doc and (l["from_system"], l["from_ref"]) in ((system, rec["source_ref"]), (system, rec["transfer_ref"])):
            return "reviewer_link", l
    if doc and doc == subj["document_ref"]:
        return "collision", None
    return None, None


def destination(rec, subj, links):
    b, s = rec["binder_ref"], rec["source_system"]
    if b is None:
        return "absent"
    if (s, b) == (subj["destination_system"], subj["binder_ref"]) or any(
            not l["revoked_at"] and l["kind"] == "destination" and (l["from_system"], l["from_ref"]) == (s, b)
            and (l["to_system"], l["to_ref"]) == (subj["destination_system"], subj["binder_ref"]) for l in links):
        return "ok"
    return "collision" if b == subj["binder_ref"] else "wrong"


def classify(rec, subj, links):
    stage, problems = rec["stage"], []
    basis, link = identity(rec, subj, links)
    if basis == "collision":
        problems.append("id_collision")
    elif basis is None:
        if rec["document_ref"] is None:
            problems.append("unlinked")
        else:
            problems.append("other_document")
    else:
        if rec["version"] is None:
            if stage in VERSION_REQUIRED:
                problems.append("version_not_recorded")
        elif rec["version"] != subj["document_version"]:
            problems.append("wrong_version")
        dest = destination(rec, subj, links)
        if stage in DEST_REQUIRED or (stage == "transfer" and dest in ("wrong", "collision")):
            if dest != "ok":
                problems.append({"absent": "destination_not_recorded", "wrong": "wrong_destination", "collision": "destination_collision"}[dest])
    return {"exact": not problems, "basis": basis, "link": link, "problems": problems}


PROBLEM_TEXT = {
    "id_collision": "same ID text as the subject document but in a different system, with no explicit mapping or reviewed link",
    "unlinked": "carries no document reference and no reviewed link ties it to this document",
    "wrong_version": "document version differs from the expected version",
    "version_not_recorded": "no document version recorded, which this stage requires",
    "wrong_destination": "destination binder differs from the intended binder",
    "destination_not_recorded": "no destination binder recorded, which this stage requires",
    "destination_collision": "binder ID text matches the intended binder but it belongs to a different system with no mapping",
}


def summary(rec, cls=None, role=None):
    out = {k: rec[k] for k in ("ref", "stage", "source_system", "source_ref", "document_ref", "version", "transfer_ref", "binder_ref", "xref_system", "xref_ref",
                               "status", "status_raw", "observed_at", "export_ref", "export_complete", "raw")}
    if cls:
        out.update(match_basis=cls["basis"], problems=cls["problems"], link=cls["link"] and {**{k: cls["link"][k] for k in ("id", "rationale", "evidence", "actor_name")}, "created_at": cls["link"]["created_at"].isoformat()})
    if role:
        out["role"] = role
    return out


def latest_per_system(recs):
    best = {}
    for r in recs:
        best[r["source_system"]] = max(best.get(r["source_system"], ""), r["observed_at"])
    return [r for r in recs if r["observed_at"] == best[r["source_system"]]]


def assess_stage(stage, records, exports, subj, links):
    mine = [(r, classify(r, subj, links)) for r in records if r["stage"] == stage]
    support = [r for r, c in mine if c["exact"]]
    cur = latest_per_system(support)
    statuses = {r["status"] for r in cur if r["status"]}
    conflict = len(statuses) > 1
    doc = "%s %s version %s" % (subj["document_system"], subj["document_ref"], subj["document_version"])
    where = subj["destination_system"] if stage in DEST_REQUIRED else subj["document_system"]
    gaps, missing, conflicts, notes, cands = [], [], [], [], []
    for r, c in sorted(mine, key=lambda x: x[0]["observed_at"], reverse=True):
        if c["exact"] or "other_document" in c["problems"]:
            continue
        cands.append(summary(r, c, "excluded"))
    shown = cands[:MAX_CANDIDATES]
    for cand in shown:
        p = cand["problems"][0]
        ref = "%s %s" % (cand["source_system"], cand["source_ref"])
        why = "; ".join(PROBLEM_TEXT[x] for x in cand["problems"])
        missing.append("%s (%s): %s." % (ref, LABEL[stage], why[0].upper() + why[1:]))
        gaps.append({"code": p, "key": p + ":" + cand["ref"], "description": missing[-1],
                     "question": {"id_collision": "Is %s record %s the same document as %s? Please give the mapping between the two systems' identifiers." % (cand["source_system"], cand["document_ref"], doc),
                                  "unlinked": "Does %s record %s (%s, recorded status %s) concern %s? Please provide the record-to-document cross-reference." % (cand["source_system"], cand["source_ref"], LABEL[stage].lower(), cand["status_raw"] or "not recorded", doc),
                                  "wrong_version": "The %s record %s is for version %s; was version %s processed for this stage? Please provide the record for the expected version." % (LABEL[stage].lower(), cand["source_ref"], cand["version"], subj["document_version"]),
                                  "version_not_recorded": "Which document version does %s record %s apply to? Please provide the version it recorded." % (cand["source_system"], cand["source_ref"]),
                                  "wrong_destination": "Record %s shows binder %s, not the intended %s/%s. Was the document also filed in the intended binder? Please provide that record." % (cand["source_ref"], cand["binder_ref"], subj["destination_system"], subj["binder_ref"]),
                                  "destination_not_recorded": "Record %s does not name a destination binder. Which binder does it concern? Please provide the destination reference." % cand["source_ref"],
                                  "destination_collision": "Is binder %s in %s the same as %s/%s? Please provide the mapping." % (cand["binder_ref"], cand["source_system"], subj["destination_system"], subj["binder_ref"])}[p],
                     "would_settle": "An explicit identifier mapping or a source record that names %s%s lets a reviewer confirm or reject this candidate." % (doc, (" and binder " + subj["binder_ref"]) if stage in DEST_REQUIRED else "")})
    if len(cands) > len(shown):
        notes.append("%d further excluded candidates not shown." % (len(cands) - len(shown)))
    if conflict:
        by = ["%s %s: %s at %s" % (r["source_system"], r["source_ref"], r["status"], r["observed_at"]) for r in cur if r["status"]]
        conflicts.append("Sources disagree on the recorded status — " + "; ".join(by) + ". The newest record is not treated as truth.")
        gaps.append({"code": "conflict", "key": "conflict:" + stage, "description": conflicts[-1],
                     "question": "Records disagree on the %s status for %s. Which source record is authoritative, and what does its audit trail show?" % (LABEL[stage].lower(), doc),
                     "would_settle": "A source-system audit entry reconciling the competing records, which a reviewer can confirm."})
    if not support:
        cover = [e for e in exports if stage in e["coverage"]["stages"]]
        complete = [e for e in cover if e["coverage"]["complete"]]
        if not cover:
            missing.append("No imported export declares coverage of %s." % LABEL[stage].lower())
        elif not complete:
            missing.append("Export(s) %s declare coverage of this stage but are marked incomplete; an absent record there is not evidence." % ", ".join(e["export_ref"] for e in cover))
        else:
            missing.append("Complete export(s) %s hold no record for this document; absence does not establish a failure." % ", ".join(e["export_ref"] for e in complete))
        code = "export_incomplete" if cover and not complete else "no_record"
        missing.insert(0, "No exact %s record in %s for %s%s." % (LABEL[stage].lower(), where, doc, (" in binder " + subj["binder_ref"]) if stage in DEST_REQUIRED else ""))
        gaps.append({"code": code, "key": code + ":" + stage, "description": missing[0],
                     "question": "Please provide the %s record for %s%s from %s, with its record reference, recorded status and observation time." % (LABEL[stage].lower(), doc, (" in binder " + subj["binder_ref"]) if stage in DEST_REQUIRED else "", where) if code == "no_record"
                     else "Please provide a complete %s export covering %s for this study and site, or confirm no record exists." % (where, LABEL[stage].lower()),
                     "would_settle": "A record in %s naming this document and version%s, observed after the issue, with its recorded status." % (where, " and the intended binder" if stage in DEST_REQUIRED else "")})
    status = None if conflict or not statuses else next(iter(statuses))
    if status == "failed":
        notes.append("A recorded failure. The root cause is not established by this record.")
    assessment = "conflicting" if conflict else "verified" if support else "unknown"
    prior = [r for r in support if r not in cur]
    recs = [summary(r, c, "supporting" if r in cur else "earlier_observation") for r, c in mine if c["exact"]]
    return {"stage": stage, "label": LABEL[stage], "operational_status": status, "as_of": max((r["observed_at"] for r in cur), default=None),
            "assessment": assessment, "records": recs, "candidates": shown, "conflicts": conflicts, "missing": missing, "gaps": gaps, "notes": notes,
            "earlier_observations": len(prior)}


def humanize(s):
    return s.replace("_", " ") if s else ""


def findings(stages):
    out = []
    for s in stages:
        if s["assessment"] == "verified":
            out.append("%s: %s (verified as of %s, %s)." % (s["label"], (s["operational_status"] or "no status recorded").replace("_", " "), s["as_of"][:16].replace("T", " "), next(r for r in s["records"] if r["role"] == "supporting")["source_system"]))
        elif s["assessment"] == "conflicting":
            out.append("%s: conflicting sources — not resolved." % s["label"])
        else:
            out.append("%s: unknown — %s" % (s["label"], s["missing"][0]))
    return out


def build_journey(subj, links, exports, policy_hours=None, now=None, attested=()):
    """exports: [{id, source_system, export_ref, observed_at, coverage, records, created_at}] already scoped to the case's study/site."""
    now = now or datetime.now(timezone.utc)
    records = [{**r, "ref": "%s:%d" % (e["id"], r["index"]), "export_ref": e["export_ref"], "export_complete": e["coverage"]["complete"]} for e in exports for r in e["records"]]
    stages = [assess_stage(s, records, exports, subj, links) for s in STAGES]
    for st in stages:  # reviewed-response assertions: shown with provenance, never counted as verification
        mine = [(a, classify(a, subj, links)) for a in attested if a["stage"] == st["stage"]]
        st["attested"] = [summary(a, c, "attested") | {"attested_by": a["attested_by"], "response_ref": a["response_ref"]} for a, c in mine if "other_document" not in c["problems"]]
        exact = [a for a in st["attested"] if not a["problems"]]
        if exact and st["assessment"] != "verified":
            st["missing"].append("A reviewed response asserts this stage (%s); no system record supports it, so it stays unknown." % "; ".join("%s %s: %s" % (a["source_system"], a["source_ref"], humanize(a["status"]) or "no status") for a in exact))
    for st in stages:  # structured description of the exact record each gap asks for (no free text)
        cands = {c["ref"]: c for c in st["candidates"]}
        for g in st["gaps"]:
            c = cands.get(g["key"].split(":", 1)[1]) if g["code"] not in ("no_record", "export_incomplete", "conflict") else None
            g["target"] = {"stage": st["stage"], "code": g["code"], "source_system": subj["destination_system"] if st["stage"] in DEST_REQUIRED else subj["document_system"],
                           "document_ref": subj["document_ref"], "document_version": subj["document_version"],
                           "binder_ref": subj["binder_ref"] if st["stage"] in DEST_REQUIRED else None,
                           "record": {"source_system": c["source_system"], "source_ref": c["source_ref"]} if c else None}
    core = {"subject": {k: subj[k] for k in ("rev", "document_system", "document_ref", "document_version", "destination_system", "binder_ref")},
            "stages": [{k: s[k] for k in ("stage", "operational_status", "as_of", "assessment")} | {"refs": [r["ref"] for r in s["records"]], "cands": [r["ref"] for r in s["candidates"]]} for s in stages],
            "links": sorted(l["id"] + ("x" if l["revoked_at"] else "") for l in links), "exports": sorted(e["id"] for e in exports),
            "attested": sorted(a["ref"] for a in attested)}
    fingerprint = hashlib.sha256(canon(core).encode()).hexdigest()
    for s in stages:  # freshness is time-dependent, so it stays outside the fingerprint
        for r in s["records"]:
            age = (now - instant(r["observed_at"])).total_seconds() / 3600
            r["age_hours"] = round(age, 2)
            r["stale"] = bool(policy_hours is not None and age > float(policy_hours))
    return {"subject": core["subject"], "stages": stages, "findings": findings(stages), "fingerprint": fingerprint,
            "freshness_policy_hours": float(policy_hours) if policy_hours is not None else None, "evaluated_at": now.isoformat(), "interpretation": INTERPRETATION,
            "records": records}


# ------------------------------------------------------------------ expected outcomes and verification
def valid_requirements(req):
    if req is None:
        return None
    if not isinstance(req, list) or not 1 <= len(req) <= 5:
        raise ValueError("Give 1–5 structured requirements, or leave empty for human assessment")
    for r in req:
        if not isinstance(r, dict) or set(r) != {"stage", "status"} or r["stage"] not in STAGES or r["status"] not in ALLOWED[r["stage"]]:
            raise ValueError("Each requirement needs a stage and a status valid for that stage")
    return req


def eval_requirement(req, outcome, journey, subj, links, now, hours):
    stage = req["stage"]
    cls = [(r, classify(r, subj, links)) for r in journey["records"] if r["stage"] == stage]
    exact = [r for r, c in cls if c["exact"]]
    remediation = instant(outcome["remediation_at"])
    before = [r["ref"] for r in exact if instant(r["observed_at"]) <= remediation]
    post = [r for r in exact if instant(r["observed_at"]) > remediation]
    out = {"stage": stage, "expected_status": req["status"], "before": before, "after": [r["ref"] for r in post]}
    others = [r for r, c in cls if not c["exact"] and "other_document" not in c["problems"] and instant(r["observed_at"]) > remediation]
    if not post:
        why = "no exact-document/version/destination observation after the remediation point (%s)" % remediation.isoformat()
        if before:
            why += "; %d earlier observation(s) do not count" % len(before)
        if others:
            why += "; %d later record(s) were excluded as mismatched or unlinked (%s)" % (len(others), ", ".join(sorted({p for r, c in cls if r in others for p in c["problems"]})))
        return {**out, "result": "insufficient", "reason": why}
    if hours is not None:
        fresh = [r for r in post if (now - instant(r["observed_at"])).total_seconds() / 3600 <= float(hours)]
        if not fresh:
            return {**out, "result": "insufficient", "reason": "post-remediation observations are older than the workspace freshness policy (%g hours)" % float(hours)}
        post = fresh
    cur = latest_per_system(post)
    ok = [r for r in cur if r["status"] == req["status"]]
    bad = [r for r in cur if r["status"] in NEGATIVE and r["status"] != req["status"]]
    other = [r for r in cur if r["status"] and r["status"] != req["status"] and r["status"] not in NEGATIVE]
    out["used"] = [r["ref"] for r in cur]
    if ok and bad:
        return {**out, "result": "insufficient", "reason": "post-remediation sources conflict (%s)" % ", ".join("%s: %s" % (r["source_system"], r["status"]) for r in cur)}
    if ok:
        return {**out, "result": "verified", "reason": "exact record(s) show '%s' observed after the remediation point" % req["status"]}
    if bad:
        return {**out, "result": "contradicted", "reason": "exact record(s) show '%s', not '%s'" % (bad[0]["status"], req["status"])}
    if other:
        return {**out, "result": "insufficient", "reason": "latest exact record shows '%s', which neither confirms nor contradicts '%s'" % (other[0]["status"], req["status"])}
    return {**out, "result": "insufficient", "reason": "matching post-remediation records carry no recorded status"}


def evaluate(outcomes, human, journey, subj, links, now, hours):
    results = []
    for o in outcomes:
        if o["requirements"]:
            parts = [eval_requirement(r, o, journey, subj, links, now, hours) for r in o["requirements"]]
            res = "contradicted" if any(p["result"] == "contradicted" for p in parts) else "verified" if all(p["result"] == "verified" for p in parts) else "insufficient"
            results.append({"outcome_id": str(o["id"]), "outcome_key": str(o["outcome_key"]), "rev": o["rev"], "required": o["required"], "method": "deterministic", "result": res, "parts": parts})
        else:
            h = human.get(str(o["id"]))
            results.append({"outcome_id": str(o["id"]), "outcome_key": str(o["outcome_key"]), "rev": o["rev"], "required": o["required"], "method": "human" if h else "needs_human_assessment",
                            "result": h["result"] if h else "insufficient",
                            "parts": [], "reason": ("Human assessment: " + h["rationale"]) if h else "This outcome cannot be assessed deterministically; a human assessment is required."})
    return results


def overall(results):
    req = [r["result"] for r in results if r["required"]]
    if not req:
        return "insufficient_evidence"
    if "contradicted" in req:
        return "not_verified"
    if all(r == "verified" for r in req):
        return "verified"
    return "partially_verified" if "verified" in req else "insufficient_evidence"


# ------------------------------------------------------------------ persistence helpers
def writer(c, a):
    from five_features import current
    return current(c, a, True)


def case_for(c, a, cid, lock=False):
    from main import get_case
    return get_case(a, cid, c, lock)


def audit(c, a, cid, kind, notes, payload):
    from main import event
    return event(c, a, cid, kind, notes, None, payload)


def load(c, w, item):
    exports = c.execute("SELECT * FROM journey_exports WHERE workspace_id=%s AND study_id=%s AND site_id=%s ORDER BY observed_at,created_at LIMIT 200", (w, item["study_id"], item["site_id"])).fetchall()
    for e in exports:
        e["id"] = str(e["id"])
    subjects = c.execute("SELECT * FROM journey_subjects WHERE workspace_id=%s AND case_id=%s ORDER BY rev", (w, item["id"])).fetchall()
    links = c.execute("SELECT * FROM journey_links WHERE workspace_id=%s AND case_id=%s ORDER BY created_at,id", (w, item["id"])).fetchall()
    for l in links:
        l["id"] = str(l["id"])
    return exports, subjects, links


def hours(c, w):
    row = c.execute("SELECT freshness_hours FROM workspace_policies WHERE workspace_id=%s", (w,)).fetchone()
    return row["freshness_hours"] if row else None


def attestation_records(rows):
    return [{"stage": r["stage"], "source_system": r["source_system"], "source_ref": r["source_ref"], "document_ref": r["document_ref"], "version": r["version"],
             "transfer_ref": r["transfer_ref"], "binder_ref": r["binder_ref"], "xref_system": None, "xref_ref": None, "status": r["status"], "status_raw": r["status"],
             "observed_at": r["observed_at"].isoformat(), "export_ref": r["response_ref"], "export_complete": None, "ref": "att:" + str(r["id"]), "index": 0,
             "attested_by": r["actor_name"], "response_ref": r["response_ref"],
             "raw": {"provenance": "reviewed response", "response": r["response_ref"], "response_submitted_at": r["response_submitted_at"].isoformat(), "response_reviewer": r["response_reviewer"],
                     "recorded_by": r["actor_name"], "rationale": r["rationale"]}} for r in rows]


def current_journey(c, a, item, now=None):
    w = a["workspace_id"]
    exports, subjects, links = load(c, w, item)
    subj = subjects[-1] if subjects else None
    att = c.execute("SELECT * FROM journey_attestations WHERE workspace_id=%s AND case_id=%s ORDER BY created_at", (w, item["id"])).fetchall()
    j = build_journey(subj, links, exports, hours(c, w), now, attestation_records(att)) if subj else None
    return j, subj, links, exports, subjects


def save_assessment(c, a, cid, j):
    stored = {k: v for k, v in j.items() if k not in ("records", "evaluated_at")}
    row = c.execute("INSERT INTO journey_assessments(workspace_id,id,case_id,fingerprint,subject_rev,result,actor_id) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(workspace_id,case_id,fingerprint) DO NOTHING RETURNING id",
                    (a["workspace_id"], uuid4(), cid, j["fingerprint"], j["subject"]["rev"], Jsonb(stored), a["user_id"])).fetchone()
    return (row or c.execute("SELECT id FROM journey_assessments WHERE workspace_id=%s AND case_id=%s AND fingerprint=%s", (a["workspace_id"], cid, j["fingerprint"])).fetchone())["id"]


def current_outcomes(rows):
    latest = {}
    for r in rows:
        latest[r["outcome_key"]] = r
    return [r for r in latest.values() if not r["retired"]]


def verification_view(v, j, outcomes):
    """A stored verification is historical, never rewritten, once its outcomes or the journey evidence differ from now."""
    v = dict(v)
    ids = sorted(o["id"] for o in outcomes)
    v["current"] = bool(j and v["assessment_fingerprint"] == j["fingerprint"] and sorted(UUID(x["outcome_id"]) for x in v["results"]) == ids)
    return v


# ------------------------------------------------------------------ routes
class Subject(Model):
    id: UUID
    expected_rev: int = Field(ge=0)
    document_system: T(2, 60, "^" + SYSTEM.pattern + "$")
    document_ref: T(1, 100, "^" + IDENT.pattern + "$")
    document_version: T(1, 30, r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,29}$")
    destination_system: T(2, 60, "^" + SYSTEM.pattern + "$")
    binder_ref: T(1, 100, "^" + IDENT.pattern + "$")


class Link(Model):
    id: UUID
    kind: Literal["document", "record", "destination"]
    from_system: T(2, 60, "^" + SYSTEM.pattern + "$")
    from_ref: T(1, 100, "^" + IDENT.pattern + "$")
    rationale: T(10, 1000)
    evidence: T(5, 1000)
    snapshot_decision_id: UUID | None = None


class Attest(Model):
    id: UUID
    response_ref: T(10, 120)
    stage: Literal[STAGES]
    source_system: T(2, 60, "^" + SYSTEM.pattern + "$")
    source_ref: T(1, 100, "^" + IDENT.pattern + "$")
    document_ref: T(1, 100, "^" + IDENT.pattern + "$") | None = None
    version: T(1, 30, r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,29}$") | None = None
    transfer_ref: T(1, 100, "^" + IDENT.pattern + "$") | None = None
    binder_ref: T(1, 100, "^" + IDENT.pattern + "$") | None = None
    status: str | None = None
    observed_at: datetime
    rationale: T(10, 1000)

    @field_validator("observed_at")
    @classmethod
    def aware(cls, v):
        if v.tzinfo is None:
            raise ValueError("Timezone required")
        return v


class Revoke(Model):
    reason: T(10, 1000)


class Collection(Model):
    id: UUID
    request_id: UUID
    stage: Literal[STAGES]
    gap_key: T(1, 300)
    question: T(10, 1500)
    would_settle: T(5, 1000)
    contact_id: UUID | None = None
    due_at: datetime | None = None
    duplicate_reason: str = Field(default="", max_length=2000)
    prioritization_id: UUID | None = None

    @field_validator("due_at")
    @classmethod
    def aware(cls, v):
        if v is not None and v.tzinfo is None:
            raise ValueError("Timezone required")
        return v


class OutcomeEdit(Model):
    id: UUID
    key: UUID
    expected_rev: int = Field(ge=0)
    description: T(10, 500)
    requirements: list[dict] | None = None
    required: bool = True
    remediation_at: datetime | None = None
    retired: bool = False

    @field_validator("remediation_at")
    @classmethod
    def aware(cls, v):
        if v is not None and v.tzinfo is None:
            raise ValueError("Timezone required")
        return v


class Human(Model):
    result: Literal["verified", "contradicted", "insufficient"]
    rationale: T(10, 1000)


class Verify(Model):
    id: UUID
    rationale: T(10, 1000)
    human: dict[UUID, Human] = {}


class ImportBody(Model):
    export: dict
    mapping: dict


def public_exports(exports):
    return [{"id": e["id"], "source_system": e["source_system"], "export_ref": e["export_ref"], "observed_at": e["observed_at"], "coverage": e["coverage"], "records": len(e["records"]), "created_at": e["created_at"]} for e in exports]


@router.post("/operations/journey-import", status_code=201)
def journey_import(body: ImportBody, a=Depends(actor)):
    rate("journey-import:" + str(a["workspace_id"]), 30)
    env = body.export
    try:
        n = normalize_export(env, body.mapping)
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(422, str(e))
    study, site = env.get("study_id"), env.get("site_id")
    with connect() as c:
        from five_features import current
        from security import require
        require({**a, "role": current(c, a)}, ("owner",))
        if not c.execute("SELECT 1 FROM sites WHERE workspace_id=%s AND id=%s AND study_id=%s", (a["workspace_id"], site, study)).fetchone():
            raise HTTPException(422, "Study/site relationship is outside this workspace")
        sha = hashlib.sha256(canon({"export": env, "mapping": body.mapping}).encode()).hexdigest()
        old = c.execute("SELECT id,content_hash FROM journey_exports WHERE workspace_id=%s AND source_system=%s AND export_ref=%s FOR UPDATE", (a["workspace_id"], n["source_system"], n["export_ref"])).fetchone()
        if old:
            if old["content_hash"] != sha:
                raise HTTPException(409, "This export reference already holds different immutable evidence. Use a new export reference.")
            return {"id": old["id"], "status": "already_imported", "records": len(n["records"])}
        eid = uuid4()
        c.execute("INSERT INTO journey_exports(workspace_id,id,study_id,site_id,source_system,export_ref,observed_at,coverage,mapping,records,content_hash,actor_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                  (a["workspace_id"], eid, study, site, n["source_system"], n["export_ref"], n["observed_at"], Jsonb(n["coverage"]), Jsonb(body.mapping), Jsonb(n["records"]), sha, a["user_id"]))
        return {"id": eid, "status": "imported", "records": len(n["records"]), "coverage": n["coverage"]}


def plan_items(c, w, cid):
    return c.execute("SELECT p.*,r.status AS request_status,r.title AS request_title,k.name AS contact_name FROM journey_plan_items p JOIN information_requests r ON (r.workspace_id,r.id)=(p.workspace_id,p.request_id) LEFT JOIN support_contacts k ON (k.workspace_id,k.id)=(p.workspace_id,p.contact_id) WHERE p.workspace_id=%s AND p.case_id=%s ORDER BY p.created_at DESC", (w, cid)).fetchall()


def outcome_rows(c, w, cid):
    return c.execute("SELECT * FROM journey_outcomes WHERE workspace_id=%s AND case_id=%s ORDER BY created_at,rev", (w, cid)).fetchall()


def verifications(c, w, cid):
    rows = c.execute("SELECT v.*,s.fingerprint AS assessment_fingerprint FROM journey_verifications v JOIN journey_assessments s ON (s.workspace_id,s.id)=(v.workspace_id,v.assessment_id) WHERE v.workspace_id=%s AND v.case_id=%s ORDER BY v.created_at DESC", (w, cid)).fetchall()
    return rows


@router.get("/cases/{cid}/journey")
def get_journey(cid: str, a=Depends(actor)):
    with connect() as c:
        item = case_for(c, a, cid)
        j, subj, links, exports, subjects = current_journey(c, a, item)
        w = a["workspace_id"]
        orows = outcome_rows(c, w, cid)
        outcomes = current_outcomes(orows)
        reviewer = a["role"] in ("owner", "reviewer")
        ver = [verification_view(v, j, outcomes) for v in verifications(c, w, cid)] if reviewer else []
        for v in ver[1:]:
            v["current"] = False  # only the newest verification can describe the present state
        if j:
            j = {k: v for k, v in j.items() if k != "records"}
        for l in links:
            l["applies_to_current_definition"] = bool(subj and (l["to_system"], l["to_ref"]) in ((subj["document_system"], subj["document_ref"]), (subj["destination_system"], subj["binder_ref"])))
        extra = {"snapshot_links": snapshot_links(c, a, cid), "responses": reviewable_responses(c, a, cid),
                 "attestations": c.execute("SELECT * FROM journey_attestations WHERE workspace_id=%s AND case_id=%s ORDER BY created_at DESC", (w, cid)).fetchall()} if reviewer else {"snapshot_links": [], "responses": [], "attestations": []}
        return {**extra, "subject": subj, "subjects": subjects, "journey": j, "links": links, "exports": public_exports(exports), "plan_items": plan_items(c, w, cid),
                "outcomes": outcomes, "outcome_history": orows if reviewer else [], "verifications": ver, "can_write": reviewer, "can_import": a["role"] == "owner",
                "freshness_hours": float(hours(c, w)) if hours(c, w) is not None else None}


@router.post("/cases/{cid}/journey/subject")
def set_subject(cid: str, body: Subject, a=Depends(actor)):
    with connect() as c:
        item = case_for(c, a, cid, True)
        writer(c, a)
        old = c.execute("SELECT * FROM journey_subjects WHERE workspace_id=%s AND id=%s", (a["workspace_id"], body.id)).fetchone()
        mine = {k: getattr(body, k) for k in ("document_system", "document_ref", "document_version", "destination_system", "binder_ref")}
        if old:
            if old["case_id"] != cid or any(old[k] != v for k, v in mine.items()):
                raise HTTPException(409, "Subject ID already holds a different definition.")
            return old
        last = c.execute("SELECT max(rev) AS rev FROM journey_subjects WHERE workspace_id=%s AND case_id=%s", (a["workspace_id"], cid)).fetchone()["rev"] or 0
        if last != body.expected_rev:
            raise HTTPException(409, "The document definition changed. Reload before saving.")
        row = c.execute("INSERT INTO journey_subjects(workspace_id,id,case_id,rev,actor_id,actor_name,document_system,document_ref,document_version,destination_system,binder_ref) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                        (a["workspace_id"], body.id, cid, last + 1, a["user_id"], a["name"], *mine.values())).fetchone()
        audit(c, a, cid, "journey_subject_set", "Document journey subject defined (revision %d)." % row["rev"], {"subject_id": str(body.id), **mine, "rev": row["rev"]})
        return row


def snapshot_links(c, a, cid):
    """Existing human-confirmed links join two *snapshot* records (no source-system identity). They apply to saved snapshots only;
    here they are listed as provenance a reviewer may explicitly adopt for a journey link."""
    from assessments import view
    out = []
    for d in c.execute("SELECT d.*,s.kind FROM assessment_decisions d JOIN case_assessments s ON (s.workspace_id,s.id)=(d.workspace_id,d.assessment_id) WHERE d.workspace_id=%s AND d.case_id=%s AND d.action='confirm_link' ORDER BY d.created_at DESC", (a["workspace_id"], cid)).fetchall():
        row = c.execute("SELECT * FROM case_assessments WHERE workspace_id=%s AND id=%s", (a["workspace_id"], d["assessment_id"])).fetchone()
        cand = d["details"].get("candidate", {})
        out.append({"id": d["id"], "at": d["created_at"], "actor": d["actor_name"], "reason": d["reason"], "left_id": cand.get("left_id"), "right_id": cand.get("right_id"),
                    "exact_matches": cand.get("exact_matches", []), "stale": view(c, a, row)["stale"], "applies_to": "saved snapshots only until explicitly adopted for a journey link"})
    return out


ADOPT_FIELDS = {"document": ("document_id",), "record": ("job_id", "upload_receipt_id")}


def snapshot_basis(c, a, cid, body, subj, j):
    if body.kind not in ADOPT_FIELDS:
        raise HTTPException(422, "Existing snapshot links cannot establish a destination mapping.")
    d = next((x for x in snapshot_links(c, a, cid) if x["id"] == body.snapshot_decision_id), None)
    if not d:
        raise HTTPException(422, "That confirmed link does not belong to this case and workspace.")
    if d["stale"]:
        raise HTTPException(409, "The evidence behind that confirmed link changed. Reassess it before relying on it.")
    values = {m["field"]: m["left"] for m in d["exact_matches"] if m["field"] in ("document_id", "job_id", "upload_receipt_id") and m["left"] == m["right"]}
    docs = {v for k, v in values.items() if k == "document_id"}
    if docs and docs != {subj["document_ref"]}:
        raise HTTPException(422, "That confirmed link concerns a different document than the one defined for this journey.")
    if not any(values.get(f) == body.from_ref for f in ADOPT_FIELDS[body.kind]):
        raise HTTPException(422, "The identifier is not one of the exact structured matches the reviewer confirmed.")
    if not docs:  # a job/receipt link only reaches this document through a receipt that a system record already ties to it
        receipts = {values.get("upload_receipt_id")} - {None}
        if not any(r["source_ref"] in receipts and classify(r, subj, [])["exact"] for r in j["records"]):
            raise HTTPException(422, "That confirmed link does not name this document or a receipt recorded for it.")


@router.post("/cases/{cid}/journey/links", status_code=201)
def add_link(cid: str, body: Link, a=Depends(actor)):
    with connect() as c:
        item = case_for(c, a, cid, True)
        writer(c, a)
        j, subj, links, exports, _ = current_journey(c, a, item)
        if not subj:
            raise HTTPException(409, "Define the document and intended binder first.")
        to = (subj["destination_system"], subj["binder_ref"]) if body.kind == "destination" else (subj["document_system"], subj["document_ref"])
        if (body.from_system, body.from_ref) == to:
            raise HTTPException(422, "A link must join two different source identifiers.")
        field = {"document": ("document_ref",), "record": ("source_ref", "transfer_ref"), "destination": ("binder_ref",)}[body.kind]
        if not any(r["source_system"] == body.from_system and r[f] == body.from_ref for r in j["records"] for f in field):
            raise HTTPException(422, "No imported record of %s carries that %s identifier." % (body.from_system, body.kind))
        old = c.execute("SELECT * FROM journey_links WHERE workspace_id=%s AND id=%s", (a["workspace_id"], body.id)).fetchone()
        if old:
            if old["case_id"] != cid or (old["kind"], old["from_system"], old["from_ref"], old["rationale"], old["evidence"], old["snapshot_decision_id"]) != (body.kind, body.from_system, body.from_ref, body.rationale, body.evidence, body.snapshot_decision_id):
                raise HTTPException(409, "Link ID already holds a different link.")
            return old
        for l in links:
            if not l["revoked_at"] and (l["kind"], l["from_system"], l["from_ref"]) == (body.kind, body.from_system, body.from_ref):
                raise HTTPException(409, "An active link already exists for %s %s (to %s %s). Revoke it before adding another." % (body.from_system, body.from_ref, l["to_system"], l["to_ref"]))
        if body.snapshot_decision_id:
            snapshot_basis(c, a, cid, body, subj, j)
        row = c.execute("INSERT INTO journey_links(workspace_id,id,case_id,kind,from_system,from_ref,to_system,to_ref,rationale,evidence,actor_id,actor_name,snapshot_decision_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                        (a["workspace_id"], body.id, cid, body.kind, body.from_system, body.from_ref, *to, body.rationale, body.evidence, a["user_id"], a["name"], body.snapshot_decision_id)).fetchone()
        audit(c, a, cid, "journey_link_confirmed", body.rationale, {"link_id": str(body.id), "kind": body.kind, "from": [body.from_system, body.from_ref], "to": list(to), "evidence": body.evidence, "snapshot_decision_id": str(body.snapshot_decision_id) if body.snapshot_decision_id else None})
        return row


@router.post("/cases/{cid}/journey/links/{lid}/revoke")
def revoke_link(cid: str, lid: UUID, body: Revoke, a=Depends(actor)):
    with connect() as c:
        case_for(c, a, cid, True)
        writer(c, a)
        row = c.execute("SELECT * FROM journey_links WHERE workspace_id=%s AND case_id=%s AND id=%s FOR UPDATE", (a["workspace_id"], cid, lid)).fetchone()
        if not row:
            raise HTTPException(404, "Link not found for this case.")
        if row["revoked_at"]:
            return row
        row = c.execute("UPDATE journey_links SET revoked_at=now(),revoked_by=%s,revoke_reason=%s WHERE workspace_id=%s AND id=%s RETURNING *", (a["name"], body.reason, a["workspace_id"], lid)).fetchone()
        audit(c, a, cid, "journey_link_revoked", body.reason, {"link_id": str(lid)})
        return row


@router.post("/cases/{cid}/journey/collection", status_code=201)
def draft_collection(cid: str, body: Collection, a=Depends(actor)):
    with connect() as c:
        item = case_for(c, a, cid)
        writer(c, a)
        old = c.execute("SELECT * FROM journey_plan_items WHERE workspace_id=%s AND id=%s", (a["workspace_id"], body.id)).fetchone()
        if old:
            if old["case_id"] != cid or (old["request_id"], old["stage"], old["gap_key"], old["question"], old["would_settle"], old["contact_id"]) != (body.request_id, body.stage, body.gap_key, body.question, body.would_settle, body.contact_id):
                raise HTTPException(409, "Plan item ID already holds a different item.")
            return old
        if body.prioritization_id and not c.execute("SELECT 1 FROM journey_prioritizations WHERE workspace_id=%s AND case_id=%s AND id=%s", (a["workspace_id"], cid, body.prioritization_id)).fetchone():
            raise HTTPException(422, "That saved request order does not belong to this case.")
        live = c.execute("SELECT p.request_id,r.status FROM journey_plan_items p JOIN information_requests r ON (r.workspace_id,r.id)=(p.workspace_id,p.request_id) WHERE p.workspace_id=%s AND p.case_id=%s AND p.gap_key=%s AND r.status<>'cancelled'", (a["workspace_id"], cid, body.gap_key)).fetchone()
        if live and len(body.duplicate_reason.strip()) < 10:
            raise HTTPException(409, {"message": "A %s request already targets this exact evidence. Open it instead, or give a reason to draft another." % live["status"], "matches": [{"request_id": str(live["request_id"]), "status": live["status"]}]})
        j = current_journey(c, a, item)[0]
        if not j:
            raise HTTPException(409, "Define the document and intended binder first.")
        stage = next(s for s in j["stages"] if s["stage"] == body.stage)
        if stage["assessment"] == "verified" or not any(g["key"] == body.gap_key for g in stage["gaps"]):
            raise HTTPException(409, "That stage no longer has this gap. Reload the journey.")
        run = c.execute("SELECT id FROM runs WHERE workspace_id=%s AND case_id=%s ORDER BY created_at DESC LIMIT 1", (a["workspace_id"], cid)).fetchone()
        if not run:
            raise HTTPException(409, "Run an investigation before drafting an information request.")
    from release_api import create_request
    from models import RequestCreate
    create_request(cid, RequestCreate(id=body.request_id, run_id=run["id"], title="Document journey: " + LABEL[body.stage] + " evidence", items=[body.question], contact_id=body.contact_id, due_at=body.due_at, duplicate_reason=body.duplicate_reason), a)
    with connect() as c:
        case_for(c, a, cid, True)
        writer(c, a)
        j = current_journey(c, a, case_for(c, a, cid))[0]
        aid = save_assessment(c, a, cid, j)
        row = c.execute("INSERT INTO journey_plan_items(workspace_id,id,case_id,stage,gap_key,assessment_id,request_id,contact_id,question,would_settle,actor_name) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING *",
                        (a["workspace_id"], body.id, cid, body.stage, body.gap_key, aid, body.request_id, body.contact_id, body.question, body.would_settle, a["name"])).fetchone()
        if row:
            audit(c, a, cid, "journey_collection_drafted", body.question, {"plan_item_id": str(body.id), "request_id": str(body.request_id), "stage": body.stage, "gap_key": body.gap_key, "assessment_id": str(aid), "no_message_sent": True, "from_suggested_order": body.prioritization_id is not None, "prioritization_id": str(body.prioritization_id) if body.prioritization_id else None})
        return row or c.execute("SELECT * FROM journey_plan_items WHERE workspace_id=%s AND id=%s", (a["workspace_id"], body.id)).fetchone()


def response_provenance(c, a, cid, ref):
    parts = ref.split(":")
    if parts[0] == "external" and len(parts) == 2:
        try:
            rid = UUID(parts[1])
        except ValueError:
            raise HTTPException(422, "Response reference is malformed.")
        r = c.execute("SELECT * FROM external_responses WHERE workspace_id=%s AND case_id=%s AND id=%s", (a["workspace_id"], cid, rid)).fetchone()
        if not r:
            raise HTTPException(404, "Response not found for this case.")
        if r["status"] != "accepted":
            raise HTTPException(422, "Only a reviewed (accepted) response can be recorded as an attested observation.")
        return r["submitted_at"], r["reviewer_name"], r["reviewed_at"]
    if parts[0] == "request" and len(parts) == 3 and parts[2].isdigit():
        try:
            rid = UUID(parts[1])
        except ValueError:
            raise HTTPException(422, "Response reference is malformed.")
        r = c.execute("SELECT responses FROM information_requests WHERE workspace_id=%s AND case_id=%s AND id=%s", (a["workspace_id"], cid, rid)).fetchone()
        i = int(parts[2])
        if not r or i >= len(r["responses"]):
            raise HTTPException(404, "Response not found for this case.")
        x = r["responses"][i]
        if x.get("external_response_id"):
            return response_provenance(c, a, cid, "external:" + x["external_response_id"])
        t = instant(x["recorded_at"])
        return t, x.get("actor_name"), t
    raise HTTPException(422, "Response reference is malformed.")


@router.post("/cases/{cid}/journey/attestations", status_code=201)
def attest(cid: str, body: Attest, a=Depends(actor)):
    with connect() as c:
        case_for(c, a, cid, True)
        writer(c, a)
        mine = (body.response_ref, body.stage, body.source_system, body.source_ref, body.document_ref, body.version, body.transfer_ref, body.binder_ref, body.status, body.observed_at, body.rationale)
        old = c.execute("SELECT * FROM journey_attestations WHERE workspace_id=%s AND id=%s", (a["workspace_id"], body.id)).fetchone()
        if old:
            if old["case_id"] != cid or (old["response_ref"], old["stage"], old["source_system"], old["source_ref"], old["document_ref"], old["version"], old["transfer_ref"], old["binder_ref"], old["status"], old["observed_at"], old["rationale"]) != mine:
                raise HTTPException(409, "Attestation ID already holds a different attestation.")
            return old
        if body.status is not None and body.status not in ALLOWED[body.stage]:
            raise HTTPException(422, "Status is not valid for " + LABEL[body.stage] + ".")
        submitted, reviewer, reviewed = response_provenance(c, a, cid, body.response_ref)
        if body.observed_at > submitted:
            raise HTTPException(422, "An observation cannot be later than the response that reports it.")
        row = c.execute("INSERT INTO journey_attestations(workspace_id,id,case_id,response_ref,response_submitted_at,response_reviewer,response_reviewed_at,stage,source_system,source_ref,document_ref,version,transfer_ref,binder_ref,status,observed_at,rationale,actor_id,actor_name) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                        (a["workspace_id"], body.id, cid, body.response_ref, submitted, reviewer, reviewed, body.stage, body.source_system, body.source_ref, body.document_ref, body.version, body.transfer_ref, body.binder_ref, body.status, body.observed_at, body.rationale, a["user_id"], a["name"])).fetchone()
        audit(c, a, cid, "journey_attestation_recorded", body.rationale, {"attestation_id": str(body.id), "response_ref": body.response_ref, "stage": body.stage, "verifies_nothing": True})
        return row


def reviewable_responses(c, a, cid):
    out = [{"ref": "external:" + str(r["id"]), "kind": "external response (reviewed)", "text": r["text"][:300], "reviewer": r["reviewer_name"], "submitted_at": r["submitted_at"]}
           for r in c.execute("SELECT * FROM external_responses WHERE workspace_id=%s AND case_id=%s AND status='accepted' ORDER BY submitted_at DESC", (a["workspace_id"], cid)).fetchall()]
    for q in c.execute("SELECT id,responses FROM information_requests WHERE workspace_id=%s AND case_id=%s", (a["workspace_id"], cid)).fetchall():
        for i, x in enumerate(q["responses"]):
            if not x.get("external_response_id"):
                out.append({"ref": "request:%s:%d" % (q["id"], i), "kind": "response recorded by " + (x.get("actor_name") or "a teammate"), "text": x["text"][:300], "reviewer": x.get("actor_name"), "submitted_at": x["recorded_at"]})
    return out


@router.post("/cases/{cid}/journey/outcomes", status_code=201)
def save_outcome(cid: str, body: OutcomeEdit, a=Depends(actor)):
    try:
        reqs = valid_requirements(body.requirements)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if reqs and (body.remediation_at is None or body.remediation_at > datetime.now(timezone.utc)):
        raise HTTPException(422, "A structured check needs a remediation time that is not in the future; only later observations can verify it.")
    with connect() as c:
        case_for(c, a, cid, True)
        writer(c, a)
        old = c.execute("SELECT * FROM journey_outcomes WHERE workspace_id=%s AND id=%s", (a["workspace_id"], body.id)).fetchone()
        mine = (body.key, body.description, reqs, body.required, body.remediation_at, body.retired)
        if old:
            if old["case_id"] != cid or (old["outcome_key"], old["description"], old["requirements"], old["required"], old["remediation_at"], old["retired"]) != mine:
                raise HTTPException(409, "Outcome revision ID already holds a different revision.")
            return old
        last = c.execute("SELECT max(rev) AS rev FROM journey_outcomes WHERE workspace_id=%s AND case_id=%s AND outcome_key=%s", (a["workspace_id"], cid, body.key)).fetchone()["rev"] or 0
        if last != body.expected_rev:
            raise HTTPException(409, "This outcome changed. Reload before saving.")
        row = c.execute("INSERT INTO journey_outcomes(workspace_id,id,case_id,outcome_key,rev,description,requirements,required,remediation_at,retired,actor_id,actor_name) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                        (a["workspace_id"], body.id, cid, body.key, last + 1, body.description, Jsonb(reqs) if reqs else None, body.required, body.remediation_at, body.retired, a["user_id"], a["name"])).fetchone()
        audit(c, a, cid, "journey_outcome_saved", body.description, {"outcome_id": str(body.id), "outcome_key": str(body.key), "rev": row["rev"], "retired": body.retired, "requirements": reqs})
        return row


@router.post("/cases/{cid}/journey/verify", status_code=201)
def verify(cid: str, body: Verify, a=Depends(actor)):
    with connect() as c:
        item = case_for(c, a, cid, True)
        writer(c, a)
        outcomes = current_outcomes(outcome_rows(c, a["workspace_id"], cid))
        human = {str(k): v.model_dump() for k, v in body.human.items()}
        if any(k not in {str(o["id"]) for o in outcomes if not o["requirements"]} for k in human):
            raise HTTPException(422, "Human assessments may only be given for current outcomes that have no structured check.")
        old = c.execute("SELECT * FROM journey_verifications WHERE workspace_id=%s AND id=%s", (a["workspace_id"], body.id)).fetchone()
        if old:
            if old["case_id"] != cid or old["human"] != human or old["rationale"] != body.rationale or sorted(x["outcome_id"] for x in old["results"]) != sorted(str(o["id"]) for o in outcomes):
                raise HTTPException(409, "Verification ID already holds a different verification.")
            return old
        now = datetime.now(timezone.utc)
        j, subj, links, exports, _ = current_journey(c, a, item, now)
        if not j:
            raise HTTPException(409, "Define the document and intended binder first.")
        results = evaluate(outcomes, human, j, subj, links, now, hours(c, a["workspace_id"]))
        status = overall(results)
        aid = save_assessment(c, a, cid, j)
        frozen = [{k: (str(o[k]) if k in ("id", "outcome_key") else o[k].isoformat() if k in ("remediation_at", "created_at") and o[k] else o[k]) for k in ("id", "outcome_key", "rev", "description", "requirements", "required", "remediation_at", "retired", "actor_name", "created_at")} for o in outcomes]
        row = c.execute("INSERT INTO journey_verifications(workspace_id,id,case_id,assessment_id,subject_rev,outcomes,human,results,overall,policy,evaluated_at,rationale,actor_id,actor_name) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                        (a["workspace_id"], body.id, cid, aid, subj["rev"], Jsonb(frozen), Jsonb(human), Jsonb(results), status, Jsonb({"freshness_hours": j["freshness_policy_hours"]}), now, body.rationale, a["user_id"], a["name"])).fetchone()
        audit(c, a, cid, "journey_verification_recorded", body.rationale, {"verification_id": str(body.id), "overall": status, "assessment_id": str(aid), "case_status_unchanged": True})
        return row


@router.get("/cases/{cid}/journey/replay")
def replay(cid: str, a=Depends(actor)):
    with connect() as c:
        item = case_for(c, a, cid)
        if a["role"] not in ("owner", "reviewer"):
            raise HTTPException(403, "Your workspace role does not permit this action.")
        w = a["workspace_id"]
        j, subj, links, exports, _ = current_journey(c, a, item)
        orows = outcome_rows(c, w, cid)
        out = []
        for v in verifications(c, w, cid):
            frozen = c.execute("SELECT result FROM journey_assessments WHERE workspace_id=%s AND id=%s", (w, v["assessment_id"])).fetchone()["result"]
            after = v["created_at"]
            now_by = {s["stage"]: s for s in j["stages"]} if j else {}
            out.append({
                "kind": "verification", "id": v["id"], "at": v["created_at"], "actor": v["actor_name"], "decision": v["overall"], "rationale": v["rationale"], "complete": True,
                "inputs": {"outcomes": v["outcomes"], "human_assessments": v["human"], "policy": v["policy"], "evaluated_at": v["evaluated_at"], "assessment_id": v["assessment_id"], "results": v["results"]},
                "known": [{"stage": s["stage"], "label": s["label"], "assessment": s["assessment"], "operational_status": s["operational_status"], "as_of": s["as_of"]} for s in frozen["stages"] if s["assessment"] == "verified"],
                "unknown": [{"stage": s["stage"], "label": s["label"], "assessment": s["assessment"], "missing": s["missing"], "conflicts": s["conflicts"]} for s in frozen["stages"] if s["assessment"] != "verified"],
                "changed_since": {
                    "exports": [{"source_system": e["source_system"], "export_ref": e["export_ref"], "observed_at": e["observed_at"], "imported_at": e["created_at"]} for e in exports if e["created_at"] > after],
                    "links": [{"id": l["id"], "kind": l["kind"], "from": [l["from_system"], l["from_ref"]], "created_at": l["created_at"], "revoked_at": l["revoked_at"]} for l in links if l["created_at"] > after or (l["revoked_at"] and l["revoked_at"] > after)],
                    "outcome_revisions": [{"outcome_key": o["outcome_key"], "rev": o["rev"], "description": o["description"], "retired": o["retired"], "created_at": o["created_at"]} for o in orows if o["created_at"] > after],
                    "stages": [{"stage": s["stage"], "was": s["assessment"], "now": now_by[s["stage"]]["assessment"], "status_was": s["operational_status"], "status_now": now_by[s["stage"]]["operational_status"]}
                               for s in frozen["stages"] if s["stage"] in now_by and (now_by[s["stage"]]["assessment"], now_by[s["stage"]]["operational_status"]) != (s["assessment"], s["operational_status"])],
                    "same_evidence_as_now": bool(j and j["fingerprint"] == frozen["fingerprint"]),
                }})
        for r in c.execute("SELECT r.id,r.decision,r.review_notes,r.reviewed_at,r.result,u.name AS reviewer FROM runs r LEFT JOIN users u ON u.id=r.reviewer_id WHERE r.workspace_id=%s AND r.case_id=%s AND r.decision IS NOT NULL ORDER BY r.reviewed_at DESC", (w, cid)).fetchall():
            cited = set(r["result"]["recommendation"]["evidence_ids"])
            events = c.execute("SELECT event_type,actor_name,created_at FROM case_events WHERE workspace_id=%s AND case_id=%s AND run_id=%s ORDER BY id", (w, cid, r["id"])).fetchall()
            out.append({"kind": "investigation_review", "id": r["id"], "at": r["reviewed_at"], "actor": r["reviewer"], "decision": r["decision"], "rationale": r["review_notes"], "complete": False,
                        "incomplete_reason": "Journey assessments were not retained with this decision, so what it knew about the document journey cannot be replayed. Facts are not reconstructed.",
                        "inputs": {"recommendation_status": r["result"]["recommendation"]["status"], "cited_procedures": [{"id": s["id"], "version": s.get("version"), "title": s.get("title")} for s in r["result"].get("sources", []) if s["id"] in cited], "audit_events": events}})
        out.sort(key=lambda x: x["at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return {"decisions": out, "note": "Recorded inputs and rationale only. Decisions are immutable and shown exactly as saved."}


@router.get("/cases/{cid}/journey/example")
def example(cid: str, shape: Literal["portal", "hub"] = "portal", a=Depends(actor)):
    """Synthetic mock-system export with its explicit mapping, sized to this case's scope (not a real vendor integration)."""
    with connect() as c:
        item = case_for(c, a, cid)
        subj = current_journey(c, a, item)[1]
        writer(c, a)
    return example_export(shape, item["study_id"], item["site_id"], subj)


def example_export(shape, study, site, subj=None, ref=None, observed_at=None, rows=None, complete=True):
    doc, ver = (subj["document_ref"], subj["document_version"]) if subj else ("DOC-5001", "2")
    binder = subj["binder_ref"] if subj else "BND-77"
    now = observed_at or datetime.now(timezone.utc).replace(microsecond=0)
    t = now.isoformat()
    ref = ref or ("EXAMPLE-%s-%s" % (shape.upper(), uuid4().hex[:8]))
    if shape == "portal":  # flat event rows, UPPER-case status words
        env = {"source_system": "mock-upload-portal", "export_ref": ref, "study_id": study, "site_id": site, "observed_at": t, "synthetic": True,
               "coverage": {"complete": complete, "stages": ["upload_receipt", "processing"]},
               "rows": rows or [{"event": "RECEIPT", "receipt_no": "RCPT-" + doc[-4:], "doc_id": doc, "doc_rev": ver, "state": "RECEIVED", "at": t},
                                {"event": "PROCESS", "receipt_no": "PROC-" + doc[-4:], "doc_id": doc, "doc_rev": ver, "state": "DONE", "at": t}]}
        mapping = {"stage_field": "event", "stage_values": {"RECEIPT": "upload_receipt", "PROCESS": "processing"},
                   "fields": {"source_ref": "receipt_no", "document_ref": "doc_id", "version": "doc_rev", "status": "state", "observed_at": "at"},
                   "status_values": {"RECEIVED": "received", "DONE": "completed", "WAIT": "pending", "ERR": "failed"}}
    else:  # nested job/filing records with their own vocabulary and an optional cross-reference
        env = {"source_system": "mock-binder-hub", "export_ref": ref, "study_id": study, "site_id": site, "observed_at": t, "synthetic": True,
               "coverage": {"complete": complete, "stages": ["transfer", "destination_filing", "binder_visibility"]},
               "rows": rows or [{"kind": "sync_job", "job": {"id": "JOB-" + doc[-4:]}, "item": {"upstream": doc, "rev": ver}, "outcome": "ok", "when": t, "target": binder},
                                {"kind": "filing", "job": {"id": "FILE-" + doc[-4:]}, "item": {"upstream": doc, "rev": ver}, "outcome": "filed", "when": t, "target": binder},
                                {"kind": "visibility", "job": {"id": "VIS-" + doc[-4:]}, "item": {"upstream": doc, "rev": ver}, "outcome": "shown", "when": t, "target": binder}]}
        mapping = {"stage_field": "kind", "stage_values": {"sync_job": "transfer", "filing": "destination_filing", "visibility": "binder_visibility"},
                   "fields": {"source_ref": "job.id", "document_ref": "item.upstream", "version": "item.rev", "status": "outcome", "observed_at": "when", "binder_ref": "target"},
                   "status_values": {"ok": "completed", "failed": "failed", "filed": "completed", "shown": "visible", "hidden": "not_visible"}}
    return {"export": env, "mapping": mapping, "note": "Synthetic mock-system export. Not a real vendor integration."}
