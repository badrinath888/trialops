"""Evidence workflow rules; no generated diagnoses, external delivery, or case closure."""

import copy, csv, hashlib, io, json, re
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import HTTPException
from psycopg.types.json import Jsonb
from operational_evidence import KINDS, instant, validate_operations

STATES = {"not_checked", "verified", "needs_follow_up", "not_applicable"}


def canonical(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def checklist_suggestions(result):
    cited = set(result["recommendation"]["evidence_ids"])
    sources = [copy.deepcopy(s) for s in result.get("sources", []) if s["id"] in cited]
    # A whole cited section is retained verbatim rather than inventing mandatory substeps.
    items = [
        {
            "id": str(uuid4()),
            "text": s["content"],
            "source_id": s["id"],
            "suggestion": True,
            "state": "not_checked",
            "notes": "",
            "evidence_refs": [],
        }
        for s in sources
    ]
    return sources, items


def check_items(items, sources, old=None, actor=None):
    source_ids = {s["id"] for s in sources}
    old_by = {i["id"]: i for i in old or []}
    if not 1 <= len(items) <= 50:
        raise HTTPException(422, "Use 1–50 checks.")
    ids = set()
    result = []
    for item in items:
        if item["id"] in ids:
            raise HTTPException(422, "Check identifiers must be unique.")
        ids.add(item["id"])
        if item["source_id"] not in source_ids:
            raise HTTPException(
                422, "Check must reference an exact cited procedure section."
            )
        if item["state"] not in STATES:
            raise HTTPException(422, "Invalid check state.")
        if (
            item["state"] in {"needs_follow_up", "not_applicable"}
            and len(item.get("notes", "").strip()) < 5
        ):
            raise HTTPException(422, "Explain follow-up or not-applicable checks.")
        if item["state"] == "verified" and not item.get("evidence_refs"):
            raise HTTPException(422, "Verified checks need supporting evidence.")
        saved = copy.deepcopy(item)
        previous = old_by.get(item["id"])
        if not previous or any(
            previous.get(k) != item.get(k)
            for k in ("state", "notes", "evidence_refs", "text")
        ):
            saved["actor_id"] = str(actor["user_id"])
            saved["actor_name"] = actor["name"]
            saved["recorded_at"] = datetime.now(timezone.utc).isoformat()
        else:
            for k in ("actor_id", "actor_name", "recorded_at"):
                if k in previous:
                    saved[k] = previous[k]
        result.append(saved)
    return result


def compare_snapshots(before, after):
    if (before["workspace_id"], before["study_id"], before["site_id"]) != (
        after["workspace_id"],
        after["study_id"],
        after["site_id"],
    ):
        raise HTTPException(
            422, "Comparison requires the same workspace, study and site."
        )
    if instant(after["observed_at"]) <= instant(before["observed_at"]):
        raise HTTPException(422, "Choose a later observation for the second snapshot.")
    changes = []
    for kind in KINDS:
        left = {r["id"]: r for r in before["evidence"][kind]["records"]}
        right = {r["id"]: r for r in after["evidence"][kind]["records"]}
        for rid in sorted(left.keys() | right.keys()):
            a, b = left.get(rid), right.get(rid)
            fields = (
                []
                if a is None or b is None
                else [
                    {"field": k, "before": a.get(k), "after": b.get(k)}
                    for k in sorted(a.keys() | b.keys())
                    if k != "snapshot_id" and a.get(k) != b.get(k)
                ]
            )
            state = (
                "added"
                if a is None
                else "missing"
                if b is None
                else "changed"
                if fields
                else "unchanged"
            )
            changes.append(
                {
                    "kind": kind,
                    "record_id": rid,
                    "state": state,
                    "fields": fields,
                    "before": a,
                    "after": b,
                }
            )
    return {
        "before_observed_at": instant(before["observed_at"]).isoformat(),
        "after_observed_at": instant(after["observed_at"]).isoformat(),
        "records": changes,
        "interpretation": "A missing record is absent from the later snapshot; it does not establish resolution.",
    }


def evidence_flags(case, evidence, freshness_hours=None, now=None):
    now = now or datetime.now(timezone.utc)
    flags = []
    by_entity = {}
    for kind in KINDS:
        group = evidence.get(kind) or {}
        snapshot = group.get("snapshot")
        if not snapshot:
            flags.append(
                {
                    "type": "missing",
                    "kind": kind,
                    "explanation": "No observation snapshot is available for "
                    + kind.replace("_", " ")
                    + ".",
                }
            )
            continue
        try:
            observed = instant(snapshot["observed_at"])
            age = (now - observed).total_seconds() / 3600
            if age < 0:
                flags.append(
                    {
                        "type": "chronology",
                        "snapshot_id": snapshot["id"],
                        "explanation": "Observation timestamp is in the future.",
                    }
                )
            if freshness_hours is not None and age > float(freshness_hours):
                flags.append(
                    {
                        "type": "stale",
                        "snapshot_id": snapshot["id"],
                        "age_hours": round(age, 2),
                        "limit_hours": float(freshness_hours),
                        "explanation": f"Observation age {age:.1f} hours exceeds the workspace policy of {freshness_hours} hours.",
                    }
                )
            if (
                snapshot.get("study_id") != case["study_id"]
                or snapshot.get("site_id") != case["site_id"]
            ):
                flags.append(
                    {
                        "type": "scope",
                        "snapshot_id": snapshot["id"],
                        "explanation": "Snapshot study/site differs from the case.",
                    }
                )
            for r in group.get("records", []):
                key = (kind, r.get("document_id") or r["id"])
                status = r.get("status", r.get("processing_status"))
                by_entity.setdefault(key, []).append(
                    {"record_id": r["id"], "status": status}
                )
                if (
                    r.get("assigned_study_id", case["study_id"]) != case["study_id"]
                    or r.get("snapshot_id") != snapshot["id"]
                ):
                    flags.append(
                        {
                            "type": "scope",
                            "record_id": r["id"],
                            "explanation": "Record snapshot or assigned study does not match the observation scope.",
                        }
                    )
                fields = (
                    ("last_attempt_at", "source_updated_at", "destination_updated_at")
                    if kind == "synchronization"
                    else ("uploaded_at", "status_since")
                )
                for field in fields:
                    if r.get(field) and instant(r[field]) > observed:
                        flags.append(
                            {
                                "type": "chronology",
                                "record_id": r["id"],
                                "field": field,
                                "value": r[field],
                                "explanation": field.replace("_", " ")
                                + " occurs after observation time.",
                            }
                        )
                if kind == "document_processing" and instant(
                    r["status_since"]
                ) < instant(r["uploaded_at"]):
                    flags.append(
                        {
                            "type": "chronology",
                            "record_id": r["id"],
                            "explanation": "Processing status predates upload.",
                        }
                    )
        except (ValueError, KeyError, TypeError) as e:
            flags.append(
                {
                    "type": "chronology",
                    "snapshot_id": snapshot.get("id"),
                    "explanation": "Invalid or missing timestamp/record field: "
                    + str(e),
                }
            )
    for key, records in by_entity.items():
        if len({r["status"] for r in records}) > 1:
            flags.append(
                {
                    "type": "conflict",
                    "entity": key[1],
                    "records": records,
                    "explanation": "The same stable entity has conflicting statuses in this observation.",
                }
            )
    return flags


def save_snapshot(c, w, study, site, evidence, actor=None):
    validate_operations({"study_id": study, "site_id": site}, evidence)
    snapshots = [
        evidence[k].get("snapshot") for k in KINDS if evidence[k].get("snapshot")
    ]
    if not snapshots:
        raise HTTPException(422, "Import requires an observation snapshot.")
    snapshot = snapshots[0]
    sha = canonical(evidence)
    if instant(snapshot["observed_at"]) > datetime.now(timezone.utc):
        raise HTTPException(422, "Snapshot observation cannot be in the future.")
    old = c.execute(
        "SELECT * FROM snapshot_history WHERE workspace_id=%s AND study_id=%s AND site_id=%s AND external_id=%s FOR UPDATE",
        (w, study, site, snapshot["id"]),
    ).fetchone()
    if old:
        if old["content_hash"] != sha:
            raise HTTPException(
                409,
                "Snapshot identifier already contains different immutable evidence. Use a new snapshot ID.",
            )
        return old, False
    row = c.execute(
        "INSERT INTO snapshot_history(workspace_id,id,study_id,site_id,external_id,observed_at,evidence,content_hash,actor_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (
            w,
            uuid4(),
            study,
            site,
            snapshot["id"],
            instant(snapshot["observed_at"]),
            Jsonb(evidence),
            sha,
            actor,
        ),
    ).fetchone()
    latest = c.execute(
        "SELECT * FROM snapshot_history WHERE workspace_id=%s AND study_id=%s AND site_id=%s ORDER BY observed_at DESC,created_at DESC LIMIT 1",
        (w, study, site),
    ).fetchone()
    c.execute(
        "INSERT INTO operations(workspace_id,study_id,site_id,evidence) VALUES(%s,%s,%s,%s) ON CONFLICT(workspace_id,study_id,site_id) DO UPDATE SET evidence=EXCLUDED.evidence,updated_at=now()",
        (w, study, site, Jsonb(latest["evidence"])),
    )
    return row, True


def remember_existing(c, w=None):
    params = (w,) if w else ()
    condition = " WHERE workspace_id=%s" if w else ""
    for row in c.execute("SELECT * FROM operations" + condition, params).fetchall():
        # Preserve the stored current snapshot before accepting an update.
        evidence = row["evidence"]
        snap = next(
            (
                evidence.get(k, {}).get("snapshot")
                for k in KINDS
                if evidence.get(k, {}).get("snapshot")
            ),
            None,
        )
        if not snap:
            continue
        c.execute(
            "INSERT INTO snapshot_history(workspace_id,id,study_id,site_id,external_id,observed_at,evidence,content_hash) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (
                row["workspace_id"],
                uuid4(),
                row["study_id"],
                row["site_id"],
                snap["id"],
                instant(snap["observed_at"]),
                Jsonb(evidence),
                canonical(evidence),
            ),
        )


def procedure_impact(c, w, article_id, new_version):
    runs = c.execute(
        "SELECT r.* FROM runs r JOIN cases c ON (c.workspace_id,c.id)=(r.workspace_id,r.case_id) WHERE r.workspace_id=%s AND c.status='open'",
        (w,),
    ).fetchall()
    for run in runs:
        cited = set(run["result"]["recommendation"]["evidence_ids"])
        for src in run["result"].get("sources", []):
            if (
                src["id"] not in cited
                or src.get("article_id") != article_id
                or src.get("version", new_version) >= new_version
            ):
                continue
            c.execute(
                "INSERT INTO procedure_reassessments(workspace_id,run_id,article_id,old_version,new_version,case_id) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (w, run["id"], article_id, src["version"], new_version, run["case_id"]),
            )


def preview_rows(raw, format, mapping, sites):
    if len(raw) > 100000:
        raise HTTPException(413, "Import preview is limited to 100 KB.")
    try:
        rows = (
            list(csv.DictReader(io.StringIO(raw)))
            if format == "csv"
            else json.loads(raw)
        )
    except (ValueError, csv.Error):
        raise HTTPException(422, "Cannot parse the CSV/JSON input.")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 200:
        raise HTTPException(422, "Provide an array or CSV with 1–200 rows.")
    accepted = []
    rejected = []
    seen = set()
    groups = {}
    for index, row in enumerate(rows, 1):
        try:
            if not isinstance(row, dict):
                raise ValueError("Row must be an object")
            row = {mapping.get(k, k): v for k, v in row.items()}
            study = str(row["study_id"])
            site = str(row["site_id"])
            sid = str(row["snapshot_id"])
            kind = row["kind"]
            for value in [study, site, sid, str(row["id"])]:
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{1,99}", value):
                    raise ValueError(
                        "Identifiers must use letters, numbers, underscores or hyphens"
                    )
            if (study, site) not in sites:
                raise ValueError("Study/site relationship is outside this workspace")
            if kind not in KINDS:
                raise ValueError("Use synchronization or document_processing")
            key = (study, site, sid, kind, str(row["id"]))
            if key in seen:
                raise ValueError("Duplicate record in this import")
            group_key = (study, site, sid)
            observed = instant(str(row["observed_at"]))
            if observed > datetime.now(timezone.utc):
                raise ValueError("Observation is in the future")
            if str(row.get("synthetic", "")).lower() != "true":
                raise ValueError("synthetic must be true")
            snapshot = {
                "id": sid,
                "study_id": study,
                "site_id": site,
                "observed_at": observed.isoformat(),
                "synthetic": True,
            }
            record = {
                k: v
                for k, v in row.items()
                if k not in {"study_id", "site_id", "observed_at", "synthetic", "kind"}
            }
            record["id"] = str(record["id"])
            record["snapshot_id"] = sid
            if kind == "document_processing":
                record["binder_visible"] = (
                    str(record.get("binder_visible", "")).lower() == "true"
                    if str(record.get("binder_visible", "")).lower()
                    in {"true", "false"}
                    else record.get("binder_visible")
                )
            for k in list(record):
                if record[k] == "":
                    record[k] = None
            evidence = {
                k: {
                    "snapshot": snapshot,
                    "records": [record] if k == kind else [],
                    "truncated": False,
                }
                for k in KINDS
            }
            validate_operations({"study_id": study, "site_id": site}, evidence)
            group = groups.setdefault(
                group_key,
                {
                    "study_id": study,
                    "site_id": site,
                    "evidence": {
                        k: {"snapshot": snapshot, "records": [], "truncated": False}
                        for k in KINDS
                    },
                    "rows": [],
                },
            )
            if group["evidence"][kind]["snapshot"] != snapshot:
                raise ValueError("All rows of a snapshot must share observation time")
            if len(group["evidence"][kind]["records"]) >= 10:
                raise ValueError("At most 10 records per kind in a snapshot")
            group["evidence"][kind]["records"].append(record)
            group["rows"].append(index)
            seen.add(key)
            accepted.append(
                {
                    "row": index,
                    "study_id": study,
                    "site_id": site,
                    "snapshot_id": sid,
                    "kind": kind,
                    "record_id": record["id"],
                }
            )
        except (ValueError, KeyError, TypeError) as e:
            rejected.append({"row": index, "reason": str(e)})
    # Catch cross-kind duplicate IDs/invalid snapshot groups before any commit.
    valid = []
    for group in groups.values():
        try:
            validate_operations(group, group["evidence"])
            valid.append(group)
        except (ValueError, KeyError, TypeError) as e:
            accepted = [r for r in accepted if r["row"] not in group["rows"]]
            rejected.extend({"row": i, "reason": str(e)} for i in group["rows"])
    return accepted, rejected, valid
