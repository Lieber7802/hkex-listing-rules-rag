"""Download recommended HKEX P1/P2 manifest rows and audit the result."""

from __future__ import annotations

import csv
import hashlib
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests
from urllib3.exceptions import InsecureRequestWarning


requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "data" / "raw" / "_download_manifests" / "hkex_p1_p2_download_manifest.csv"
LOG_PATH = PROJECT_ROOT / "data" / "raw" / "_download_manifests" / "hkex_p1_p2_download_log.csv"
AUDIT_PATH = PROJECT_ROOT / "data" / "raw" / "_download_manifests" / "hkex_p1_p2_download_audit.md"

DOWNLOAD_RECOMMENDATIONS = {
    "download",
    "download_optional_consolidated_pdf",
    "download_optional_core_html",
}

REQUEST_TIMEOUT = 45
REQUEST_DELAY_SECONDS = 0.2
MAX_ATTEMPTS = 3
CHUNK_SIZE = 1024 * 128


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_kind(path: Path, content_type: str = "") -> tuple[bool, str]:
    if not path.exists() or path.stat().st_size == 0:
        return False, "missing_or_empty"
    prefix = path.read_bytes()[:512]
    suffix = path.suffix.lower()
    lower_type = content_type.lower()
    if prefix.startswith(b"%PDF"):
        return True, "pdf"
    if prefix.startswith(b"PK\x03\x04"):
        return True, "zip_office"
    if prefix.startswith(b"\xd0\xcf\x11\xe0"):
        return True, "ole_office"
    if suffix in {".html", ".htm"}:
        text = prefix.lower()
        if b"<html" in text or b"<!doctype html" in text or "text/html" in lower_type:
            return True, "html"
        return True, "html_unknown_prefix"
    if suffix in {".xls", ".xlsx", ".doc", ".docx", ".ppt", ".pptx", ".zip"}:
        return True, "office_or_zip_by_extension"
    return True, "unknown_binary"


def selected_rows() -> list[dict[str, str]]:
    with MANIFEST_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    selected = [row for row in rows if row["recommendation"] in DOWNLOAD_RECOMMENDATIONS and row["status"] == "missing"]
    selected.sort(key=lambda row: (row["priority"], row["category"], row["title"].lower(), row["url"].lower()))
    return selected


def download_one(session: requests.Session, row: dict[str, str]) -> dict[str, str]:
    target = PROJECT_ROOT / row["suggested_local_path"]
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists() and target.stat().st_size > 0:
        valid, kind = file_kind(target)
        return {
            "status": "skipped_existing",
            "http_status": "",
            "content_type": "",
            "bytes": str(target.stat().st_size),
            "sha256": sha256_file(target),
            "file_kind": kind,
            "valid_file": str(valid),
            "error": "",
        }

    last_error = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        tmp_path = target.with_suffix(target.suffix + ".part")
        if tmp_path.exists():
            tmp_path.unlink()
        try:
            with session.get(row["url"], stream=True, timeout=REQUEST_TIMEOUT, allow_redirects=True, verify=False) as response:
                http_status = str(response.status_code)
                content_type = response.headers.get("content-type", "")
                response.raise_for_status()
                with tmp_path.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                        if chunk:
                            handle.write(chunk)
            if tmp_path.stat().st_size == 0:
                raise RuntimeError("downloaded zero bytes")
            tmp_path.replace(target)
            valid, kind = file_kind(target, content_type)
            return {
                "status": "downloaded",
                "http_status": http_status,
                "content_type": content_type,
                "bytes": str(target.stat().st_size),
                "sha256": sha256_file(target),
                "file_kind": kind,
                "valid_file": str(valid),
                "error": "",
            }
        except Exception as exc:  # noqa: BLE001
            last_error = f"attempt {attempt}: {type(exc).__name__}: {exc}"
            if tmp_path.exists():
                tmp_path.unlink()
            time.sleep(REQUEST_DELAY_SECONDS * attempt)

    return {
        "status": "failed",
        "http_status": "",
        "content_type": "",
        "bytes": "0",
        "sha256": "",
        "file_kind": "",
        "valid_file": "False",
        "error": last_error,
    }


def write_log(rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "run_at",
        "priority",
        "category",
        "recommendation",
        "title",
        "url",
        "suggested_local_path",
        "filename",
        "content_length",
        "content_type_manifest",
        "status",
        "http_status",
        "content_type",
        "bytes",
        "sha256",
        "file_kind",
        "valid_file",
        "error",
    ]
    with LOG_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_audit(selected: list[dict[str, str]], log_rows: list[dict[str, str]]) -> None:
    by_status = Counter(row["status"] for row in log_rows)
    by_category = defaultdict(Counter)
    by_kind = Counter(row["file_kind"] or "(none)" for row in log_rows)
    total_bytes = sum(int(row["bytes"]) for row in log_rows if row["bytes"].isdigit())
    failed = [row for row in log_rows if row["status"] == "failed"]
    invalid = [row for row in log_rows if row["valid_file"] != "True" and row["status"] != "failed"]
    expected_by_category = Counter(row["category"] for row in selected)
    for row in log_rows:
        by_category[row["category"]][row["status"]] += 1

    lines = [
        "# HKEX P1/P2 Recommended Download Audit",
        "",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Scope",
        "",
        f"- Manifest: `{MANIFEST_PATH.relative_to(PROJECT_ROOT).as_posix()}`",
        f"- Expected recommended rows: **{len(selected)}**",
        "- Selection rule: missing rows whose recommendation is `download`, `download_optional_consolidated_pdf`, or `download_optional_core_html`.",
        f"- Download log: `{LOG_PATH.relative_to(PROJECT_ROOT).as_posix()}`",
        "",
        "## Result Summary",
        "",
        f"- Downloaded files: **{by_status['downloaded']}**",
        f"- Already present and skipped: **{by_status['skipped_existing']}**",
        f"- Failed rows: **{by_status['failed']}**",
        f"- Total rows accounted for: **{by_status['downloaded'] + by_status['skipped_existing']} / {len(selected)}**",
        f"- Total bytes accounted for: **{total_bytes:,}** ({total_bytes / 1024 / 1024:.2f} MiB)",
        "",
        "## By Category",
        "",
        "| Category | Expected | Downloaded | Skipped existing | Failed |",
        "|---|---:|---:|---:|---:|",
    ]
    for category in sorted(expected_by_category):
        counts = by_category[category]
        lines.append(
            f"| `{category}` | {expected_by_category[category]} | "
            f"{counts['downloaded']} | {counts['skipped_existing']} | {counts['failed']} |"
        )

    lines.extend(["", "## File-Kind Check", "", "| File kind | Count |", "|---|---:|"])
    for kind, count in by_kind.most_common():
        lines.append(f"| `{kind}` | {count} |")

    lines.extend(["", "## Failed Rows", ""])
    if failed:
        lines.extend(["| Category | Title | URL | Error |", "|---|---|---|---|"])
        for row in failed:
            lines.append(f"| `{row['category']}` | {row['title']} | {row['url']} | {row['error']} |")
    else:
        lines.append("No failed rows.")

    lines.extend(["", "## Invalid or Empty File Checks", ""])
    if invalid:
        lines.extend(["| Category | Path | Kind | Bytes |", "|---|---|---|---:|"])
        for row in invalid:
            lines.append(f"| `{row['category']}` | `{row['suggested_local_path']}` | {row['file_kind']} | {row['bytes']} |")
    else:
        lines.append("No non-failed rows produced empty or invalid files.")

    lines.extend(["", "## Ingestion Note", ""])
    lines.append("Most P1/P2 sources downloaded here are `.html` pages. The current ingestion pipeline needs an HTML loader or HTML-to-text conversion before these can enter the FAISS/BM25 knowledge base.")
    AUDIT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    selected = selected_rows()
    run_at = datetime.now(timezone.utc).isoformat()
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; HKEX-RAG-Research/1.0; official-document-download)"})

    log_rows: list[dict[str, str]] = []
    for index, row in enumerate(selected, start=1):
        result = download_one(session, row)
        log_row = {
            "run_at": run_at,
            "priority": row["priority"],
            "category": row["category"],
            "recommendation": row["recommendation"],
            "title": row["title"],
            "url": row["url"],
            "suggested_local_path": row["suggested_local_path"],
            "filename": row["filename"],
            "content_length": row["content_length"],
            "content_type_manifest": row["content_type"],
            **result,
        }
        log_rows.append(log_row)
        print(f"[{index:03d}/{len(selected)}] {log_row['status']}: {row['category']}/{row['filename']} ({log_row['bytes']} bytes)")
        write_log(log_rows)
        write_audit(selected, log_rows)
        time.sleep(REQUEST_DELAY_SECONDS)

    write_log(log_rows)
    write_audit(selected, log_rows)
    failures = sum(1 for row in log_rows if row["status"] == "failed")
    print(f"Download audit written to {AUDIT_PATH}")
    print(f"Download log written to {LOG_PATH}")
    print(f"Failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
