"""Convert downloaded HKEX HTML sources into ingestion-ready Markdown.

The current ingestion pipeline supports PDF and text/Markdown files, not HTML.
This script extracts only likely page-body content from downloaded official
HTML files and writes cleaned Markdown under data/raw/html_converted/.

Noise control:
- skips internal folders such as data/raw/_download_manifests
- removes script/style/nav/header/footer/aside/media and common menu containers
- extracts from article/main when available instead of full body
- filters common HKEX site navigation lines
- records extraction metrics for audit before indexing
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from bs4 import BeautifulSoup, NavigableString, Tag


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = PROJECT_ROOT / "data" / "raw"
OUTPUT_ROOT = RAW_ROOT / "html_converted"
AUDIT_PATH = RAW_ROOT / "_download_manifests" / "hkex_html_conversion_audit.md"
LOG_PATH = RAW_ROOT / "_download_manifests" / "hkex_html_conversion_log.csv"

SKIP_DIR_NAMES = {"_download_manifests", "html_converted"}

REMOVE_TAGS = {
    "script",
    "style",
    "noscript",
    "svg",
    "img",
    "picture",
    "video",
    "audio",
    "iframe",
    "canvas",
    "header",
    "footer",
    "nav",
    "aside",
    "button",
    "input",
    "select",
    "textarea",
}

NOISE_ATTR_RE = re.compile(
    r"(nav|menu|mega|breadcrumb|footer|header|toolbar|language|search|"
    r"social|cookie|market-data|turnover|related-site|sidebar|"
    r"hkex-header|hkex-footer|skip|client-connect)",
    re.I,
)

NOISE_LINE_RE = re.compile(
    r"^(skip to main content|繁\s*简|about hkex|investor relations|"
    r"corporate governance|sustainability|media centre|careers|"
    r"related sites|latest market data|our products|our services|"
    r"securities$|listed derivatives|otc derivatives|clearing$|"
    r"market turnover|lme$|hkex group|bond connect|qme$|hkexnews|"
    r"client connect|copyright|privacy policy|terms of use)$",
    re.I,
)

MENU_PHRASE_RE = re.compile(
    r"(About HKEX.*Latest Market Data.*Our Products|"
    r"Our Products.*Our Services.*Trading|"
    r"Rules, Forms & Fees.*Clearing.*Settlement)",
    re.I,
)

TABLE_AGGREGATE_RE = re.compile(r"\| \([a-zivx]{1,4}\) \|", re.I)

BLOCK_TAGS = {
    "p",
    "div",
    "section",
    "article",
    "main",
    "li",
    "tr",
    "table",
    "thead",
    "tbody",
    "ul",
    "ol",
    "br",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
}


@dataclass
class ManifestInfo:
    title: str = ""
    url: str = ""
    category: str = ""


def load_manifest_info() -> dict[str, ManifestInfo]:
    info: dict[str, ManifestInfo] = {}
    for manifest in [
        RAW_ROOT / "_download_manifests" / "hkex_p1_p2_download_manifest.csv",
        RAW_ROOT / "_download_manifests" / "hkex_archive_download_manifest.csv",
    ]:
        if not manifest.exists():
            continue
        with manifest.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                local_path = row.get("suggested_local_path", "")
                if local_path:
                    info[Path(local_path).as_posix()] = ManifestInfo(
                        title=row.get("title", ""),
                        url=row.get("url", ""),
                        category=row.get("category", ""),
                    )
    return info


def html_files() -> list[Path]:
    files = []
    for path in RAW_ROOT.rglob("*.html"):
        rel_parts = path.relative_to(RAW_ROOT).parts
        if any(part in SKIP_DIR_NAMES or part.startswith(".") or part.startswith("_") for part in rel_parts[:-1]):
            continue
        files.append(path)
    return sorted(files)


def remove_noise(soup: BeautifulSoup) -> None:
    for tag_name in REMOVE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    for tag in soup.find_all(True):
        if tag.attrs is None:
            continue
        if tag.name and tag.name.lower() in {"html", "body", "main", "article"}:
            continue
        attrs = " ".join(
            str(value)
            for key, value in tag.attrs.items()
            if key in {"class", "id", "role", "aria-label"}
        )
        if attrs and NOISE_ATTR_RE.search(attrs):
            tag.decompose()


def choose_content_node(soup: BeautifulSoup) -> Tag:
    candidates: list[Tag] = []
    for selector in ["article", "main", "[role='main']", ".main-content", ".page-content", ".content"]:
        candidates.extend(soup.select(selector))

    body = soup.body or soup
    if not candidates:
        return body

    def score(tag: Tag) -> int:
        text = normalize_space(tag.get_text(" ", strip=True))
        if not text:
            return 0
        penalty = 0
        if MENU_PHRASE_RE.search(text):
            penalty += 5000
        return len(text) - penalty

    best = max(candidates, key=score)
    return best if score(best) > 0 else body


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def clean_line(line: str) -> str:
    line = normalize_space(line)
    line = line.replace("\u200b", "")
    line = re.sub(r"^[‹›]\s*", "", line)
    line = re.sub(r"\s*[‹›]\s*$", "", line)
    return line.strip()


def is_noise_line(line: str) -> bool:
    if not line:
        return True
    if line.lower() == "versions":
        return True
    if NOISE_LINE_RE.match(line):
        return True
    if MENU_PHRASE_RE.search(line):
        return True
    # HKEX rulebook pages sometimes render a table row as one giant aggregate
    # and then render each paragraph again. Keep the readable paragraphs.
    if len(line) > 500 and line.count(" | ") >= 4 and TABLE_AGGREGATE_RE.search(line):
        return True
    # Very long link/menu aggregates with little punctuation tend to be site chrome.
    words = line.split()
    if len(words) > 45 and sum(ch in line for ch in ".,;:()[]") < 3:
        return True
    return False


def link_text(tag: Tag) -> str:
    text = normalize_space(tag.get_text(" ", strip=True))
    href = tag.get("href")
    if href and text and href.startswith(("http://", "https://", "/-/media/")):
        return f"{text} ({href})"
    return text


def table_to_lines(table: Tag) -> list[str]:
    lines = []
    for row in table.find_all("tr"):
        cells = [normalize_space(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
        cells = [cell for cell in cells if cell]
        if cells:
            lines.append(" | ".join(cells))
    return lines


def node_to_lines(node: Tag) -> list[str]:
    lines: list[str] = []

    def append(text: str) -> None:
        line = clean_line(text)
        if not is_noise_line(line):
            lines.append(line)

    for element in node.descendants:
        if isinstance(element, NavigableString):
            parent = element.parent
            if not isinstance(parent, Tag):
                continue
            if parent.name in {"script", "style"}:
                continue
            if parent.name not in BLOCK_TAGS and parent.find_parent(["p", "li", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6"]):
                continue
        if not isinstance(element, Tag):
            continue

        name = element.name.lower()
        if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(name[1])
            append("#" * min(level, 4) + " " + element.get_text(" ", strip=True))
        elif name == "p":
            append(element.get_text(" ", strip=True))
        elif name == "li":
            append("- " + element.get_text(" ", strip=True))
        elif name == "table":
            for line in table_to_lines(element):
                append(line)
        elif name == "a" and not element.find_parent(["p", "li", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6"]):
            append(link_text(element))

    return dedupe_lines(lines)


def dedupe_lines(lines: Iterable[str]) -> list[str]:
    cleaned = []
    previous = None
    seen_run: Counter[str] = Counter()
    seen_long: set[str] = set()
    for line in lines:
        line = clean_line(line)
        if not line or is_noise_line(line):
            continue
        if line == previous:
            continue
        normalized_line = line.lower()
        if len(line) >= 120:
            if normalized_line in seen_long:
                continue
            seen_long.add(normalized_line)
        # Drop boilerplate-like lines after a few repeats, but keep table values.
        seen_run[line] += 1
        if seen_run[line] > 3 and len(line) < 120:
            continue
        cleaned.append(line)
        previous = line
    return cleaned


def output_path_for(source: Path) -> Path:
    rel = source.relative_to(RAW_ROOT)
    return OUTPUT_ROOT / rel.with_suffix(".md")


def front_matter(path: Path, info: ManifestInfo, title: str) -> str:
    source = path.relative_to(PROJECT_ROOT).as_posix()
    source_url = info.url or ""
    category = info.category or path.relative_to(RAW_ROOT).parts[0]
    return "\n".join(
        [
            "---",
            f"title: {title}",
            f"source_path: {source}",
            f"source_url: {source_url}",
            f"category: {category}",
            "converted_from: html",
            f"converted_at: {datetime.now(timezone.utc).isoformat()}",
            "---",
            "",
        ]
    )


def convert_file(path: Path, manifest_info: dict[str, ManifestInfo]) -> dict[str, str]:
    html = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")
    title = normalize_space(soup.title.get_text(" ", strip=True) if soup.title else path.stem)
    key = path.relative_to(PROJECT_ROOT).as_posix()
    info = manifest_info.get(key, ManifestInfo())
    if info.title:
        title = info.title

    remove_noise(soup)
    content_node = choose_content_node(soup)
    lines = node_to_lines(content_node)

    out_path = output_path_for(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n\n".join(lines).strip()
    content = front_matter(path, info, title) + f"# {title}\n\n" + body + "\n"
    out_path.write_text(content, encoding="utf-8")

    text = "\n".join(lines)
    suspicious = any(
        phrase.lower() in text.lower()
        for phrase in [
            "Latest Market Data Our Products",
            "About HKEX Investor Relations",
            "Rules, Forms & Fees Clearing",
            "Market Turnover",
        ]
    )
    return {
        "source_path": path.relative_to(PROJECT_ROOT).as_posix(),
        "output_path": out_path.relative_to(PROJECT_ROOT).as_posix(),
        "title": title,
        "line_count": str(len(lines)),
        "char_count": str(len(text)),
        "suspicious_navigation": str(suspicious),
        "status": "ok" if lines else "empty",
    }


def write_log(rows: list[dict[str, str]]) -> None:
    fieldnames = ["source_path", "output_path", "title", "line_count", "char_count", "suspicious_navigation", "status"]
    with LOG_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_audit(rows: list[dict[str, str]]) -> None:
    by_status = Counter(row["status"] for row in rows)
    suspicious = [row for row in rows if row["suspicious_navigation"] == "True"]
    low_text = [row for row in rows if int(row["char_count"]) < 200]
    total_chars = sum(int(row["char_count"]) for row in rows)
    lines = [
        "# HKEX HTML to Markdown Conversion Audit",
        "",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Scope",
        "",
        f"- Source root: `{RAW_ROOT.relative_to(PROJECT_ROOT).as_posix()}`",
        f"- Output root: `{OUTPUT_ROOT.relative_to(PROJECT_ROOT).as_posix()}`",
        "- Skipped internal directories: `_download_manifests`, `html_converted`, dot/underscore directories.",
        "",
        "## Result Summary",
        "",
        f"- HTML files converted: **{len(rows)}**",
        f"- Successful non-empty conversions: **{by_status['ok']}**",
        f"- Empty conversions: **{by_status['empty']}**",
        f"- Total extracted characters: **{total_chars:,}**",
        f"- Files flagged for possible navigation noise: **{len(suspicious)}**",
        f"- Files with fewer than 200 extracted characters: **{len(low_text)}**",
        "",
        "## Noise Controls",
        "",
        "- Uses `article` or `main` content where available, not full page body.",
        "- Removes script/style/nav/header/footer/aside/media and form-control tags.",
        "- Removes common HKEX menu, breadcrumb, language, search, market-data, footer, and social containers by class/id/role.",
        "- Filters common navigation-only lines and repeated boilerplate.",
        "",
        "## Files Flagged for Possible Navigation Noise",
        "",
    ]
    if suspicious:
        lines.extend(["| Output | Characters |", "|---|---:|"])
        for row in suspicious[:50]:
            lines.append(f"| `{row['output_path']}` | {row['char_count']} |")
    else:
        lines.append("No converted files matched the navigation-noise heuristics.")

    lines.extend(["", "## Low-Text Conversions", ""])
    if low_text:
        lines.extend(["| Output | Characters |", "|---|---:|"])
        for row in low_text:
            lines.append(f"| `{row['output_path']}` | {row['char_count']} |")
    else:
        lines.append("No converted files had fewer than 200 extracted characters.")

    AUDIT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    info = load_manifest_info()
    rows = []
    for path in html_files():
        row = convert_file(path, info)
        rows.append(row)
        print(f"{row['status']}: {row['source_path']} -> {row['output_path']} ({row['char_count']} chars)")
    write_log(rows)
    write_audit(rows)
    failures = sum(1 for row in rows if row["status"] != "ok")
    print(f"Wrote {LOG_PATH}")
    print(f"Wrote {AUDIT_PATH}")
    print(f"Non-ok conversions: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
