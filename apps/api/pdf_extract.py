"""Isolated PDF parsing with process memory, CPU, size, and time limits."""

import io, json, resource, sys

resource.setrlimit(resource.RLIMIT_AS, (384 * 1024 * 1024, 384 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
try:
    from pypdf import PdfReader

    data = sys.stdin.buffer.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise ValueError("Upload must be 2 MB or smaller.")
    reader = PdfReader(io.BytesIO(data), strict=True)
    if reader.is_encrypted:
        raise ValueError("Encrypted PDFs are not supported. Upload a text version.")
    if len(reader.pages) > 30:
        raise ValueError("PDF must contain 30 pages or fewer.")
    parts = []
    for page in reader.pages:
        contents = page.get_contents()
        if contents and len(contents.get_data()) > 5 * 1024 * 1024:
            raise ValueError("PDF is too complex. Upload plain text.")
        parts.append(page.extract_text() or "")
        if sum(map(len, parts)) > 50000:
            raise ValueError("Extracted text exceeds 50,000 characters.")
    print(json.dumps({"content": "\n\n".join(parts)}))
except Exception as exc:
    print(json.dumps({"error": str(exc)[:200] or "PDF could not be read."}))
    sys.exit(1)
