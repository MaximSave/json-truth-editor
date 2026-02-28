import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import mammoth
from fastapi import APIRouter, HTTPException, UploadFile, File, Body
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse

router = APIRouter(tags=["pairs"])

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_DOC_EXT = {".pdf", ".doc", ".docx", ".txt"}
MAX_FILENAME = 200


def _safe_name(name: str) -> str:
    name = re.sub(r'[^\w\s\-\.\(\)]', '_', name)
    return name[:MAX_FILENAME]


def _pair_dir(pair_id: str) -> Path:
    if not re.match(r'^[a-f0-9\-]{36}$', pair_id):
        raise HTTPException(400, "Invalid pair ID")
    return DATA_DIR / pair_id


def _read_meta(pair_id: str) -> dict:
    meta_path = _pair_dir(pair_id) / "meta.json"
    if not meta_path.exists():
        raise HTTPException(404, "Pair not found")
    return json.loads(meta_path.read_text(encoding="utf-8"))


def _write_meta(pair_id: str, meta: dict):
    meta_path = _pair_dir(pair_id) / "meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _convert_docx_to_html(docx_path: Path) -> str:
    """Convert DOCX to HTML using mammoth (pure Python, no LibreOffice)."""
    with open(docx_path, "rb") as f:
        result = mammoth.convert_to_html(f)
    css = """
    <style>
      body { font-family: 'Segoe UI', Arial, sans-serif; padding: 24px;
             max-width: 800px; margin: 0 auto; line-height: 1.6;
             color: #e0e0e0; background: #1a1a2e; }
      table { border-collapse: collapse; width: 100%; margin: 12px 0; }
      td, th { border: 1px solid #333; padding: 8px; }
      img { max-width: 100%; }
      p { margin: 8px 0; }
    </style>
    """
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'>{css}</head><body>{result.value}</body></html>"


async def _convert_doc_to_docx(doc_path: Path) -> Path:
    """Convert .doc to .docx using LibreOffice headless. Returns path to .docx."""
    import asyncio
    proc = await asyncio.create_subprocess_exec(
        "libreoffice", "--headless", "--convert-to", "docx",
        "--outdir", str(doc_path.parent), str(doc_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise HTTPException(500, f"DOC→DOCX conversion failed: {stderr.decode()[:300]}")
    docx_path = doc_path.with_suffix(".docx")
    if not docx_path.exists():
        raise HTTPException(500, "DOC→DOCX conversion produced no output")
    return docx_path


def _process_doc_preview(pair_path: Path, doc_ext: str):
    """Generate HTML preview. For .doc, first convert to .docx, then to HTML."""
    if doc_ext == ".docx":
        docx_path = pair_path / "document.docx"
        html = _convert_docx_to_html(docx_path)
        (pair_path / "preview.html").write_text(html, encoding="utf-8")


async def _process_doc_upload(pair_path: Path, doc_path: Path, doc_ext: str):
    """Handle preview generation for uploaded document, including .doc→.docx conversion."""
    if doc_ext == ".doc":
        # Convert .doc → .docx, then .docx → HTML for preview
        docx_path = await _convert_doc_to_docx(doc_path)
        # Rename so preview logic finds it
        target = pair_path / "document.docx"
        if docx_path != target:
            shutil.copy2(docx_path, target)
        html = _convert_docx_to_html(target)
        (pair_path / "preview.html").write_text(html, encoding="utf-8")
    elif doc_ext == ".docx":
        html = _convert_docx_to_html(doc_path)
        (pair_path / "preview.html").write_text(html, encoding="utf-8")


# ---- endpoints ----

@router.post("/pairs")
async def create_pair(
    document: UploadFile = File(...),
    json_file: UploadFile = File(...),
):
    doc_ext = Path(document.filename or "").suffix.lower()
    if doc_ext not in ALLOWED_DOC_EXT:
        raise HTTPException(400, f"Document type not allowed: {doc_ext}")

    if not (json_file.filename or "").lower().endswith(".json"):
        raise HTTPException(400, "JSON file must have .json extension")

    json_bytes = await json_file.read()
    try:
        json_data = json.loads(json_bytes)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"Invalid JSON: {e}")

    pair_id = str(uuid.uuid4())
    pair_path = DATA_DIR / pair_id
    pair_path.mkdir(parents=True)

    try:
        doc_filename = f"document{doc_ext}"
        doc_path = pair_path / doc_filename
        doc_content = await document.read()
        doc_path.write_bytes(doc_content)

        # Generate preview (handles .doc → .docx → HTML, .docx → HTML)
        await _process_doc_upload(pair_path, doc_path, doc_ext)

        data_path = pair_path / "data.json"
        data_path.write_text(
            json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        meta = {
            "id": pair_id,
            "document_name": _safe_name(document.filename or "unknown"),
            "document_ext": doc_ext,
            "json_name": _safe_name(json_file.filename or "data.json"),
            "verified": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_meta(pair_id, meta)
        return meta

    except Exception:
        shutil.rmtree(pair_path, ignore_errors=True)
        raise


@router.post("/pairs/batch")
async def create_batch(files: list[UploadFile] = File(...)):
    """
    Batch upload: accepts a mix of documents and JSON files.
    Pairs are matched by filename stem (e.g., order_123.pdf + order_123.json).
    """
    docs = {}   # stem -> UploadFile
    jsons = {}  # stem -> UploadFile

    for f in files:
        name = f.filename or ""
        ext = Path(name).suffix.lower()
        stem = Path(name).stem

        if ext in ALLOWED_DOC_EXT:
            docs[stem] = f
        elif ext == ".json":
            jsons[stem] = f

    # Match pairs by stem
    matched_stems = set(docs.keys()) & set(jsons.keys())
    if not matched_stems:
        raise HTTPException(400,
            "No matching pairs found. Files must share the same name "
            "(e.g., order_123.pdf + order_123.json)")

    created = []
    errors = []

    for stem in sorted(matched_stems):
        doc = docs[stem]
        jf = jsons[stem]

        doc_ext = Path(doc.filename or "").suffix.lower()
        json_bytes = await jf.read()

        try:
            json_data = json.loads(json_bytes)
        except json.JSONDecodeError as e:
            errors.append({"file": jf.filename, "error": f"Invalid JSON: {e}"})
            continue

        pair_id = str(uuid.uuid4())
        pair_path = DATA_DIR / pair_id
        pair_path.mkdir(parents=True)

        try:
            doc_path = pair_path / f"document{doc_ext}"
            doc_content = await doc.read()
            doc_path.write_bytes(doc_content)

            await _process_doc_upload(pair_path, doc_path, doc_ext)

            (pair_path / "data.json").write_text(
                json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            meta = {
                "id": pair_id,
                "document_name": _safe_name(doc.filename or "unknown"),
                "document_ext": doc_ext,
                "json_name": _safe_name(jf.filename or "data.json"),
                "verified": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            _write_meta(pair_id, meta)
            created.append(meta)

        except Exception as e:
            shutil.rmtree(pair_path, ignore_errors=True)
            errors.append({"file": doc.filename, "error": str(e)})

    unmatched_docs = set(docs.keys()) - matched_stems
    unmatched_jsons = set(jsons.keys()) - matched_stems

    return {
        "created": created,
        "errors": errors,
        "unmatched_documents": [docs[s].filename for s in sorted(unmatched_docs)],
        "unmatched_jsons": [jsons[s].filename for s in sorted(unmatched_jsons)],
    }


@router.get("/pairs")
async def list_pairs():
    pairs = []
    if not DATA_DIR.exists():
        return pairs
    for d in sorted(DATA_DIR.iterdir()):
        meta_path = d / "meta.json"
        if d.is_dir() and meta_path.exists():
            try:
                pairs.append(json.loads(meta_path.read_text(encoding="utf-8")))
            except Exception:
                continue
    return pairs


@router.get("/pairs/{pair_id}")
async def get_pair(pair_id: str):
    return _read_meta(pair_id)


@router.get("/pairs/{pair_id}/document")
async def get_document_preview(pair_id: str):
    meta = _read_meta(pair_id)
    pair_path = _pair_dir(pair_id)

    # TXT → plain text
    if meta["document_ext"] == ".txt":
        txt_path = pair_path / "document.txt"
        if not txt_path.exists():
            raise HTTPException(404, "Document file not found")
        return PlainTextResponse(
            txt_path.read_text(encoding="utf-8", errors="replace"),
            media_type="text/plain; charset=utf-8",
        )

    # DOCX → HTML preview
    if meta["document_ext"] == ".docx":
        html_path = pair_path / "preview.html"
        if html_path.exists():
            return HTMLResponse(html_path.read_text(encoding="utf-8"))
        # Fallback: regenerate
        doc_path = pair_path / "document.docx"
        if doc_path.exists():
            html = _convert_docx_to_html(doc_path)
            html_path.write_text(html, encoding="utf-8")
            return HTMLResponse(html)
        raise HTTPException(404, "Document not found")

    # DOC → was converted to DOCX → HTML at upload time
    if meta["document_ext"] == ".doc":
        html_path = pair_path / "preview.html"
        if html_path.exists():
            return HTMLResponse(html_path.read_text(encoding="utf-8"))
        return HTMLResponse(
            "<html><body style='background:#1a1a2e;color:#e0e0e0;padding:40px;font-family:sans-serif'>"
            "<h2>⚠️ Предпросмотр недоступен</h2>"
            "<p>Не удалось сконвертировать .doc файл.</p>"
            "<p><a href='original' style='color:#6366f1'>Скачать оригинал</a></p>"
            "</body></html>"
        )

    # PDF → serve directly
    pdf_path = pair_path / "document.pdf"
    if not pdf_path.exists():
        raise HTTPException(404, "Preview not available")
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline"},
    )


@router.get("/pairs/{pair_id}/original")
async def download_original(pair_id: str):
    meta = _read_meta(pair_id)
    pair_path = _pair_dir(pair_id)
    doc_path = pair_path / f"document{meta['document_ext']}"
    if not doc_path.exists():
        raise HTTPException(404, "Original not found")
    return FileResponse(doc_path, filename=meta["document_name"])


@router.get("/pairs/{pair_id}/json")
async def get_json(pair_id: str):
    _read_meta(pair_id)
    data_path = _pair_dir(pair_id) / "data.json"
    if not data_path.exists():
        raise HTTPException(404, "JSON not found")
    return json.loads(data_path.read_text(encoding="utf-8"))


@router.put("/pairs/{pair_id}/json")
async def update_json(pair_id: str, payload: dict = Body(...)):
    _read_meta(pair_id)
    data_path = _pair_dir(pair_id) / "data.json"
    data_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"status": "saved", "id": pair_id}


@router.patch("/pairs/{pair_id}/verify")
async def toggle_verified(pair_id: str):
    meta = _read_meta(pair_id)
    meta["verified"] = not meta["verified"]
    _write_meta(pair_id, meta)
    return {"id": pair_id, "verified": meta["verified"]}


@router.delete("/pairs")
async def delete_all_pairs():
    """Delete ALL pairs and their files."""
    count = 0
    if DATA_DIR.exists():
        for d in list(DATA_DIR.iterdir()):
            if d.is_dir() and (d / "meta.json").exists():
                shutil.rmtree(d)
                count += 1
    return {"status": "deleted", "count": count}


@router.delete("/pairs/{pair_id}")
async def delete_pair(pair_id: str):
    pair_path = _pair_dir(pair_id)
    if not pair_path.exists():
        raise HTTPException(404, "Pair not found")
    shutil.rmtree(pair_path)
    return {"status": "deleted", "id": pair_id}