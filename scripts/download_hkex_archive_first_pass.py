"""Download the first-pass HKEX Archive documents from the manifest.

The manifest is generated under data/raw/_download_manifests and contains
candidate official HKEX document links. This script downloads the first-pass
recommended subset:

- missing rows where priority is P1_recommended, or relevance is high
- excluding optional country guides

It is intentionally sequential and polite because HKEX archive downloads can be
slow. The script is safe to re-run: existing non-empty files are skipped and a
fresh audit report is generated every run.
"""

from __future__ import annotations

import csv
import hashlib
import mimetypes
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "data" / "raw" / "_download_manifests" / "hkex_archive_download_manifest.csv"
LOG_PATH = PROJECT_ROOT / "data" / "raw" / "_download_manifests" / "hkex_archive_first_pass_download_log.csv"
AUDIT_PATH = PROJECT_ROOT / "data" / "raw" / "_download_manifests" / "hkex_archive_first_pass_audit.md"

REQUEST_TIMEOUT = 45
REQUEST_DELAY_SECONDS = 0.35
MAX_ATTEMPTS = 3
CHUNK_SIZE = 1024 * 128


@dataclass
class DownloadRow:
    category: str
    priority: str
    relevance: str
    title: str
    url: str
    suggested_local_path: str
    filename: str
    status: str
    source_page: str


def read_manifest() -> list[DownloadRow]:
    with MANIFEST_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [
            DownloadRow(
                category=row["category"],
                priority=row["priority"],
                relevance=row["relevance"],
                title=row["title"],
                url=row["url"],
                suggested_local_path=row["suggested_local_path"],
                filename=row["filename"],
                status=row["status"],
                source_page=row["source_page"],
            )
            for row in reader
        ]


def is_first_pass(row: DownloadRow) -> bool:
    if row.category == "archive_country_guides":
        return False
    if row.status != "missing":
        return False
    return row.priority == "P1_recommended" or row.relevance == "high"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sniff_file_kind(path: Path, content_type: str) -> tuple[bool, str]:
    if not path.exists() or path.stat().st_size == 0:
        return False, "missing_or_empty"

    with path.open("rb") as f:
        prefix = f.read(16)

    lower_type = content_type.lower()
    suffix = path.suffix.lower()
    if prefix.startswith(b"%PDF"):
        return True, "pdf"
    if prefix.startswith(b"PK\x03\x04"):
        return True, "zip_office"
    if prefix.startswith(b"\xd0\xcf\x11\xe0"):
        return True, "ole_office"
    if b"<html" in prefix.lower() or "text/html" in lower_type:
        return suffix in {".html", ".htm"}, "html"
    if suffix in {".doc", ".docx", ".xls", ".xlsx"}:
        return True, "office_by_extension"
    if "application/pdf" in lower_type:
        return True, "pdf_by_content_type"
    return True, "unknown_binary"


def iter_first_pass(rows: Iterable[DownloadRow]) -> list[DownloadRow]:
    selected = [row for row in rows if is_first_pass(row)]
    selected.sort(key=lambda r: (r.category, r.relevance != "high", r.title.lower(), r.url.lower()))
    return selected


def download_one(session: requests.Session, row: DownloadRow) -> dict[str, str]:
    target = PROJECT_ROOT / row.suggested_local_path
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists() and target.stat().st_size > 0:
        ok, kind = sniff_file_kind(target, "")
        return {
            "status": "skipped_existing",
            "http_status": "",
            "content_type": "",
            "bytes": str(target.stat().st_size),
            "sha256": sha256_file(target),
            "file_kind": kind,
            "valid_file": str(ok),
            "error": "",
        }

    last_error = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        tmp_path = target.with_suffix(target.suffix + ".part")
        if tmp_path.exists():
            tmp_path.unlink()

        try:
            with session.get(row.url, stream=True, timeout=REQUEST_TIMEOUT, allow_redirects=True) as response:
                http_status = str(response.status_code)
                content_type = response.headers.get("content-type", "")
                response.raise_for_status()

                with tmp_path.open("wb") as f:
                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)

            if tmp_path.stat().st_size == 0:
                raise RuntimeError("downloaded zero bytes")

            tmp_path.replace(target)
            ok, kind = sniff_file_kind(target, content_type)
            return {
                "status": "downloaded",
                "http_status": http_status,
                "content_type": content_type,
                "bytes": str(target.stat().st_size),
                "sha256": sha256_file(target),
                "file_kind": kind,
                "valid_file": str(ok),
                "error": "",
            }
        except Exception as exc:  # noqa: BLE001 - log and retry every network/file failure
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
        "category",
        "priority",
        "relevance",
        "title",
        "url",
        "suggested_local_path",
        "filename",
        "source_page",
        "status",
        "http_status",
        "content_type",
        "bytes",
        "sha256",
        "file_kind",
        "valid_file",
        "error",
    ]
    with LOG_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_audit(selected: list[DownloadRow], log_rows: list[dict[str, str]]) -> None:
    by_status = Counter(row["status"] for row in log_rows)
    by_category = defaultdict(Counter)
    by_kind = Counter()
    total_bytes = 0
    invalid = []
    failed = []

    for row in log_rows:
        by_category[row["category"]][row["status"]] += 1
        by_kind[row["file_kind"] or "(none)"] += 1
        try:
            total_bytes += int(row["bytes"])
        except ValueError:
            pass
        if row["status"] == "failed":
            failed.append(row)
        if row["valid_file"] != "True":
            invalid.append(row)

    lines = [
        "# HKEX Archive First-Pass Download Audit",
        "",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Scope",
        "",
        f"- Manifest: `{MANIFEST_PATH.relative_to(PROJECT_ROOT).as_posix()}`",
        f"- Expected first-pass rows: **{len(selected)}**",
        "- Selection rule: missing rows where `priority=P1_recommended` or `relevance=high`, excluding `archive_country_guides`.",
        f"- Download log: `{LOG_PATH.relative_to(PROJECT_ROOT).as_posix()}`",
        "",
        "## Result Summary",
        "",
        f"- Successful downloaded files: **{by_status['downloaded']}**",
        f"- Already present and skipped: **{by_status['skipped_existing']}**",
        f"- Failed rows: **{by_status['failed']}**",
        f"- Total local files accounted for: **{by_status['downloaded'] + by_status['skipped_existing']} / {len(selected)}**",
        f"- Total bytes accounted for: **{total_bytes:,}** ({total_bytes / 1024 / 1024:.2f} MiB)",
        "",
        "## By Category",
        "",
        "| Category | Expected | Downloaded | Skipped existing | Failed |",
        "|---|---:|---:|---:|---:|",
    ]

    expected_by_category = Counter(row.category for row in selected)
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
    invalid_non_failed = [row for row in invalid if row["status"] != "failed"]
    if invalid_non_failed:
        lines.extend(["| Category | Path | File kind | Bytes |", "|---|---|---:|---:|"])
        for row in invalid_non_failed:
            lines.append(
                f"| `{row['category']}` | `{row['suggested_local_path']}` | "
                f"{row['file_kind']} | {row['bytes']} |"
            )
    else:
        lines.append("No non-failed rows produced empty or invalid files.")

    lines.extend(["", "## Next Step", ""])
    if failed:
        lines.append("Re-run the script to retry failed rows. It will skip existing successful files.")
    else:
        lines.append("All first-pass rows are accounted for. The files are ready for ingestion compatibility checks.")

    AUDIT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"Manifest not found: {MANIFEST_PATH}")

    selected = iter_first_pass(read_manifest())
    run_at = datetime.now(timezone.utc).isoformat()

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; HKEX-RAG-Research/1.0; official-document-download)",
            "Accept": "application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/octet-stream,*/*",
        }
    )

    log_rows: list[dict[str, str]] = []
    for index, row in enumerate(selected, start=1):
        result = download_one(session, row)
        log_row = {
            "run_at": run_at,
            "category": row.category,
            "priority": row.priority,
            "relevance": row.relevance,
            "title": row.title,
            "url": row.url,
            "suggested_local_path": row.suggested_local_path,
            "filename": row.filename,
            "source_page": row.source_page,
            **result,
        }
        log_rows.append(log_row)
        print(
            f"[{index:03d}/{len(selected)}] {log_row['status']}: "
            f"{row.category}/{row.filename} ({log_row['bytes']} bytes)"
        )
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
