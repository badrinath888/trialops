import io, re
from fastapi import HTTPException


def chunks(text, size=1400):
    parts = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = max(
                text.rfind("\n", start + size // 2, end),
                text.rfind(". ", start + size // 2, end),
            )
            if boundary > start:
                end = boundary + 1
        parts.append(text[start:end].strip())
        if end == len(text):
            break
        start = max(start + 1, end - 120)
    return [p for p in parts if p]


def extract(filename, data):
    if len(data) > 2 * 1024 * 1024:
        raise HTTPException(413, "Upload must be 2 MB or smaller.")
    extension = filename.lower().rsplit(".", 1)[-1]
    try:
        if extension in ("txt", "md"):
            text = data.decode("utf-8-sig")
        elif extension == "pdf":
            import json, subprocess, sys
            from pathlib import Path

            try:
                result = subprocess.run(
                    [sys.executable, str(Path(__file__).with_name("pdf_extract.py"))],
                    input=data,
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
                parsed = json.loads(result.stdout)
                if result.returncode or parsed.get("error"):
                    raise HTTPException(
                        422, parsed.get("error", "PDF could not be read.")
                    )
                text = parsed["content"]
            except (subprocess.TimeoutExpired, ValueError, KeyError):
                raise HTTPException(
                    422,
                    "PDF could not be processed within the limit. Upload plain text.",
                )
        else:
            raise HTTPException(415, "Use a UTF-8 .txt, .md, or text-based .pdf file.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, "File could not be read. Try a plain-text version.")
    text = re.sub(r"\x00", "", text).strip()
    if len(text) < 30:
        raise HTTPException(
            422,
            "Not enough readable text. Scanned PDFs require OCR outside this application.",
        )
    if len(text) > 50000:
        raise HTTPException(
            422, "Extracted text exceeds 50,000 characters. Split the document."
        )
    return {
        "title": filename.rsplit(".", 1)[0][:200],
        "content": text,
        "characters": len(text),
    }
