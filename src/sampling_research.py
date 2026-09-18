"""Research sampling recommendations in model cards and official sources.

The registry stores benchmark sampling per category, while model cards usually
publish one generation profile.  A verified web profile is therefore copied to
all benchmark categories.  The caller must keep the provenance fields next to
the generated values; this module never writes files or LM Studio configs.
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

SAMPLING_CATEGORIES = ("coding", "knowledge", "agentic", "math", "thinking")
SUPPORTED_FIELDS = ("temperature", "top_p", "top_k", "min_p")

_FIELD_PATTERNS = {
    "temperature": re.compile(r"(?i)(?<![a-z])(?:temperature|temp)(?![a-z])\s*[=:]\s*(-?(?:\d+(?:\.\d*)?|\.\d+))"),
    "top_p": re.compile(r"(?i)(?<![a-z])top[_ -]?p(?![a-z])\s*[=:]\s*(-?(?:\d+(?:\.\d*)?|\.\d+))"),
    "top_k": re.compile(r"(?i)(?<![a-z])top[_ -]?k(?![a-z])\s*[=:]\s*(\d+)"),
    "min_p": re.compile(r"(?i)(?<![a-z])min[_ -]?p(?![a-z])\s*[=:]\s*(-?(?:\d+(?:\.\d*)?|\.\d+))"),
}

_VALUE_LIMITS: dict[str, tuple[float, float]] = {
    "temperature": (0.0, 2.0),
    "top_p": (0.0, 1.0),
    "top_k": (0.0, 1000.0),
    "min_p": (0.0, 1.0),
}

# These are official documentation/organization roots, not arbitrary links.
# HF model cards can add more official links, but only these known manufacturer
# domains are followed automatically.  Extending this table is intentionally
# explicit so a model card cannot make registry_tool fetch arbitrary domains.
_MANUFACTURER_SOURCES: dict[str, tuple[str, ...]] = {
    "qwen": (
        "https://qwenlm.github.io/",
        "https://qwen.readthedocs.io/en/latest/",
    ),
    "mistralai": ("https://docs.mistral.ai/", "https://mistral.ai/"),
    "google": ("https://ai.google.dev/gemma/",),
    "ibm": ("https://www.ibm.com/granite/",),
    "openai": ("https://openai.com/", "https://cookbook.openai.com/"),
    "microsoft": ("https://learn.microsoft.com/",),
    "zai-org": ("https://z.ai/",),
    "essentialai": ("https://www.essential.ai/",),
    "jetbrains": ("https://www.jetbrains.com/",),
}

_HF_HOSTS = {"huggingface.co", "www.huggingface.co"}
_OFFICIAL_LINK_LABELS = re.compile(r"(?i)(official|original|model card|paper|documentation|docs)")
_MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\((https?://[^)\s]+)\)")
_HTML_LINK = re.compile(r"(?i)href=[\"'](https?://[^\"']+)")


@dataclass(frozen=True)
class SourceDocument:
    """Fetched text and source priority used for one sampling decision."""

    url: str
    text: str
    priority: int


FetchText = Callable[[str, float], str | None]


def validate_sampling_block(block: Any) -> list[str]:
    """Return schema/range issues for a Registry sampling block."""
    if not isinstance(block, Mapping):
        return ["sampling muss ein Mapping sein"]
    issues: list[str] = []
    for category, cell in block.items():
        if category not in SAMPLING_CATEGORIES:
            continue
        if not isinstance(cell, Mapping):
            issues.append(f"{category}: Sampling-Zelle muss ein Mapping sein")
            continue
        for field, value in cell.items():
            if field not in SUPPORTED_FIELDS:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                issues.append(f"{category}.{field}: numerischer Wert erwartet")
                continue
            lower, upper = _VALUE_LIMITS[field]
            if not lower <= float(value) <= upper:
                issues.append(f"{category}.{field}: {value} ausserhalb [{lower}, {upper}]")
            if field == "top_k" and float(value) != int(value):
                issues.append(f"{category}.top_k: ganzzahliger Wert erwartet")
    return issues


def _fetch_text(url: str, timeout_s: float) -> str | None:
    """Fetch a public HTTPS text document without adding a runtime dependency."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        return None
    request = Request(
        url,
        headers={
            "Accept": "text/plain,text/markdown,text/html,application/json;q=0.9,*/*;q=0.1",
            "User-Agent": "Local-LLM-Benchmark-Tool/registry-sampling-research",
        },
    )
    try:
        with urlopen(request, timeout=timeout_s) as response:
            content_type = response.headers.get_content_type()
            if content_type not in {"text/plain", "text/markdown", "text/html", "application/json"}:
                return None
            return cast("str", response.read(2_000_000).decode("utf-8", errors="replace"))
    except (HTTPError, URLError, TimeoutError, UnicodeError, OSError):
        return None


def _base_model_name(model: Mapping[str, Any]) -> str:
    key = str(model.get("modelKey") or model.get("key") or model.get("displayName") or "")
    return key.split("@", 1)[0].strip()


def _hf_repo_urls(model: Mapping[str, Any]) -> list[str]:
    """Return likely HF model-card URLs for the installed model."""
    urls: list[str] = []
    explicit = str(model.get("hf_url") or "").strip()
    if explicit:
        urls.append(explicit.rstrip("/"))

    key = _base_model_name(model)
    publisher = str(model.get("publisher") or "").strip()
    if "/" in key:
        urls.append(f"https://huggingface.co/{key}")
    elif publisher and key:
        urls.append(f"https://huggingface.co/{publisher}/{key}")

    path = str(model.get("path") or model.get("indexedModelIdentifier") or "").strip()
    parts = [part for part in path.split("/") if part]
    if len(parts) >= 2:
        urls.append(f"https://huggingface.co/{parts[0]}/{parts[1]}")

    return _unique_urls(urls)


def _manufacturer_urls(model: Mapping[str, Any]) -> list[str]:
    publisher = str(model.get("publisher") or "").strip().lower()
    model_name = _base_model_name(model).lower()
    urls: list[str] = []
    for name, candidates in _MANUFACTURER_SOURCES.items():
        if publisher == name or publisher.startswith(f"{name}-") or name in model_name:
            urls.extend(candidates)
    return _unique_urls(urls)


def _unique_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        normalized = url.rstrip("/")
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _is_known_official_url(url: str, publisher: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower().split(":", 1)[0]
    if host in _HF_HOSTS:
        return True
    for root in _MANUFACTURER_SOURCES.get(publisher.lower(), ()):
        if urlparse(root).netloc.lower() == host:
            return True
    return False


def _linked_official_sources(text: str, publisher: str, base_url: str) -> list[str]:
    """Extract only labelled/known official links from an HF model card."""
    links: list[str] = []
    for match in _MARKDOWN_LINK.finditer(text):
        start = max(0, match.start() - 100)
        label_context = text[start : match.end()]
        url = html.unescape(match.group(1)).rstrip(".,)")
        if _is_known_official_url(url, publisher) or _OFFICIAL_LINK_LABELS.search(label_context):
            links.append(urljoin(base_url, url))
    for match in _HTML_LINK.finditer(text):
        url = html.unescape(match.group(1)).rstrip(".,)")
        if _is_known_official_url(url, publisher):
            links.append(urljoin(base_url, url))
    return _unique_urls(links)


def _strip_markup(text: str) -> str:
    text = re.sub(r"```.*?```", lambda m: m.group(0), text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(text)


def _extract_candidates(
    document: SourceDocument,
    profile: str = "default",
) -> dict[str, list[tuple[float, str, str]]]:
    candidates: dict[str, list[tuple[float, str, str]]] = {field: [] for field in SUPPORTED_FIELDS}
    text = _strip_markup(document.text)
    for line in text.splitlines():
        lower_line = line.lower()
        is_thinking = "thinking mode" in lower_line or "thinking=" in lower_line
        is_non_thinking = "non-thinking mode" in lower_line or "enable_thinking=false" in lower_line
        if profile == "thinking" and (not is_thinking or is_non_thinking):
            continue
        if profile == "normal" and is_thinking and not is_non_thinking:
            continue
        for field, pattern in _FIELD_PATTERNS.items():
            for match in pattern.finditer(line):
                try:
                    value = float(match.group(1))
                except ValueError:
                    continue
                lower, upper = _VALUE_LIMITS[field]
                if not lower <= value <= upper:
                    continue
                if field == "top_k" and value != int(value):
                    continue
                candidates[field].append((value, document.url, line.strip()[:240]))
    return candidates


def research_sampling(
    model: Mapping[str, Any],
    timeout_s: float = 8.0,
    fetcher: FetchText | None = None,
) -> dict[str, Any] | None:
    """Research and validate a model's sampling profile.

    Returns a registry-ready dictionary or ``None`` if no unambiguous source
    contains both temperature and top_p.  ``fetcher`` is injectable for tests.
    The function never writes files and never changes LM Studio state.
    """
    fetch = fetcher or _fetch_text
    publisher = str(model.get("publisher") or "").strip().lower()
    hf_urls = _hf_repo_urls(model)
    documents: list[SourceDocument] = []
    visited: set[str] = set()

    for url in hf_urls:
        for read_url in (f"{url}/raw/main/README.md", f"{url}/raw/master/README.md"):
            if read_url in visited:
                continue
            visited.add(read_url)
            text = fetch(read_url, timeout_s)
            if text:
                documents.append(SourceDocument(read_url, text, 4 if publisher in url.lower() else 1))
                linked = _linked_official_sources(text, publisher, url)
                for linked_url in linked[:6]:
                    if linked_url in visited:
                        continue
                    visited.add(linked_url)
                    linked_text = fetch(linked_url, timeout_s)
                    if linked_text:
                        documents.append(SourceDocument(linked_url, linked_text, 3))

    for url in _manufacturer_urls(model)[:4]:
        if url in visited:
            continue
        visited.add(url)
        text = fetch(url, timeout_s)
        if text:
            documents.append(SourceDocument(url, text, 2))

    if not documents:
        return None

    # Higher-priority official documents win over quantizer cards.  For a
    # given field, values at the same priority must agree; otherwise the field
    # is rejected instead of guessing.
    def resolve_profile(profile: str) -> tuple[dict[str, float | int], dict[str, dict[str, str]], list[str]]:
        profile_candidates: dict[str, list[tuple[int, float, str, str]]] = {field: [] for field in SUPPORTED_FIELDS}
        for document in documents:
            for field, profile_entries in _extract_candidates(document, profile).items():
                profile_candidates[field].extend(
                    (document.priority, value, url, excerpt) for value, url, excerpt in profile_entries
                )
        values: dict[str, float | int] = {}
        evidence: dict[str, dict[str, str]] = {}
        conflicts: list[str] = []
        for field, entries in profile_candidates.items():
            if not entries:
                continue
            priority = max(entry[0] for entry in entries)
            top_entries = [entry for entry in entries if entry[0] == priority]
            distinct = {entry[1] for entry in top_entries}
            if len(distinct) != 1:
                conflicts.append(field)
                continue
            _, value, url, excerpt = top_entries[0]
            values[field] = int(value) if field == "top_k" else value
            evidence[field] = {"url": url, "excerpt": excerpt}
        return values, evidence, conflicts

    values, evidence, conflicts = resolve_profile("normal")
    if not values:
        values, evidence, conflicts = resolve_profile("default")
    if "temperature" not in values or "top_p" not in values or conflicts:
        return None

    sampling = {category: dict(values) for category in SAMPLING_CATEGORIES if category != "thinking"}
    thinking_values, thinking_evidence, thinking_conflicts = resolve_profile("thinking")
    if "temperature" in thinking_values and "top_p" in thinking_values and not thinking_conflicts:
        thinking_values = {"enabled": True, **thinking_values}
        sampling["thinking"] = thinking_values
        evidence.update(thinking_evidence)
    source_urls = sorted({item["url"] for item in evidence.values()})
    return {
        "sampling": sampling,
        "sampling_source": "web-research",
        "sampling_sources": source_urls,
    }
