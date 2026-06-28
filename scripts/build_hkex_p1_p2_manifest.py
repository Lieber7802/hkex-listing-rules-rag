"""Build a clean P1/P2 HKEX download manifest.

This manifest covers the project download-list items not handled by the
Archive first-pass download:

P1:
- Listing Review Committee Decisions
- Headline Categories
- Checklists, Forms & Templates
- Enforcement guidance / disciplinary materials

P2:
- Guide for New Listing Applicants
- Overseas / Biotech / Specialist Technology listing-path pages

Many of these sources are official HTML pages rather than standalone PDFs. They
are still downloaded as raw source files, but current ingestion will need an
HTML loader or an HTML-to-text conversion step before indexing them.
"""

from __future__ import annotations

import csv
import re
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from urllib3.exceptions import InsecureRequestWarning


requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = PROJECT_ROOT / "data" / "raw"
OUT_DIR = RAW_ROOT / "_download_manifests"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MANIFEST_PATH = OUT_DIR / "hkex_p1_p2_download_manifest.csv"
SUMMARY_PATH = OUT_DIR / "hkex_p1_p2_download_recommendation.md"

REQUEST_TIMEOUT = 30
REQUEST_DELAY_SECONDS = 0.2


@dataclass(frozen=True)
class Candidate:
    priority: str
    category: str
    title: str
    url: str
    local_dir: str
    recommendation: str
    note: str


P1_STATIC_PAGES = [
    Candidate("P1", "headline_categories", "Headline Categories", "https://www.hkex.com.hk/Listing/Rules-and-Resources/Checklist-forms-and-templates/Headline-Categories?sc_lang=en", "headline_categories", "download", "Main Headline Categories page."),
    Candidate("P1", "headline_categories", "Headline Categories - Main Board", "https://www.hkex.com.hk/Listing/Rules-and-Resources/Checklist-forms-and-templates/Headline-Categories/Main-Board?sc_lang=en", "headline_categories", "download", "Main Board headline mapping page."),
    Candidate("P1", "headline_categories", "Headline Categories - GEM", "https://www.hkex.com.hk/Listing/Rules-and-Resources/Checklist-forms-and-templates/Headline-Categories/GEM?sc_lang=en", "headline_categories", "download", "GEM headline mapping page."),
    Candidate("P1", "forms_templates", "Checklists, Forms & Templates", "https://www.hkex.com.hk/Listing/Rules-and-Resources/Checklist-forms-and-templates?sc_lang=en", "forms_templates", "download", "Main checklists/forms/templates page."),
    Candidate("P1", "forms_templates", "Forms - New Applicants", "https://www.hkex.com.hk/Listing/Rules-and-Resources/Checklist-forms-and-templates/Forms/New-Applicants/Main-Board-New-Applicants?sc_lang=en", "forms_templates", "download", "New applicants / Main Board forms page."),
    Candidate("P1", "forms_templates", "Forms - Main Board New Applicants", "https://www.hkex.com.hk/Listing/Rules-and-Resources/Checklist-forms-and-templates/Forms/New-Applicants/Main-Board-New-Applicants?sc_lang=en", "forms_templates", "download", "Main Board new applicant forms."),
    Candidate("P1", "forms_templates", "Forms - GEM New Applicants", "https://www.hkex.com.hk/Listing/Rules-and-Resources/Checklist-forms-and-templates/Forms/New-Applicants/GEM-New-Applicants?sc_lang=en", "forms_templates", "download", "GEM new applicant forms."),
    Candidate("P1", "forms_templates", "Forms - Equity Securities Issuers", "https://www.hkex.com.hk/Listing/Rules-and-Resources/Checklist-forms-and-templates/Forms/Equity-Securities-Issuers/Main-Board-Issuers?sc_lang=en", "forms_templates", "download", "Equity securities issuer / Main Board forms page."),
    Candidate("P1", "forms_templates", "Forms - Main Board Issuers", "https://www.hkex.com.hk/Listing/Rules-and-Resources/Checklist-forms-and-templates/Forms/Equity-Securities-Issuers/Main-Board-Issuers?sc_lang=en", "forms_templates", "download", "Main Board listed issuer forms."),
    Candidate("P1", "forms_templates", "Forms - GEM Issuers", "https://www.hkex.com.hk/Listing/Rules-and-Resources/Checklist-forms-and-templates/Forms/Equity-Securities-Issuers/GEM-Issuers?sc_lang=en", "forms_templates", "download", "GEM listed issuer forms."),
    Candidate("P1", "forms_templates", "Forms - Debt Securities Issuers", "https://www.hkex.com.hk/Listing/Rules-and-Resources/Checklist-forms-and-templates/Forms/Debt-Securities-Issuers/Main-Board-Issuers?sc_lang=en", "forms_templates", "download", "Debt securities issuer / Main Board forms page."),
    Candidate("P1", "forms_templates", "Forms - Main Board Debt Securities Issuers", "https://www.hkex.com.hk/Listing/Rules-and-Resources/Checklist-forms-and-templates/Forms/Debt-Securities-Issuers/Main-Board-Issuers?sc_lang=en", "forms_templates", "download", "Main Board debt securities issuer forms."),
    Candidate("P1", "forms_templates", "Forms - GEM Debt Securities Issuers", "https://www.hkex.com.hk/Listing/Rules-and-Resources/Checklist-forms-and-templates/Forms/Debt-Securities-Issuers/GEM-Issuers?sc_lang=en", "forms_templates", "download", "GEM debt securities issuer forms."),
    Candidate("P1", "forms_templates", "Forms - Structured Products Issuers", "https://www.hkex.com.hk/Listing/Rules-and-Resources/Checklist-forms-and-templates/Forms/Structured-Products-Issuers?sc_lang=en", "forms_templates", "download", "Structured products issuer forms."),
    Candidate("P1", "enforcement_guidance", "Disciplinary and Enforcement - Overview", "https://www.hkex.com.hk/Listing/Disciplinary-and-Enforcement/Overview?sc_lang=en", "enforcement_guidance", "download", "Current enforcement overview page."),
    Candidate("P1", "enforcement_guidance", "Enforcement Guidance Materials", "https://www.hkex.com.hk/Listing/Disciplinary-and-Enforcement/Enforcement-Guidance-Materials?sc_lang=en", "enforcement_guidance", "download", "Current enforcement guidance entry page."),
    Candidate("P1", "enforcement_guidance", "Disciplinary Procedures", "https://www.hkex.com.hk/Listing/Disciplinary-and-Enforcement/Disciplinary-Procedures?sc_lang=en", "enforcement_guidance", "download", "Disciplinary procedures page."),
    Candidate("P1", "enforcement_guidance", "Disciplinary Sanctions", "https://www.hkex.com.hk/Listing/Disciplinary-and-Enforcement/Disciplinary-Sanctions?sc_lang=en", "enforcement_guidance", "download", "Disciplinary sanctions page."),
    Candidate("P1", "enforcement_guidance", "Enforcement Bulletin", "https://www.hkex.com.hk/Listing/Disciplinary-and-Enforcement/Enforcement-Bulletin?sc_lang=en", "enforcement_guidance", "download", "Enforcement bulletin page."),
    Candidate("P1", "enforcement_guidance", "Enforcement Statistics", "https://www.hkex.com.hk/Listing/Disciplinary-and-Enforcement/Enforcement-Statistics?sc_lang=en", "enforcement_guidance", "download", "Enforcement statistics page."),
]

P2_STATIC_PAGES = [
    Candidate("P2", "new_listing_applicants", "Guide for New Listing Applicants - Consolidated PDF", "https://www.hkex.com.hk/-/media/HKEX-Market/Listing/Rules-and-Guidance/Interpretation-and-Guidance/Guide-for-New-Listing-Applicants/newlist_consolidated.pdf", "guidance/new_listing_applicants", "download_optional_consolidated_pdf", "Consolidated P2 PDF from original download list."),
    Candidate("P2", "new_listing_applicants", "Guide for New Listing Applicants", "https://en-rules.hkex.com.hk/rulebook/guide-new-listing-applicants", "guidance/new_listing_applicants", "download_optional_core_html", "Core en-rules HTML entry page."),
    Candidate("P2", "new_listing_applicants", "Special Listing Regimes", "https://en-rules.hkex.com.hk/rulebook/chapter-2-special-listing-regimes", "guidance/new_listing_applicants", "download_optional_core_html", "P2 special listing regimes chapter."),
    Candidate("P2", "special_listing_paths", "Biotech Companies", "https://www.hkex.com.hk/Join-Our-Markets/IPO/Biotech?sc_lang=en", "guidance/special_listing_paths", "optional_review", "Biotech listing path page."),
    Candidate("P2", "special_listing_paths", "Specialist Technology Companies", "https://www.hkex.com.hk/Join-Our-Markets/IPO/Specialist-Technology-Companies?sc_lang=en", "guidance/special_listing_paths", "optional_review", "Specialist technology listing path page."),
    Candidate("P2", "special_listing_paths", "Overseas Companies", "https://www.hkex.com.hk/Join-Our-Markets/IPO/Overseas-Issuers?sc_lang=en", "guidance/special_listing_paths", "optional_review", "Overseas issuer listing path page."),
]


def slugify(text: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return value[:100] or "document"


def extension_for(url: str) -> str:
    path = urlparse(url).path.lower()
    match = re.search(r"(\.pdf|\.docx?|\.xlsx?|\.xls|\.pptx?|\.zip)$", path)
    if match:
        return match.group(1)
    return ".html"


def filename_for(candidate: Candidate) -> str:
    path_name = Path(urlparse(candidate.url).path).name
    ext = extension_for(candidate.url)
    if path_name and "." in path_name:
        name = path_name
    else:
        name = slugify(candidate.title) + ext
    return re.sub(r'[<>:"/\\|?*]+', "_", name.replace(",", "_").replace(" ", "_"))


def existing_files() -> dict[str, str]:
    files = {}
    for path in RAW_ROOT.rglob("*"):
        if path.is_file() and path.name != ".gitkeep":
            files[path.name.lower()] = path.relative_to(PROJECT_ROOT).as_posix()
    return files


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (compatible; HKEX-RAG-Research/1.0)"})
    return s


def fetch_soup(s: requests.Session, url: str) -> BeautifulSoup:
    response = s.get(url, timeout=REQUEST_TIMEOUT, verify=False)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def listing_review_committee_candidates() -> list[Candidate]:
    base = "https://en-rules.hkex.com.hk/rulebook/listing-review-committee-decisions"
    s = session()
    soup = fetch_soup(s, base)
    candidates = [
        Candidate("P1", "review_committee_decisions", "Listing Review Committee Decisions", base, "review_committee_decisions", "download", "Main LRC decisions page."),
    ]

    year_urls: dict[str, str] = {}
    for anchor in soup.find_all("a", href=True):
        title = " ".join(anchor.get_text(" ", strip=True).split())
        if re.fullmatch(r"20\d{2}", title):
            year_urls[title] = urljoin(base, anchor["href"])

    individual_urls: dict[str, str] = {}
    for year, year_url in sorted(year_urls.items()):
        candidates.append(
            Candidate("P1", "review_committee_decisions", f"Listing Review Committee Decisions - {year}", year_url, "review_committee_decisions", "download", "LRC decisions year index page.")
        )
        year_soup = fetch_soup(s, year_url)
        for anchor in year_soup.find_all("a", href=True):
            title = " ".join(anchor.get_text(" ", strip=True).split())
            href = urljoin(year_url, anchor["href"])
            path = urlparse(href).path
            if re.search(r"/rulebook/\d{1,2}-[a-z]+-20\d{2}$", path, re.I):
                individual_urls[href] = title or Path(path).name
        time.sleep(REQUEST_DELAY_SECONDS)

    for href, title in sorted(individual_urls.items(), key=lambda item: item[0]):
        candidates.append(
            Candidate("P1", "review_committee_decisions", f"LRC Decision - {title}", href, "review_committee_decisions/decisions", "download", "Individual LRC decision page.")
        )
    return candidates


def all_candidates() -> list[Candidate]:
    candidates = []
    candidates.extend(P1_STATIC_PAGES)
    candidates.extend(listing_review_committee_candidates())
    candidates.extend(P2_STATIC_PAGES)
    seen = set()
    unique = []
    for candidate in candidates:
        key = candidate.url.split("?")[0].lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def estimate(s: requests.Session, url: str) -> tuple[str, str, str]:
    try:
        response = s.head(url, timeout=REQUEST_TIMEOUT, allow_redirects=True, verify=False)
        if response.status_code >= 400 or not response.headers.get("content-length"):
            response.close()
            response = s.get(url, timeout=REQUEST_TIMEOUT, stream=True, allow_redirects=True, verify=False)
        response.raise_for_status()
        size = response.headers.get("content-length", "")
        content_type = response.headers.get("content-type", "")
        response.close()
        return size, content_type, ""
    except Exception as exc:  # noqa: BLE001
        return "", "", f"{type(exc).__name__}: {exc}"


def build_manifest() -> list[dict[str, str]]:
    files = existing_files()
    s = session()
    rows = []
    candidates = all_candidates()
    for index, candidate in enumerate(candidates, start=1):
        filename = filename_for(candidate)
        local_path = f"data/raw/{candidate.local_dir}/{filename}"
        size, content_type, error = estimate(s, candidate.url)
        status = "exists" if filename.lower() in files else "missing"
        rows.append(
            {
                "priority": candidate.priority,
                "category": candidate.category,
                "recommendation": "skip_existing" if status == "exists" else candidate.recommendation,
                "title": candidate.title,
                "url": candidate.url,
                "suggested_local_path": local_path,
                "filename": filename,
                "status": status,
                "existing_path": files.get(filename.lower(), ""),
                "content_length": size,
                "content_type": content_type,
                "metadata_error": error,
                "note": candidate.note,
            }
        )
        print(f"[{index:03d}/{len(candidates)}] {candidate.priority} {candidate.category} {filename} size={size or '?'}")
        time.sleep(REQUEST_DELAY_SECONDS)
    return rows


def write_outputs(rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "priority",
        "category",
        "recommendation",
        "title",
        "url",
        "suggested_local_path",
        "filename",
        "status",
        "existing_path",
        "content_length",
        "content_type",
        "metadata_error",
        "note",
    ]
    with MANIFEST_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    by_category = Counter(row["category"] for row in rows)
    by_rec = Counter(row["recommendation"] for row in rows)
    recommended = [
        row for row in rows if row["recommendation"] in {"download", "download_optional_consolidated_pdf", "download_optional_core_html"}
    ]
    known_total = sum(int(row["content_length"]) for row in rows if row["content_length"].isdigit())
    known_rec = sum(int(row["content_length"]) for row in recommended if row["content_length"].isdigit())

    lines = [
        "# HKEX P1/P2 Download Recommendation",
        "",
        "This manifest covers remaining P1/P2 items from the project download list. It includes official HTML pages where the source is not available as a standalone PDF/XLS/DOC file.",
        "",
        "## Summary",
        "",
        f"- Candidate rows: **{len(rows)}**",
        f"- Recommended download rows: **{len(recommended)}**",
        f"- Known candidate size: **{known_total:,} bytes** ({known_total / 1024 / 1024:.2f} MiB)",
        f"- Known recommended size: **{known_rec:,} bytes** ({known_rec / 1024 / 1024:.2f} MiB)",
        "",
        "## By Category",
        "",
        "| Category | Candidate rows |",
        "|---|---:|",
    ]
    for category, count in sorted(by_category.items()):
        lines.append(f"| `{category}` | {count} |")
    lines.extend(["", "## By Recommendation", "", "| Recommendation | Rows |", "|---|---:|"])
    for rec, count in sorted(by_rec.items()):
        lines.append(f"| `{rec}` | {count} |")
    lines.extend(
        [
            "",
            "## Download Policy",
            "",
            "- Download all missing P1 rows.",
            "- Download P2 consolidated/core guide rows.",
            "- Keep P2 special listing path pages as `optional_review` unless the project scope expands.",
            "- Treat downloaded `.html` files as raw sources; ingestion requires HTML-to-text conversion or an HTML loader.",
            "",
            "## Files",
            "",
            f"- CSV manifest: `{MANIFEST_PATH.relative_to(PROJECT_ROOT).as_posix()}`",
            f"- Recommendation summary: `{SUMMARY_PATH.relative_to(PROJECT_ROOT).as_posix()}`",
        ]
    )
    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    rows = build_manifest()
    write_outputs(rows)
    print(f"Wrote {MANIFEST_PATH} ({len(rows)} rows)")
    print(f"Wrote {SUMMARY_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
