import json
import math
import os
import urllib.request

MODEL = "nomic-embed-text:v1.5"
DIMENSIONS = 768


def embed(texts, purpose):
    if purpose not in ("search_document", "search_query"):
        raise ValueError("Invalid embedding purpose")

    payload = {
        "model": MODEL,
        "input": [f"{purpose}: {text}" for text in texts],
        "truncate": False,
        "keep_alive": "1m",
    }

    base_url = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
    request = urllib.request.Request(
        base_url + "/api/embed",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=180) as response:
        vectors = json.load(response)["embeddings"]

    if len(vectors) != len(texts):
        raise ValueError("Unexpected embedding count")

    for vector in vectors:
        if len(vector) != DIMENSIONS:
            raise ValueError("Unexpected embedding dimensions")
        if not all(math.isfinite(value) for value in vector):
            raise ValueError("Invalid embedding values")

    return vectors
