"""Execute versioned synthetic scenarios without reading/writing operational cases."""

import copy, json, os, time
from pathlib import Path
from datetime import datetime, timezone
from seed import operations, ARTICLES
from tools import terms
from workflows import evidence_flags, canonical
from operational_evidence import instant


def dataset():
    data = json.loads(
        Path(__file__).with_name("evaluation_data").joinpath("v1.json").read_text()
    )
    data["sha256"] = canonical({"dataset": data, "procedures": ARTICLES})
    return data


def configuration(mode):
    return {
        "mode": mode,
        "model": os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
        if mode == "ollama"
        else "procedure-matcher",
        "temperature": 0,
        "num_predict": 300,
        "num_ctx": 8192,
        "source_input": "versioned synthetic supplied sources",
        "dataset_sha256": dataset()["sha256"],
    }


def evaluate(config, heartbeat=lambda: None):
    from investigation import investigate_evidence

    data = dataset()
    if data["sha256"] != config["dataset_sha256"]:
        raise ValueError("Evaluation dataset changed. Create a new evaluation.")
    results = []
    for scenario in data["scenarios"]:
        heartbeat()
        start = time.monotonic()
        item = {
            "scenario_id": scenario["id"],
            "kind": scenario["kind"],
            "expected_status": scenario["expected_status"],
            "expected_drafts": scenario["expected_drafts"],
        }
        try:
            case = {
                "id": "EVALUATION-" + scenario["id"],
                "title": scenario["title"],
                "description": scenario["description"],
                "study_id": "CT-204",
                "site_id": "SITE-104",
                "category": "unknown",
            }
            evidence = operations()
            evidence.update(
                study={"id": "CT-204"},
                site={"id": "SITE-104", "study_id": "CT-204"},
                cases=[],
            )
            if scenario.get("sync_status"):
                evidence["synchronization"]["records"][0]["status"] = scenario[
                    "sync_status"
                ]
            if scenario.get("processing_status"):
                evidence["document_processing"]["records"][0].update(
                    processing_status=scenario["processing_status"],
                    binder_visible=scenario["processing_status"] == "processed",
                )
            if scenario.get("conflict"):
                r = copy.deepcopy(evidence["document_processing"]["records"][0])
                r.update(
                    id="PROC-CONFLICT",
                    processing_status="processed",
                    binder_visible=True,
                )
                evidence["document_processing"]["records"].append(r)
            if scenario.get("missing"):
                for kind in ("synchronization", "document_processing"):
                    evidence[kind] = {
                        "snapshot": None,
                        "records": [],
                        "truncated": False,
                    }
            needle = terms(case["title"] + " " + case["description"])
            sources = []
            for a in ARTICLES:
                content = a["content"] + (
                    scenario.get("source_suffix", "")
                    if a["id"] == scenario.get("procedure")
                    else ""
                )
                sources.append(
                    {
                        "id": a["id"] + "#v1-s1",
                        "article_id": a["id"],
                        "title": a["title"],
                        "category": a["category"],
                        "version": 1,
                        "number": 1,
                        "content": content,
                        "retrieval_method": "evaluation_supplied_sources",
                        "similarity": round(
                            len(needle & terms(a["title"] + " " + content))
                            / max(1, len(needle)),
                            4,
                        ),
                    }
                )
            evidence["articles"] = sources
            result = investigate_evidence(
                case, evidence, [], mode=config["mode"], model=config["model"]
            )
            citations = result["recommendation"]["evidence_ids"]
            flags = evidence_flags(
                case,
                evidence,
                scenario.get("freshness_hours"),
                instant(scenario["now"])
                if scenario.get("now")
                else datetime.now(timezone.utc),
            )
            item.update(
                actual_status=result["recommendation"]["status"],
                citations=citations,
                actual_drafts=len(result["escalation_drafts"]),
                flags=flags,
                citation_validity=bool(
                    set(citations).issubset({s["id"] for s in sources})
                ),
                abstention_correct=result["recommendation"]["status"]
                == scenario["expected_status"],
                escalation_rule_correct=len(result["escalation_drafts"])
                == scenario["expected_drafts"],
                flag_correct=not scenario.get("expected_flag")
                or any(f["type"] == scenario["expected_flag"] for f in flags),
                external_actions=result["external_actions_executed"],
                execution_failure=None,
            )
        except Exception as e:
            item.update(execution_failure=type(e).__name__ + ": " + str(e))
        item["latency_seconds"] = round(time.monotonic() - start, 3)
        results.append(item)
    counts = {
        "scenarios": len(results),
        "execution_failures": sum(bool(x["execution_failure"]) for x in results),
    }
    for name in (
        "citation_validity",
        "abstention_correct",
        "escalation_rule_correct",
        "flag_correct",
    ):
        counts[name + "_passed"] = sum(x.get(name) is True for x in results)
    return {
        "dataset_version": data["version"],
        "dataset_sha256": data["sha256"],
        "configuration": config,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "scenarios": results,
        "counts": counts,
        "subjective_judgment": None,
    }
