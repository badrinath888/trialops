import json, re
from db import query, one
from embeddings import embed, MODEL

ALIASES = {
    "binder": ["binder", "sync", "synchronization"],
    "certificate": ["certificate", "certificates", "uploaded", "upload"],
    "monitor": ["monitor", "access", "permission", "invitation"],
    "signature": ["signature", "sign", "recipient"],
    "training": ["training", "course", "dashboard", "completion"],
}
STOP = set(
    "the a an to for in is are of and or this that at by with please review check investigate issue what will tomorrow yesterday synthetic site study".split()
)


def terms(text):
    words = set(re.findall(r"[a-z]{3,}", text.lower())) - STOP
    for triggers in ALIASES.values():
        if words.intersection(triggers):
            words.update(triggers)
    return words


def search_knowledge(w, text, semantic=True):
    vector = None
    pending = one(
        "SELECT EXISTS(SELECT 1 FROM knowledge_chunks c JOIN knowledge k ON k.workspace_id=c.workspace_id AND k.id=c.article_id WHERE k.workspace_id=%s AND NOT k.archived AND c.version=k.version AND (c.embedding IS NULL OR c.embedding_model IS DISTINCT FROM %s)) AS waiting",
        (w, MODEL),
    )["waiting"]
    if semantic and not pending:
        try:
            vector = json.dumps(embed([text[:1000]], "search_query")[0])
        except Exception:
            pass
    if vector:
        rows = query(
            """SELECT k.id AS article_id,k.title,k.category,k.version,c.number,c.content,
          1-(c.embedding <=> %s::vector) AS similarity
          FROM knowledge_chunks c JOIN knowledge k ON k.workspace_id=c.workspace_id AND k.id=c.article_id
          WHERE k.workspace_id=%s AND NOT k.archived AND c.version=k.version AND c.embedding_model=%s
          ORDER BY c.embedding <=> %s::vector LIMIT 5""",
            (vector, w, MODEL, vector),
        )
    else:
        rows = []
    method = "pgvector_cosine" if rows else "text_overlap"
    if not rows:
        rows = query(
            """SELECT k.id AS article_id,k.title,k.category,k.version,c.number,c.content FROM knowledge k
          JOIN knowledge_chunks c ON c.workspace_id=k.workspace_id AND c.article_id=k.id AND c.version=k.version
          WHERE k.workspace_id=%s AND NOT k.archived LIMIT 5000""",
            (w,),
        )
        needle = terms(text)
        for r in rows:
            matched = needle & terms(r["title"] + " " + r["content"])
            r["similarity"] = len(matched) / max(1, len(needle))
            r["matched_terms"] = sorted(matched)
        rows = sorted(
            rows, key=lambda x: (-x["similarity"], x["article_id"], x["number"])
        )[:5]
    for r in rows:
        r["id"] = f"{r['article_id']}#v{r['version']}-s{r['number']}"
        r["similarity"] = round(float(r["similarity"]), 4)
        r["retrieval_method"] = method
    return rows


def get_study(w, study):
    return one(
        "SELECT id,name FROM studies WHERE workspace_id=%s AND id=%s", (w, study)
    )


def get_site(w, site):
    return one(
        "SELECT id,name,study_id FROM sites WHERE workspace_id=%s AND id=%s", (w, site)
    )


def search_cases(w, text):
    rows = query(
        "SELECT id,title,study_id,site_id,status FROM cases WHERE workspace_id=%s ORDER BY updated_at DESC LIMIT 200",
        (w,),
    )
    needle = terms(text)
    return sorted(rows, key=lambda r: -len(needle & terms(r["title"])))[:5]


def get_operations(w, study, site):
    if not one(
        "SELECT id FROM sites WHERE workspace_id=%s AND id=%s AND study_id=%s",
        (w, site, study),
    ):
        raise ValueError("Site does not belong to study")
    row = one(
        "SELECT evidence FROM operations WHERE workspace_id=%s AND study_id=%s AND site_id=%s",
        (w, study, site),
    )
    return (
        row["evidence"]
        if row
        else {
            kind: {"snapshot": None, "records": [], "truncated": False}
            for kind in ["synchronization", "document_processing"]
        }
    )
