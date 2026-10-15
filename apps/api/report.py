"""Generate a readable PDF from frozen investigation evidence; never runs tools or a model."""

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)

FONT_DIR = Path(__file__).parent / "fonts"
for name, file in [
    ("TrialSans", "DejaVuSans.ttf"),
    ("TrialSansBold", "DejaVuSans-Bold.ttf"),
]:
    if name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / file)))
pdfmetrics.registerFontFamily(
    "TrialSans",
    normal="TrialSans",
    bold="TrialSansBold",
    italic="TrialSans",
    boldItalic="TrialSansBold",
)
INK = colors.HexColor("#24262b")
MUTED = colors.HexColor("#535963")
ACCENT = colors.HexColor("#98522e")
LINE = colors.HexColor("#e6e0d9")
STYLES = {
    "body": ParagraphStyle(
        "Body",
        fontName="TrialSans",
        fontSize=9,
        leading=14,
        textColor=INK,
        spaceAfter=7,
        splitLongWords=True,
    ),
    "small": ParagraphStyle(
        "Small",
        fontName="TrialSans",
        fontSize=7.5,
        leading=11,
        textColor=MUTED,
        spaceAfter=5,
        splitLongWords=True,
    ),
    "h1": ParagraphStyle(
        "Title",
        fontName="TrialSansBold",
        fontSize=23,
        leading=29,
        textColor=INK,
        spaceAfter=14,
    ),
    "h2": ParagraphStyle(
        "Heading",
        fontName="TrialSansBold",
        fontSize=13,
        leading=19,
        textColor=ACCENT,
        spaceBefore=15,
        spaceAfter=8,
        keepWithNext=True,
    ),
    "h3": ParagraphStyle(
        "Subheading",
        fontName="TrialSansBold",
        fontSize=10,
        leading=15,
        textColor=INK,
        spaceBefore=8,
        spaceAfter=6,
        keepWithNext=True,
    ),
}


def value(v):
    if v is None:
        return "Not recorded"
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, (dict, list)):
        return str(v)
    return str(v)


def p(text, style="body"):
    # Uploaded procedures, names, and draft text must never become ReportLab markup.
    return Paragraph(escape(value(text)).replace("\n", "<br/>"), STYLES[style])


def build_report(run, events, case=None):
    """Bytes only; workspace authorization belongs to the calling API endpoint."""
    result = run.get("result") or {}
    rec = result.get("recommendation") or {}
    sources = result.get("sources") or []
    cited = set(rec.get("evidence_ids") or [])
    case = case or {}
    output = BytesIO()
    story = [p("INVESTIGATION REPORT", "small"), p("From issue to evidence.", "h1")]
    story += [
        p(case.get("title") or "Saved investigation", "h3"),
        p("Case: " + value(run.get("case_id"))),
        p("Investigation: " + value(run.get("id")), "small"),
    ]
    details = [
        ["Review decision", run.get("decision") or "Pending review"],
        ["Evidence status", rec.get("status", "Not recorded")],
        [
            "Study / site",
            value(case.get("study_id")) + " / " + value(case.get("site_id")),
        ],
        ["Case status at export", case.get("status", "Not recorded")],
        ["Investigation created (UTC)", run.get("created_at")],
        [
            "Model / mode",
            value(run.get("model"))
            + " / "
            + value(result.get("mode_label") or result.get("mode")),
        ],
        ["Execution time", value(run.get("duration_seconds")) + " seconds"],
        [
            "Report generated (UTC)",
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ],
    ]
    table = Table(
        [[p(k, "small"), p(v, "small")] for k, v in details],
        colWidths=[155, 344],
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f3ede6")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story += [
        table,
        Spacer(1, 12),
        p(
            "Operational evaluation with synthetic data. Historical site records do not confirm current status, exact case linkage, or root cause. Approval reviews a recommendation; it does not send drafts or resolve a case.",
            "small",
        ),
    ]
    if case.get("description"):
        story += [p("Reported issue", "h2"), p(case["description"])]
    for title, key in [
        ("Summary", "summary"),
        ("Cause - unverified", "hypothesis"),
        ("Documented next steps", "recommended_next_step"),
    ]:
        story += [p(title, "h2"), p(rec.get(key) or "Not recorded")]
    story += [
        p("Human review", "h2"),
        p("Decision: " + value(run.get("decision") or "Pending review")),
    ]
    if run.get("decision"):
        story += [
            p("Reviewer: " + value(run.get("reviewer") or "Former member")),
            p("Reviewed (UTC): " + value(run.get("reviewed_at")), "small"),
            p(run.get("review_notes") or "No review notes recorded."),
        ]
    else:
        story += [p("No human decision was recorded at the time of export.", "small")]
    story += [
        p("Retrieved procedures", "h2"),
        p(
            "Cited sources support the proposed checks. Candidates were retrieved but not cited. Retrieval scores alone do not establish relevance.",
            "small",
        ),
    ]
    if not sources:
        story.append(p("No procedures retrieved."))
    for src in sources:
        label = "CITED" if src.get("id") in cited else "CANDIDATE - NOT CITED"
        story += [
            p(label + " | " + value(src.get("title")), "h3"),
            p(
                value(src.get("id"))
                + " | "
                + value(src.get("retrieval_method"))
                + " | score "
                + value(src.get("similarity")),
                "small",
            ),
            p(src.get("content") or "No content recorded."),
        ]
    story += [
        p("Operational observations", "h2"),
        p(
            "Historical site-level context. Verify current status and exact case linkage before acting.",
            "small",
        ),
    ]
    findings = result.get("operational_findings") or []
    if not findings:
        story.append(
            p("No issue-specific observations were derived from cited procedures.")
        )
    for f in findings:
        story += [
            p(
                value(f.get("record_id"))
                + " | "
                + ", ".join(f.get("knowledge_ids") or []),
                "h3",
            ),
            p(
                "Snapshot: "
                + value(f.get("snapshot_id"))
                + " | observed (UTC): "
                + value(f.get("observed_at")),
                "small",
            ),
        ]
        for fact in f.get("facts") or []:
            story.append(p("- " + value(fact)))
        story.append(
            p(
                f.get("scope") or "Exact case linkage and root cause are unconfirmed.",
                "small",
            )
        )
    for kind, bundle in (result.get("operational_evidence") or {}).items():
        story.append(p(kind.replace("_", " ").title() + " - saved snapshot", "h3"))
        snapshot = bundle.get("snapshot") or {}
        if not snapshot:
            story.append(p("No operational snapshot available."))
            continue
        for key in ["id", "study_id", "site_id", "observed_at", "synthetic"]:
            story.append(
                p(
                    key.replace("_", " ").title() + ": " + value(snapshot.get(key)),
                    "small",
                )
            )
        if bundle.get("truncated"):
            story.append(p("The saved record list was truncated.", "small"))
        records = bundle.get("records") or []
        if not records:
            story.append(p("No records in this snapshot."))
        for record in records:
            story.append(p("Record " + value(record.get("id")), "h3"))
            for key, val in record.items():
                story.append(
                    p(key.replace("_", " ").title() + ": " + value(val), "small")
                )
    story += [
        p("Engineering escalation drafts", "h2"),
        p(
            "UNSENT. Copying, downloading, or approving this report does not send an escalation or change external systems.",
            "small",
        ),
    ]
    drafts = result.get("escalation_drafts") or []
    if not drafts:
        story.append(p("No escalation drafts were created."))
    for draft in drafts:
        story += [
            p(draft.get("subject") or "Unsent draft", "h3"),
            p(
                "Draft: "
                + value(draft.get("id"))
                + " | procedure: "
                + ", ".join(draft.get("knowledge_ids") or []),
                "small",
            ),
            p(draft.get("body") or ""),
        ]
    story += [p("MCP tool trace", "h2")]
    for call in result.get("tool_calls") or []:
        story.append(
            p(
                value(call.get("tool"))
                + " | "
                + value(call.get("status"))
                + " | "
                + value(call.get("duration_seconds"))
                + " seconds"
            )
        )
        for key, val in (call.get("arguments") or {}).items():
            story.append(p(key + ": " + value(val), "small"))
    story += [p("Investigation audit trail", "h2")]
    if not events:
        story.append(p("No investigation events recorded."))
    for event in events:
        story += [
            p(value(event.get("event_type")).replace("_", " ").title(), "h3"),
            p(
                value(event.get("created_at"))
                + " | "
                + value(event.get("actor_name") or "System"),
                "small",
            ),
        ]
        if event.get("notes"):
            story.append(p(event["notes"]))
    story.append(
        p(
            "External actions recorded: "
            + (
                "None."
                if not result.get("external_actions_executed")
                else value(result["external_actions_executed"])
            ),
            "small",
        )
    )

    def footer(canvas, doc):
        canvas.saveState()
        w, h = A4
        canvas.setStrokeColor(LINE)
        canvas.line(48, h - 36, w - 48, h - 36)
        canvas.setFont("TrialSansBold", 9)
        canvas.setFillColor(INK)
        canvas.drawString(48, h - 26, "TrialOps")
        canvas.setFont("TrialSans", 7)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(w - 48, h - 26, "Evidence first. Human reviewed.")
        canvas.line(48, 39, w - 48, 39)
        canvas.drawString(
            48, 26, "Synthetic operational evaluation | Saved investigation evidence"
        )
        canvas.drawRightString(w - 48, 26, "Page " + str(doc.page))
        canvas.restoreState()

    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=48,
        rightMargin=48,
        topMargin=53,
        bottomMargin=54,
        title="TrialOps investigation " + value(run.get("case_id")),
        author="TrialOps",
        allowSplitting=1,
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


def build_case_report(package):
    """Readable complete case package with safely escaped, splittable provenance."""
    import json

    output = BytesIO()
    case = package["case"]
    story = [
        p("CASE EVIDENCE PACKAGE", "small"),
        p(case["title"], "h1"),
        p(case["id"] + " | " + case["study_id"] + " / " + case["site_id"]),
        p("Generated: " + value(package["exported_at"]), "small"),
        p(package["interpretation"], "small"),
    ]

    def render_detail(label, v, depth=0):
        if isinstance(v, dict):
            if label:
                story.append(p(label, "h3" if depth < 2 else "small"))
            if not v:
                story.append(p("None recorded.", "small"))
            for key, item in v.items():
                if key != "workspace_id":
                    render_detail(key.replace("_", " ").title(), item, depth + 1)
        elif isinstance(v, list):
            if label:
                story.append(p(label, "h3" if depth < 2 else "small"))
            if not v:
                story.append(p("None recorded.", "small"))
            for index, item in enumerate(v, 1):
                render_detail(
                    "Entry " + str(index) if isinstance(item, (dict, list)) else "",
                    item,
                    depth + 1,
                )
        else:
            text = (label + ": " if label else "") + value(v)
            story.append(p(text, "body" if len(text) > 120 else "small"))

    def section(title, items):
        story.append(p(title, "h2"))
        if not items:
            story.append(p("None recorded."))
            return
        for index, item in enumerate(items, 1):
            if isinstance(item, str):
                story.append(p(item))
            else:
                render_detail("Record " + str(index) if len(items) > 1 else "", item)

    section("Reported case", [case])
    section("Missing evidence / unresolved exceptions", package["missing_evidence"])
    section("Freshness and record conflicts", package["flags"])
    for index, run in enumerate(package["runs"], 1):
        story.append(p("Saved investigation " + str(index), "h2"))
        section(
            "Investigation and decision",
            [{k: v for k, v in run.items() if k != "result"}],
        )
        result = run["result"]
        section("Frozen recommendation", [result.get("recommendation", {})])
        section(
            "Exact cited procedure sections",
            [
                s
                for s in result.get("sources", [])
                if s.get("id")
                in result.get("recommendation", {}).get("evidence_ids", [])
            ],
        )
        section(
            "Frozen observation snapshots", [result.get("operational_evidence", {})]
        )
        section("Unsent drafts", result.get("escalation_drafts", []))
        section("Tool chronology", result.get("tool_calls", []))
    for title, key in [
        ("Retained procedure versions", "procedure_versions"),
        ("Immutable snapshot history", "snapshots"),
        ("Record comparisons", "comparisons"),
        ("Reviewed investigation checks", "checks"),
        ("Missing-information requests and responses", "requests"),
        ("Recorded supporting evidence", "evidence"),
        ("Human-confirmed related cases", "links"),
        ("Procedure reassessments", "reassessments"),
        ("Procedure-change impact reviews — deterministic comparison, human decision", "procedure_impact"),
        ("Recurrence groups and prevention plans — reviewer-confirmed; no causal claim", "recurrence"),
        ("Document journey — recorded status and evidence assessment are separate; a verified failure is still a failure", "journey_summary"),
        ("Suggested request order — deterministic rule, not an optimal or predicted ranking; each request could help assess the listed checks", "journey_priority_summary"),
        ("Request-order inputs: effort and prerequisites (user-entered; unknown stays unknown)", "journey_priority_inputs"),
        ("Request-to-check mapping corrections (reviewer reasons)", "journey_priority_mappings"),
        ("Saved request-order versions with reviewer overrides", "journey_prioritizations"),
        ("Document journey definitions (revisions)", "journey_subjects"),
        ("Document journey reviewer-confirmed links", "journey_links"),
        ("Document journey saved assessments", "journey_assessments"),
        ("Evidence collection plan references — drafts only; nothing sent", "journey_plan_items"),
        ("Reviewed-response attestations — context only; they verify nothing by themselves", "journey_attestations"),
        ("Expected outcome revisions", "journey_outcomes"),
        ("Resolution verification history — human resolution remains separate", "journey_verifications"),
        ("Explicitly recorded human effort", "effort"),
        ("Frozen selected-evidence assessments", "assessments"),
        ("Assessment human decisions and request drafts", "assessment_decisions"),
        ("External responses — unverified link holder, human review required", "external_responses"),
        ("Case watch updates — deterministic change detection; any model-assisted questions are labelled; nothing confirmed or sent", "watch_updates"),
        ("Case handover history", "handovers"),
        ("Blockers and waiting history", "blockers"),
        ("Elapsed blocked time (not human effort)", "waiting_time"),
        ("Case chronology and resolution evidence", "events"),
    ]:
        section(title, package.get(key, []))

    def footer(canvas, doc):
        canvas.saveState()
        w, h = A4
        canvas.setStrokeColor(LINE)
        canvas.line(48, 39, w - 48, 39)
        canvas.setFont("TrialSans", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(48, 26, "TrialOps | Case evidence | Drafts remain unsent")
        canvas.drawRightString(w - 48, 26, "Page " + str(doc.page))
        canvas.restoreState()

    SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=48,
        rightMargin=48,
        topMargin=48,
        bottomMargin=54,
        title="TrialOps case " + case["id"],
        allowSplitting=1,
    ).build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
