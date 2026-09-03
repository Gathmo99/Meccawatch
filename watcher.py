#!/usr/bin/env python3
"""MECCHA ROGUE / Liberation Sequence website watcher."""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urljoin, urlparse
from zoneinfo import ZoneInfo

import requests


BASE_URL = os.getenv(
    "MECCHA_BASE_URL",
    "https://2390h938fh92f8h2382h92gf928g98hyf92h9.netlify.app/",
).rstrip("/") + "/"
ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / "state.json"
SNAPSHOT_FILE = ROOT / "snapshot.html"
SNAPSHOTS_DIR = ROOT / "snapshots"
HISTORY_DIR = ROOT / "history"
ARTIFACTS_DIR = ROOT / "artifacts"
TIMEOUT = (15, 60)
MAX_PAGES = int(os.getenv("MECCHA_MAX_PAGES", "25"))
MAX_MEDIA_BYTES = int(os.getenv("MECCHA_MAX_MEDIA_BYTES", str(100 * 1024 * 1024)))
USER_AGENT = "ARGUS-MECCHA-Watcher/1.0 (+GitHub Actions)"
REQUIRED_PATHS = ("/", "/covenant.html", "/register.html", "/submit-art.html")

MEDIA_EXTENSIONS = {
    ".wav", ".mp4", ".webm", ".mp3", ".jpg", ".jpeg", ".png",
    ".gif", ".txt", ".json", ".bin",
}
KEYWORD_RE = re.compile(
    r"CARD(?:\s+\d{1,2}/20)?|SIGNAL(?:\s+17(?:/16)?)?|A\.R\.G\.U\.S\."
    r"(?:\s+SIGNAL\s+RELAY)?|PRIORITY|SEVENTEENTH|/media/",
    re.IGNORECASE,
)
CARD_RE = re.compile(r"\bCARD\s*0?(\d{1,2})\s*/\s*20\b", re.IGNORECASE)
SIGNAL_RE = re.compile(r"\bSIGNAL[\s_-]*0?(\d{1,2})(?:\s*/\s*16)?\b", re.IGNORECASE)
PRIORITY_RE = re.compile(r"\bPRIORITY(?:\s+(\d)\s*/\s*3)?\b", re.IGNORECASE)
MEDIA_RE = re.compile(
    r"(?P<url>(?:https?://[^\s\"'<>\]\)]+)?/media/[^\s\"'<>\]\)]+)",
    re.IGNORECASE,
)
VOLATILE_HEADERS = {
    "age", "date", "server-timing", "x-nf-request-id", "x-request-id",
    "cf-ray", "nel", "report-to", "cache-status", "content-length",
    "transfer-encoding",
}


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.urls: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        for key in ("href", "src", "poster"):
            if attr_map.get(key):
                self.urls.add(attr_map[key] or "")


@dataclass
class PageResult:
    url: str
    body: bytes
    text: str
    headers: dict[str, str]
    sha256: str


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def german_time(iso_utc: str) -> str:
    dt = datetime.fromisoformat(iso_utc).astimezone(ZoneInfo("Europe/Berlin"))
    return dt.strftime("%d.%m.%Y %H:%M Uhr")


def timestamp_slug(now: str) -> str:
    return now.replace("-", "").replace(":", "").replace("+00:00", "Z")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"version": 1, "pages": {}, "media": {}, "cards": {}, "signals": {}, "priorities": {}}
    with STATE_FILE.open(encoding="utf-8") as handle:
        state = json.load(handle)
    for key in ("pages", "media", "cards", "signals", "priorities"):
        state.setdefault(key, {})
    return state


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def write_json(path: Path, value: object) -> None:
    write_text(path, json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


def stable_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        key.lower(): value
        for key, value in sorted(headers.items(), key=lambda item: item[0].lower())
        if key.lower() not in VOLATILE_HEADERS
    }


def fetch_page(session: requests.Session, url: str) -> PageResult:
    response = session.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    body = response.content
    encoding = response.encoding or "utf-8"
    return PageResult(
        url=response.url,
        body=body,
        text=body.decode(encoding, errors="replace"),
        headers={str(k): str(v) for k, v in response.headers.items()},
        sha256=sha256(body),
    )


def canonical_internal_url(candidate: str, source_url: str) -> str | None:
    absolute = urljoin(source_url, candidate).split("#", 1)[0]
    parsed = urlparse(absolute)
    base = urlparse(BASE_URL)
    if parsed.scheme not in {"http", "https"} or parsed.netloc != base.netloc:
        return None
    path = parsed.path or "/"
    suffix = Path(unquote(path)).suffix.lower()
    if path.startswith("/media/") or suffix in MEDIA_EXTENSIONS:
        return None
    if suffix and suffix not in {".html", ".htm"}:
        return None
    return absolute


def discover_links(text: str, source_url: str) -> tuple[set[str], set[str]]:
    parser = LinkParser()
    try:
        parser.feed(text)
    except Exception:
        pass
    pages: set[str] = set()
    media: set[str] = set()
    for candidate in parser.urls:
        internal = canonical_internal_url(candidate, source_url)
        if internal:
            pages.add(internal)
        absolute = urljoin(source_url, candidate).split("#", 1)[0]
        parsed = urlparse(absolute)
        if parsed.netloc == urlparse(BASE_URL).netloc and parsed.path.startswith("/media/"):
            if Path(unquote(parsed.path)).suffix.lower() in MEDIA_EXTENSIONS:
                media.add(absolute)
    for match in MEDIA_RE.finditer(text):
        candidate = match.group("url").rstrip(".,;:")
        absolute = urljoin(source_url, candidate)
        parsed = urlparse(absolute)
        if parsed.netloc == urlparse(BASE_URL).netloc:
            if Path(unquote(parsed.path)).suffix.lower() in MEDIA_EXTENSIONS:
                media.add(absolute)
    return pages, media


def relevant_lines(text: str) -> list[str]:
    result: list[str] = []
    for raw_line in text.splitlines():
        line = " ".join(raw_line.strip().split())
        if line and KEYWORD_RE.search(line):
            result.append(line[:1000])
    return sorted(set(result))


def alertable_diff_lines(diff: Iterable[str], had_previous_snapshot: bool) -> list[str]:
    """Ignore the artificial full-page diff created by a page's first baseline."""
    if not had_previous_snapshot:
        return []
    return [
        line[:500]
        for line in diff
        if KEYWORD_RE.search(line)
    ]


def extract_markers(text: str, headers: dict[str, str]) -> tuple[set[int], set[int], set[str]]:
    combined = text + "\n" + "\n".join(f"{k}: {v}" for k, v in headers.items())
    cards = {int(value) for value in CARD_RE.findall(combined) if 1 <= int(value) <= 20}
    signals = {int(value) for value in SIGNAL_RE.findall(combined) if 1 <= int(value) <= 99}
    priorities = {value or "unspecified" for value in PRIORITY_RE.findall(combined)}
    return cards, signals, priorities


def card_for_media(text: str, media_url: str) -> int | None:
    path = urlparse(media_url).path
    for occurrence in re.finditer(re.escape(path), text, flags=re.IGNORECASE):
        nearby = text[max(0, occurrence.start() - 300): occurrence.end() + 300]
        matches = CARD_RE.findall(nearby)
        if matches:
            card = int(matches[-1])
            if 1 <= card <= 20:
                return card
    return None


def safe_page_name(url: str) -> str:
    parsed = urlparse(url)
    path = unquote(parsed.path).strip("/") or "index"
    path = re.sub(r"[^A-Za-z0-9._-]+", "_", path)
    query_hash = hashlib.sha256(parsed.query.encode()).hexdigest()[:8] if parsed.query else ""
    return f"{path}{'-' + query_hash if query_hash else ''}.html"


def archive_page(old_text: str | None, page: PageResult, old_headers: dict, now: str) -> list[str]:
    folder = HISTORY_DIR / timestamp_slug(now) / safe_page_name(page.url).removesuffix(".html")
    if old_text is not None:
        write_text(folder / "before.html", old_text)
    write_text(folder / "after.html", page.text)
    write_json(folder / "headers-before.json", old_headers)
    write_json(folder / "headers-after.json", page.headers)
    diff = list(difflib.unified_diff(
        (old_text or "").splitlines(), page.text.splitlines(),
        fromfile="before.html", tofile="after.html", lineterm="",
    ))
    write_text(folder / "diff.patch", "\n".join(diff) + ("\n" if diff else ""))
    return [line for line in diff if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))]


def store_media(session: requests.Session, url: str, source_url: str, source_text: str, now: str) -> dict:
    response = session.get(url, timeout=TIMEOUT, stream=True)
    response.raise_for_status()
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=128 * 1024):
        if not chunk:
            continue
        total += len(chunk)
        if total > MAX_MEDIA_BYTES:
            raise ValueError(f"media exceeds {MAX_MEDIA_BYTES} bytes: {url}")
        chunks.append(chunk)
    body = b"".join(chunks)
    card = card_for_media(source_text, url)
    folder = ARTIFACTS_DIR / (f"card{card:02d}" if card else "unknown")
    filename = Path(unquote(urlparse(url).path)).name or hashlib.sha256(url.encode()).hexdigest()[:16]
    destination = folder / filename
    if destination.exists() and sha256(destination.read_bytes()) != sha256(body):
        destination = folder / f"{destination.stem}-{sha256(url.encode())[:8]}{destination.suffix}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(body)
    metadata = {
        "card": card,
        "url": url,
        "found_at": now,
        "sha256": sha256(body),
        "size": len(body),
        "content_type": response.headers.get("content-type", ""),
        "source_page": source_url,
        "path": destination.relative_to(ROOT).as_posix(),
    }
    write_json(destination.with_name(destination.name + ".metadata.json"), metadata)
    return metadata


def send_discord(lines: Iterable[str]) -> None:
    webhook = os.getenv("DISCORD_WEBHOOK", "").strip()
    if not webhook:
        return
    content = "\n".join(lines)
    if len(content) > 1950:
        content = content[:1930] + "\n… (gekürzt)"
    response = requests.post(webhook, json={"content": content}, timeout=TIMEOUT)
    response.raise_for_status()


def main() -> int:
    now = utc_now()
    state = load_state()
    initial_run = not bool(state["pages"])
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Cache-Control": "no-cache"})

    seed_urls = {urljoin(BASE_URL, path) for path in REQUIRED_PATHS}
    seed_urls.update(state["pages"].keys())
    queue = sorted(seed_urls)
    visited: set[str] = set()
    page_results: dict[str, PageResult] = {}
    media_sources: dict[str, tuple[str, str]] = {}
    new_cards: set[int] = set()
    new_signals: set[int] = set()
    new_priorities: set[str] = set()
    relevant_diff_lines: list[str] = []
    any_change = False

    while queue and len(visited) < MAX_PAGES:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            page = fetch_page(session, url)
        except requests.RequestException as exc:
            print(f"ERROR fetching {url}: {exc}", file=sys.stderr)
            if url in seed_urls:
                raise
            continue
        page_results[url] = page
        pages, media = discover_links(page.text, page.url)
        for discovered in sorted(pages):
            if discovered not in visited and discovered not in queue and len(visited) + len(queue) < MAX_PAGES:
                queue.append(discovered)
        for media_url in media:
            media_sources.setdefault(media_url, (page.url, page.text))

        old = state["pages"].get(url, {})
        headers = stable_headers(page.headers)
        changed = old.get("sha256") != page.sha256 or old.get("headers") != headers
        if changed:
            any_change = True
            old_snapshot = ROOT / old.get("snapshot", "") if old.get("snapshot") else None
            old_text = old_snapshot.read_text(encoding="utf-8") if old_snapshot and old_snapshot.exists() else None
            diff = archive_page(old_text, page, old.get("all_headers", {}), now)
            relevant_diff_lines.extend(alertable_diff_lines(diff, old_text is not None))
            snapshot_path = SNAPSHOT_FILE if url == urljoin(BASE_URL, "/") else SNAPSHOTS_DIR / safe_page_name(url)
            write_text(snapshot_path, page.text)
            state["pages"][url] = {
                "sha256": page.sha256,
                "headers": headers,
                "all_headers": page.headers,
                "snapshot": snapshot_path.relative_to(ROOT).as_posix(),
                "changed_at": now,
                "relevant_lines": relevant_lines(page.text + "\n" + json.dumps(page.headers)),
            }

        cards, signals, priorities = extract_markers(page.text, page.headers)
        for card in cards:
            key = f"{card:02d}"
            if key not in state["cards"]:
                state["cards"][key] = {"first_seen_at": now, "source_page": page.url}
                new_cards.add(card)
        for signal in signals:
            key = f"{signal:02d}"
            if key not in state["signals"]:
                state["signals"][key] = {"first_seen_at": now, "source_page": page.url}
                new_signals.add(signal)
        for priority in priorities:
            if priority not in state["priorities"]:
                state["priorities"][priority] = {"first_seen_at": now, "source_page": page.url}
                new_priorities.add(priority)

    new_media: list[dict] = []
    for media_url, (source_url, source_text) in sorted(media_sources.items()):
        if media_url in state["media"]:
            continue
        try:
            metadata = store_media(session, media_url, source_url, source_text, now)
        except (requests.RequestException, ValueError) as exc:
            print(f"ERROR downloading {media_url}: {exc}", file=sys.stderr)
            continue
        state["media"][media_url] = metadata
        new_media.append(metadata)
        any_change = True

    if any_change or new_cards or new_signals or new_priorities:
        state["last_change_at"] = now
        state["base_url"] = BASE_URL
        write_json(STATE_FILE, state)

    if not initial_run and (new_cards or new_signals or new_priorities or new_media or relevant_diff_lines):
        alert = ["🚨 **MECCHA ROGUE CHANGE DETECTED**"]
        alert += [f"\n🃏 **NEW CARD**\nCARD {card:02d}/20" for card in sorted(new_cards)]
        alert += [f"\n📡 **NEW SIGNAL**\nSIGNAL {signal:02d}" for signal in sorted(new_signals)]
        alert += [f"\n⚠️ **NEW PRIORITY**\nPRIORITY {priority}" for priority in sorted(new_priorities)]
        if new_media:
            alert.append("\n📦 **NEW MEDIA**")
            alert.extend(f"- {urlparse(item['url']).path}" for item in new_media[:12])
        if relevant_diff_lines:
            alert.append("\n🔎 **RELEVANT SOURCE/HEADER CHANGE**")
            alert.extend(f"```diff\n{line}\n```" for line in relevant_diff_lines[:8])
        send_discord(alert)

    last_heartbeat = state.get("last_heartbeat_at")
    heartbeat_due = last_heartbeat is None or (
        datetime.now(timezone.utc) - datetime.fromisoformat(last_heartbeat)
    ).total_seconds() >= 25 * 60
    if not initial_run and heartbeat_due:
        send_discord([
            "✅ **A.R.G.U.S. STATUS**",
            f"\nWatcher aktiv – {german_time(now)}",
            f"Seiten geprüft: {len(page_results)}",
        ])
        state["last_heartbeat_at"] = now
        write_json(STATE_FILE, state)

    if new_cards:
        commit_message = f"CARD {min(new_cards):02d}/20 detected"
    elif any_change:
        commit_message = "A.R.G.U.S. website change detected"
    else:
        commit_message = ""
    output = os.getenv("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"commit_message={commit_message}\n")

    print(json.dumps({
        "pages_checked": len(page_results),
        "changed": any_change,
        "new_cards": sorted(new_cards),
        "new_signals": sorted(new_signals),
        "new_media": len(new_media),
        "initial_run": initial_run,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
