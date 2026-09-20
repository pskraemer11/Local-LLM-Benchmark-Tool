"""Research sampling recommendations in model cards and official sources.

The registry stores benchmark sampling per category, while model cards usually
publish one or more generation profiles. This module performs a bounded,
read-only onboarding search. It follows Hugging Face base-model metadata and
known official documentation links, but never writes files or LM Studio state.
"""

from __future__ import annotations

import html
import json
import re
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urldefrag, urljoin, urlparse
from urllib.request import Request, urlopen

SAMPLING_CATEGORIES = ("coding", "knowledge", "agentic", "math", "thinking")
SUPPORTED_FIELDS = ("temperature", "top_p", "top_k", "min_p", "presence_penalty", "repetition_penalty")
RESEARCH_STATUSES = ("confirmed", "unresolved", "conflict", "not_found")

_CATEGORY_MARKERS: dict[str, re.Pattern[str]] = {
    "coding": re.compile(r"(?i)\b(?:coding|code|programming|webdev|software engineering)\b"),
    "knowledge": re.compile(r"(?i)\b(?:knowledge|factual|fact[- ]?based|question answering|qa)\b"),
    "agentic": re.compile(
        r"(?i)\b(?:agentic|agent|tool[- ]use|function calling|instruction following|reasoning tasks)\b"
    ),
    "math": re.compile(r"(?i)\b(?:math|mathematics|gsm8k|aime|hmmt|math problems?)\b"),
}
_PROFILE_MODE_MARKER = re.compile(
    r"(?i)\b(?:thinking mode|reasoning mode|enable_thinking\s*[:=]\s*(?:true|false)|"
    r"instruct(?:\s+or)?\s+non[- ]thinking|non[- ]thinking|general tasks|default(?: tasks)?|normal mode)\b"
)
_NORMAL_PROFILE_MARKER = re.compile(
    r"(?i)\b(?:instruct(?:\s+or)?\s+non[- ]thinking|non[- ]thinking|general tasks|default(?: tasks)?|normal mode)\b"
)

_NUMBER = r"-?(?:\d+(?:\.\d*)?|\.\d+)"
_FIELD_PATTERNS = {
    "temperature": re.compile(
        rf"(?i)(?<![a-z])(?:`|\"|')?(?:temperature|temp)(?:`|\"|')?"
        rf"\s*(?:=|:|\||,|\bof\b|\s+)\s*({_NUMBER})"
    ),
    "top_p": re.compile(
        rf"(?i)(?<![a-z])(?:`|\"|')?top[_ -]?p(?:`|\"|')?"
        rf"\s*(?:=|:|\||,|\bof\b|\s+)\s*({_NUMBER})"
    ),
    "top_k": re.compile(
        r"(?i)(?<![a-z])(?:`|\"|')?top[_ -]?k(?:`|\"|')?"
        r"\s*(?:=|:|\||,|\bof\b|\s+)\s*(\d+)"
    ),
    "min_p": re.compile(
        rf"(?i)(?<![a-z])(?:`|\"|')?min[_ -]?p(?:`|\"|')?"
        rf"\s*(?:=|:|\||,|\bof\b|\s+)\s*({_NUMBER})"
    ),
    "presence_penalty": re.compile(
        rf"(?i)(?<![a-z])(?:`|\"|')?presence[_ -]?penalty(?:`|\"|')?\s*(?:=|:|\||,|\bof\b|\s+)\s*({_NUMBER})"
    ),
    "repetition_penalty": re.compile(
        rf"(?i)(?<![a-z])(?:`|\"|')?repetition[_ -]?penalty(?:`|\"|')?\s*(?:=|:|\||,|\bof\b|\s+)\s*({_NUMBER})"
    ),
}

_VALUE_LIMITS: dict[str, tuple[float, float]] = {
    "temperature": (0.0, 2.0),
    "top_p": (0.0, 1.0),
    "top_k": (0.0, 1000.0),
    "min_p": (0.0, 1.0),
    "presence_penalty": (-2.0, 2.0),
    "repetition_penalty": (0.0, 3.0),
}

# These are official documentation/organization roots, not arbitrary links.
# HF cards may add subpages on these hosts. Crawling remains bounded and
# same-domain, so a model card cannot turn registry_tool into a general web
# crawler.
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
    "moonshotai": ("https://github.com/moonshotai/",),
}

_HF_HOSTS = {"huggingface.co", "www.huggingface.co"}
_OFFICIAL_LINK_LABELS = re.compile(r"(?i)(official|original|model card|paper|documentation|docs)")
_MARKDOWN_LINK = re.compile(r"\[([^\]]{0,240})\]\(([^)\s]+)")
_HTML_LINK = re.compile(r"(?i)href=[\"']([^\"']+)")
_CRAWL_TERMS = (
    "sampling",
    "generation",
    "inference",
    "parameter",
    "model",
    "usage",
    "chat",
    "qwen",
    "ministral",
    "mistral",
    "gemma",
    "reasoning",
)
_MAX_OFFICIAL_PAGES = 12
_MAX_OFFICIAL_DEPTH = 2
_MAX_LINKS_PER_PAGE = 12
_MAX_HF_SEARCH_RESULTS = 20
_MAX_TERMINAL_SOURCE_URLS = 8


@dataclass(frozen=True)
class SourceDocument:
    """Fetched text and source priority used for one sampling decision."""

    url: str
    text: str
    priority: int


@dataclass(frozen=True)
class SamplingCandidate:
    """One value together with its local profile block and evidence."""

    value: float
    url: str
    excerpt: str
    group: int
    cue: int


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
    except (HTTPError, URLError, TimeoutError, UnicodeError, OSError, ValueError):
        return None


def _base_model_name(model: Mapping[str, Any]) -> str:
    key = str(model.get("modelKey") or model.get("key") or model.get("displayName") or "")
    return key.split("@", 1)[0].strip()


def _normalise_url(url: str, base_url: str | None = None) -> str | None:
    resolved = urljoin(base_url or "", html.unescape(url.strip().strip("<>")))
    resolved, _ = urldefrag(resolved)
    if any(char.isspace() or ord(char) < 32 for char in resolved) or "{" in resolved or "}" in resolved:
        return None
    parsed = urlparse(resolved)
    if parsed.scheme != "https" or not parsed.netloc:
        return None
    return resolved.rstrip("/")


def _repo_id_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.netloc.lower() not in _HF_HOSTS:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[0] in {"api", "datasets", "spaces"}:
        return None
    return "/".join(parts[:2])


def _hf_repo_urls(model: Mapping[str, Any]) -> list[str]:
    """Return likely HF model-card URLs for the installed model."""
    urls: list[str] = []
    explicit = str(model.get("hf_url") or "").strip()
    if explicit:
        normalized = _normalise_url(explicit)
        if normalized and _repo_id_from_url(normalized):
            urls.append(normalized)

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
    # IBM's generic Granite landing page links to the newest generation. That
    # is not safe evidence for an older model: sampling recommendations are
    # generation-specific and must not flow backwards from Granite 4.2.
    if publisher == "ibm-granite" or "granite-4." in model_name:
        generation_match = re.search(r"granite[- ]4[.]([012])", model_name)
        if generation_match:
            urls.append(f"https://www.ibm.com/granite/docs/models/granite4-{generation_match.group(1)}")
        else:
            urls.append("https://www.ibm.com/granite/")
    for name, candidates in _MANUFACTURER_SOURCES.items():
        if name == "ibm":
            continue
        if publisher == name or publisher.startswith(f"{name}-") or name in model_name:
            urls.extend(candidates)
    return _unique_urls(urls)


def _granite_generation(model: Mapping[str, Any]) -> str | None:
    """Return the generation token used by IBM's Granite documentation URLs."""
    match = re.search(r"granite[- ]4[.]([012])", _base_model_name(model).lower())
    return f"granite4-{match.group(1)}" if match else None


def _compatible_official_source(url: str, generation: str | None) -> bool:
    """Reject cross-generation IBM Granite documentation links."""
    if generation is None:
        return True
    parsed = urlparse(url)
    if parsed.netloc.lower() != "www.ibm.com":
        return True
    if "/granite/docs/models/granite4-" not in parsed.path.lower():
        return True
    return generation in parsed.path.lower()


def _unique_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        normalized = _normalise_url(url)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _known_official_hosts() -> set[str]:
    hosts: set[str] = set()
    for roots in _MANUFACTURER_SOURCES.values():
        hosts.update(urlparse(root).netloc.lower().split(":", 1)[0] for root in roots)
    return hosts


def _is_known_official_url(url: str, publisher: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower().split(":", 1)[0]
    if host in _HF_HOSTS or host in _known_official_hosts():
        return True
    return any(urlparse(root).netloc.lower() == host for root in _MANUFACTURER_SOURCES.get(publisher.lower(), ()))


def _linked_official_sources(text: str, publisher: str, base_url: str) -> list[str]:
    """Extract safe official links, including relative documentation links."""
    links: list[str] = []
    candidates: list[tuple[str, str]] = []
    candidates.extend((match.group(1), match.group(2)) for match in _MARKDOWN_LINK.finditer(text))
    candidates.extend(("", match.group(1)) for match in _HTML_LINK.finditer(text))
    for label, raw_url in candidates:
        join_base = base_url if base_url.endswith("/") else f"{base_url}/"
        normalized = _normalise_url(raw_url.rstrip(".,)"), join_base)
        if not normalized:
            continue
        if _is_known_official_url(normalized, publisher) or (
            _OFFICIAL_LINK_LABELS.search(label) and urlparse(normalized).netloc.lower() in _known_official_hosts()
        ):
            links.append(normalized)
    return _unique_urls(links)


def _strip_markup(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(text)


def _link_score(url: str) -> int:
    path = urlparse(url).path.lower()
    return sum(1 for term in _CRAWL_TERMS if term in path)


def _collect_document(
    url: str,
    priority: int,
    fetch: FetchText,
    timeout_s: float,
    documents: list[SourceDocument],
    visited: set[str],
) -> str | None:
    normalized = _normalise_url(url)
    if not normalized or normalized in visited:
        return None
    visited.add(normalized)
    text = fetch(normalized, timeout_s)
    if text:
        documents.append(SourceDocument(normalized, text, priority))
    return text


def _crawl_official_sources(
    seeds: list[tuple[str, int]],
    publisher: str,
    fetch: FetchText,
    timeout_s: float,
    documents: list[SourceDocument],
    visited: set[str],
    generation: str | None = None,
) -> None:
    """Follow a small, same-domain documentation frontier."""
    queue: deque[tuple[str, int, int]] = deque((url, priority, 0) for url, priority in seeds)
    pages = 0
    while queue and pages < _MAX_OFFICIAL_PAGES:
        url, priority, depth = queue.popleft()
        if not _compatible_official_source(url, generation):
            continue
        text = _collect_document(url, priority, fetch, timeout_s, documents, visited)
        if not text:
            continue
        pages += 1
        if depth >= _MAX_OFFICIAL_DEPTH:
            continue
        links = sorted(
            (link for link in _linked_official_sources(text, publisher, url) if _compatible_official_source(link, generation)),
            key=_link_score,
            reverse=True,
        )
        for linked in links[:_MAX_LINKS_PER_PAGE]:
            host = urlparse(linked).netloc.lower()
            if host in _HF_HOSTS:
                continue
            queue.append((linked, min(priority, 2), depth + 1))


def _raw_hf_urls(repo_id: str) -> list[str]:
    return [
        f"https://huggingface.co/{repo_id}/raw/main/README.md",
        f"https://huggingface.co/{repo_id}/raw/master/README.md",
    ]


def _parse_json(text: str | None) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _repo_id_from_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    for prefix in ("base_model:", "quantized:", "finetune:"):
        if candidate.startswith(prefix):
            candidate = candidate[len(prefix) :]
    if candidate.count("/") == 1 and all(part.strip() for part in candidate.split("/")):
        return candidate.strip()
    return None


def _base_model_ids(metadata: Mapping[str, Any]) -> list[str]:
    """Extract base-model repository IDs from HF API metadata/card data."""
    found: list[str] = []
    tags = metadata.get("tags")
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, str) and tag.startswith("base_model:"):
                repo_id = _repo_id_from_value(tag)
                if repo_id:
                    found.append(repo_id)
    for key in ("base_model", "baseModel", "baseModels"):
        value = metadata.get(key)
        values = value if isinstance(value, list) else [value]
        for item in values:
            repo_id = _repo_id_from_value(item)
            if repo_id:
                found.append(repo_id)
    card_data = metadata.get("cardData")
    if isinstance(card_data, Mapping):
        for key in ("base_model", "baseModel", "baseModels"):
            value = card_data.get(key)
            values = value if isinstance(value, list) else [value]
            for item in values:
                repo_id = _repo_id_from_value(item)
                if repo_id:
                    found.append(repo_id)
    return _unique_strings(found)


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _search_terms(model: Mapping[str, Any]) -> list[str]:
    base = _base_model_name(model).split("/", 1)[-1]
    simplified = re.sub(r"(?i)(?:[-_](?:gguf|i\d+|mxfp\d+|q\d+.*))$", "", base)
    return _unique_strings([base, simplified])


def _discover_hf_repositories(
    model: Mapping[str, Any],
    hf_urls: list[str],
    fetch: FetchText,
    timeout_s: float,
) -> list[tuple[str, int]]:
    """Resolve quantizer aliases and missing cards through the HF API."""
    repositories: list[tuple[str, int]] = []
    seen: set[str] = set()

    def add(repo_id: str | None, priority: int) -> None:
        if repo_id and repo_id not in seen:
            seen.add(repo_id)
            repositories.append((repo_id, priority))

    for url in hf_urls:
        repo_id = _repo_id_from_url(url)
        if not repo_id:
            continue
        api_url = f"https://huggingface.co/api/models/{quote(repo_id, safe='/')}?full=false"
        metadata = _parse_json(fetch(api_url, timeout_s))
        if isinstance(metadata, Mapping):
            for base_id in _base_model_ids(metadata):
                add(base_id, 3)

    for query in _search_terms(model):
        api_url = f"https://huggingface.co/api/models?search={quote(query)}&limit={_MAX_HF_SEARCH_RESULTS}&full=false"
        result = _parse_json(fetch(api_url, timeout_s))
        if not isinstance(result, list):
            continue
        for item in result:
            if not isinstance(item, Mapping):
                continue
            repo_id = item.get("id") or item.get("modelId")
            if not isinstance(repo_id, str) or repo_id.count("/") != 1:
                continue
            add(repo_id, 2)
            for base_id in _base_model_ids(item):
                add(base_id, 3)
        if repositories:
            break
    return repositories[:12]


def _profile_context(lines: list[str], index: int) -> tuple[str, int]:
    start = max(0, index - 1)
    # Include the heading immediately before a parameter line, but not the
    # following profile. Looking ahead caused adjacent profiles to bleed into
    # one another and made category resolution non-deterministic.
    end = min(len(lines), index + 1)
    context = " ".join(lines[start:end])
    lower = context.lower()
    cue = sum(
        1 for term in ("recommend", "suggest", "sampling", "generation", "instruct", "default", "mode") if term in lower
    )
    return context, cue


def _extract_candidates(
    document: SourceDocument,
    profile: str = "default",
) -> dict[str, list[SamplingCandidate]]:
    candidates: dict[str, list[SamplingCandidate]] = {field: [] for field in SUPPORTED_FIELDS}
    lines = _strip_markup(document.text).splitlines()
    for index, line in enumerate(lines):
        group = index // 3
        for field, pattern in _FIELD_PATTERNS.items():
            for match in pattern.finditer(line):
                context, cue = _profile_context(lines, index)
                lower_context = context.lower()
                before_match = line[: match.start()].lower()
                thinking_matches = list(
                    re.finditer(r"(?<!non[- ])thinking mode|reasoning mode|enable_thinking=true", before_match)
                )
                thinking_markers = [match_.start() for match_ in thinking_matches]
                non_thinking_markers = [
                    before_match.rfind("non-thinking"),
                    before_match.rfind("non thinking"),
                    before_match.rfind("instruct mode"),
                    before_match.rfind("enable_thinking=false"),
                ]
                last_thinking = max(thinking_markers, default=-1)
                last_non_thinking = max(non_thinking_markers)
                if last_thinking >= 0 or last_non_thinking >= 0:
                    is_thinking = last_thinking > last_non_thinking
                    is_non_thinking = last_non_thinking > last_thinking
                else:
                    is_thinking = bool(
                        re.search(r"thinking mode|reasoning mode|enable_thinking\s*[:=]\s*true", lower_context)
                    )
                    is_non_thinking = bool(
                        re.search(r"non[- ]thinking|instruct mode|enable_thinking\s*[:=]\s*false", lower_context)
                    )
                if profile == "thinking" and (not is_thinking or is_non_thinking):
                    continue
                current_line = line.lower()
                previous_line = lines[index - 1].lower() if index else ""
                category_marker = _CATEGORY_MARKERS.get(profile)
                if category_marker is not None:
                    target_matches = [
                        marker for marker in category_marker.finditer(current_line) if marker.start() < match.start()
                    ]
                    if target_matches:
                        cue_positions = [(marker.start(), "target") for marker in target_matches]
                        cue_positions.extend(
                            (marker.start(), "mode")
                            for marker in _PROFILE_MODE_MARKER.finditer(current_line)
                            if marker.start() < match.start()
                        )
                        cue_positions.extend(
                            (marker.start(), "other")
                            for other_profile, other_marker in _CATEGORY_MARKERS.items()
                            if other_profile != profile
                            for marker in other_marker.finditer(current_line)
                            if marker.start() < match.start()
                        )
                        latest_position, latest_kind = max(cue_positions, default=(-1, "other"))
                        category_context = current_line[latest_position:] if latest_kind == "target" else ""
                    elif any(marker.search(current_line) for marker in _CATEGORY_MARKERS.values()):
                        category_context = ""
                    elif re.search(
                        r"(?i)\b(?:thinking|reasoning) mode\b|\b(?:instruct|non[- ]thinking) mode\b", current_line
                    ):
                        category_context = ""
                    elif category_marker.search(previous_line):
                        category_context = f"{previous_line} {current_line}".strip()
                    else:
                        category_context = ""
                else:
                    if profile == "normal":
                        normal_matches = [
                            marker
                            for marker in _NORMAL_PROFILE_MARKER.finditer(current_line)
                            if marker.start() < match.start()
                        ]
                        if normal_matches:
                            category_context = current_line[max(marker.start() for marker in normal_matches) :]
                        elif any(marker.search(current_line) for marker in _CATEGORY_MARKERS.values()):
                            category_context = current_line
                        else:
                            category_context = current_line
                    else:
                        category_context = current_line
                        if not any(marker.search(current_line) for marker in _CATEGORY_MARKERS.values()):
                            category_context = f"{previous_line} {current_line}".strip()
                if profile == "normal" and is_thinking and not is_non_thinking:
                    continue
                if profile == "normal" and any(
                    marker.search(category_context) for marker in _CATEGORY_MARKERS.values()
                ):
                    continue
                if category_marker is not None and not category_marker.search(category_context):
                    continue
                try:
                    value = float(match.group(1))
                except ValueError:
                    continue
                lower, upper = _VALUE_LIMITS[field]
                if not lower <= value <= upper:
                    continue
                if field == "top_k" and value != int(value):
                    continue
                candidates[field].append(SamplingCandidate(value, document.url, context.strip()[:300], group, cue))
    return candidates


def _resolve_profile(
    documents: list[SourceDocument], profile: str
) -> tuple[dict[str, float | int], dict[str, dict[str, str]], list[str]]:
    groups: dict[tuple[int, str, int], dict[str, list[SamplingCandidate]]] = {}
    for document in documents:
        extracted = _extract_candidates(document, profile)
        for field, candidates in extracted.items():
            for candidate in candidates:
                key = (document.priority, document.url, candidate.group)
                groups.setdefault(key, {}).setdefault(field, []).append(candidate)

    viable: list[tuple[int, int, dict[str, float | int], dict[str, dict[str, str]]]] = []
    for (priority, _url, _group), fields in groups.items():
        values: dict[str, float | int] = {}
        evidence: dict[str, dict[str, str]] = {}
        conflict = False
        cue = 0
        for field, candidates in fields.items():
            distinct = {candidate.value for candidate in candidates}
            if len(distinct) != 1:
                conflict = True
                break
            candidate = candidates[0]
            values[field] = int(candidate.value) if field == "top_k" else candidate.value
            evidence[field] = {"url": candidate.url, "excerpt": candidate.excerpt}
            cue = max(cue, candidate.cue)
        if not conflict and "temperature" in values and "top_p" in values:
            viable.append((priority, cue + len(values), values, evidence))

    if not viable:
        return {}, {}, []
    max_priority = max(item[0] for item in viable)
    priority_matches = [item for item in viable if item[0] == max_priority]
    max_score = max(item[1] for item in priority_matches)
    best = [item for item in priority_matches if item[1] == max_score]
    signatures = {tuple(sorted(item[2].items())) for item in best}
    if len(signatures) != 1:
        return {}, {}, ["profile"]
    _, _, values, evidence = best[0]
    return values, evidence, []


def _source_evidence(
    profile: str,
    values: Mapping[str, float | int],
    evidence: Mapping[str, Mapping[str, str]],
    *,
    evidence_kind: str = "direct",
    derived_from: str | None = None,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, float | int]] = {}
    for field, value in values.items():
        if field not in evidence:
            continue
        source = evidence[field]
        key = (source["url"], source["excerpt"])
        grouped.setdefault(key, {})[field] = value

    items: list[dict[str, Any]] = []
    for (url, excerpt), grouped_values in grouped.items():
        item: dict[str, Any] = {
            "profile": profile,
            "values": grouped_values,
            "evidence_kind": evidence_kind,
        }
        # A derived profile is traceable through its source category. Repeating
        # the inherited URL and excerpt for every derived field made the YAML
        # noisy and obscured the actual provenance chain.
        if evidence_kind == "direct":
            item["url"] = url
            item["excerpt"] = excerpt
        if derived_from is not None:
            item["derived_from"] = derived_from
        items.append(item)
    return items


def _unresolved_evidence(profile: str, reason: str) -> list[dict[str, str]]:
    return [
        {
            "profile": profile,
            "evidence_kind": "unresolved",
            "reason": reason,
        }
    ]


def _research_source_urls(
    documents: list[SourceDocument],
    *evidence_maps: Mapping[str, Mapping[str, str]],
) -> list[str]:
    """Return a compact provenance list for terminal research outcomes.

    The crawler may inspect linked navigation pages while resolving a model.
    Those pages are useful search inputs, but they are not all evidence. Keep
    URLs from matched field evidence when available; otherwise retain only the
    highest-priority fetched documents as a bounded record of what was tried.
    """
    evidence_urls = {
        str(source["url"])
        for evidence in evidence_maps
        for source in evidence.values()
        if source.get("url")
    }
    if evidence_urls:
        return sorted(evidence_urls)
    highest_priority = max((document.priority for document in documents), default=None)
    if highest_priority is None:
        return []
    return sorted({document.url for document in documents if document.priority == highest_priority})[
        :_MAX_TERMINAL_SOURCE_URLS
    ]


def research_sampling_report(
    model: Mapping[str, Any],
    timeout_s: float = 8.0,
    fetcher: FetchText | None = None,
) -> dict[str, Any]:
    """Return a confirmed or explicitly unresolved onboarding research report."""
    fetch = fetcher or _fetch_text
    publisher = str(model.get("publisher") or "").strip().lower()
    generation = _granite_generation(model)
    hf_urls = _hf_repo_urls(model)
    documents: list[SourceDocument] = []
    visited: set[str] = set()

    for url in hf_urls:
        repo_id = _repo_id_from_url(url)
        if not repo_id:
            continue
        for raw_url in _raw_hf_urls(repo_id):
            text = _collect_document(raw_url, 4, fetch, timeout_s, documents, visited)
            if text:
                linked = [
                    link
                    for link in _linked_official_sources(text, publisher, url)
                    if _compatible_official_source(link, generation)
                ]
                _crawl_official_sources(
                    [(linked_url, 3) for linked_url in linked[:6]],
                    publisher,
                    fetch,
                    timeout_s,
                    documents,
                    visited,
                    generation,
                )

    _crawl_official_sources(
        [(url, 2) for url in _manufacturer_urls(model)],
        publisher,
        fetch,
        timeout_s,
        documents,
        visited,
        generation,
    )

    normal_values, normal_evidence, normal_conflicts = _resolve_profile(documents, "normal")
    if "temperature" not in normal_values or "top_p" not in normal_values or normal_conflicts:
        for repo_id, priority in _discover_hf_repositories(model, hf_urls, fetch, timeout_s):
            for raw_url in _raw_hf_urls(repo_id):
                text = _collect_document(raw_url, priority, fetch, timeout_s, documents, visited)
                if text:
                    linked = [
                        link
                        for link in _linked_official_sources(text, publisher, f"https://huggingface.co/{repo_id}")
                        if _compatible_official_source(link, generation)
                    ]
                    _crawl_official_sources(
                        [(linked_url, min(priority, 3)) for linked_url in linked[:6]],
                        publisher,
                        fetch,
                        timeout_s,
                        documents,
                        visited,
                        generation,
                    )
        normal_values, normal_evidence, normal_conflicts = _resolve_profile(documents, "normal")

    thinking_values, thinking_evidence, thinking_conflicts = _resolve_profile(documents, "thinking")
    source_urls = _research_source_urls(documents, normal_evidence, thinking_evidence)
    if "temperature" not in normal_values or "top_p" not in normal_values:
        status = "conflict" if normal_conflicts else ("unresolved" if documents else "not_found")
        unresolved = _unresolved_evidence(
            "math",
            "Kein allgemeines Profil; Coding-/Math-Fallback kann nicht belastbar bestimmt werden.",
        )
        return {
            "sampling_research_status": status,
            "sampling_sources": source_urls,
            "sampling_evidence": unresolved,
            "sampling_category_status": {"math": "unresolved"},
        }

    category_status: dict[str, str] = {}
    sampling: dict[str, Any] = {}
    evidence = _source_evidence("normal", normal_values, normal_evidence)

    coding_values, coding_evidence, coding_conflicts = _resolve_profile(documents, "coding")
    source_urls = _research_source_urls(documents, normal_evidence, thinking_evidence, coding_evidence)
    if coding_conflicts:
        return {
            "sampling_research_status": "conflict",
            "sampling_sources": source_urls,
            "sampling_evidence": evidence
            + _unresolved_evidence("coding", "Widersprüchliche Coding-Profile.")
            + _unresolved_evidence("math", "Coding-Profil widersprüchlich; Math-Ableitung nicht belastbar."),
            "sampling_category_status": {"coding": "unresolved", "math": "unresolved"},
        }
    if "temperature" in coding_values and "top_p" in coding_values:
        sampling["coding"] = dict(coding_values)
        evidence.extend(_source_evidence("coding", coding_values, coding_evidence))
        category_status["coding"] = "direct"
        coding_source = "coding"
        coding_source_evidence = coding_evidence
    else:
        sampling["coding"] = dict(normal_values)
        category_status["coding"] = "derived"
        coding_source = "normal"
        coding_source_evidence = normal_evidence
        evidence.extend(
            _source_evidence("coding", normal_values, normal_evidence, evidence_kind="derived", derived_from="normal")
        )

    for category in ("knowledge", "agentic"):
        values, profile_evidence, conflicts = _resolve_profile(documents, category)
        source_urls = _research_source_urls(
            documents,
            normal_evidence,
            thinking_evidence,
            coding_evidence,
            profile_evidence,
        )
        if conflicts:
            return {
                "sampling_research_status": "conflict",
                "sampling_sources": source_urls,
                "sampling_evidence": evidence
                + _unresolved_evidence(category, f"Widersprüchliche {category}-Profile.")
                + _unresolved_evidence("math", f"Widersprüchliches {category}-Profil; Math-Status bleibt ungeklärt."),
                "sampling_category_status": {**category_status, category: "unresolved", "math": "unresolved"},
            }
        if "temperature" in values and "top_p" in values:
            sampling[category] = dict(values)
            evidence.extend(_source_evidence(category, values, profile_evidence))
            category_status[category] = "direct"
        else:
            fallback_values = (
                thinking_values if category == "agentic" and "temperature" in thinking_values else normal_values
            )
            fallback_evidence = (
                thinking_evidence if category == "agentic" and "temperature" in thinking_values else normal_evidence
            )
            fallback_profile = "thinking" if category == "agentic" and "temperature" in thinking_values else "normal"
            sampling[category] = dict(fallback_values)
            evidence.extend(
                _source_evidence(
                    category,
                    fallback_values,
                    fallback_evidence,
                    evidence_kind="derived",
                    derived_from=fallback_profile,
                )
            )
            category_status[category] = "derived"

    math_values, math_evidence, math_conflicts = _resolve_profile(documents, "math")
    source_urls = _research_source_urls(
        documents,
        normal_evidence,
        thinking_evidence,
        coding_evidence,
        math_evidence,
    )
    if math_conflicts:
        return {
            "sampling_research_status": "conflict",
            "sampling_sources": source_urls,
            "sampling_evidence": evidence + _unresolved_evidence("math", "Widersprüchliche Math-Profile."),
            "sampling_category_status": {**category_status, "math": "unresolved"},
        }
    if "temperature" in math_values and "top_p" in math_values:
        sampling["math"] = dict(math_values)
        evidence.extend(_source_evidence("math", math_values, math_evidence))
        category_status["math"] = "direct"
    else:
        sampling["math"] = dict(coding_values if coding_source == "coding" else normal_values)
        evidence.extend(
            _source_evidence(
                "math",
                sampling["math"],
                coding_source_evidence,
                evidence_kind="derived",
                derived_from="coding",
            )
        )
        category_status["math"] = "derived"

    if "temperature" in thinking_values and "top_p" in thinking_values and not thinking_conflicts:
        sampling["thinking"] = {"enabled": True, **thinking_values}
        evidence.extend(_source_evidence("thinking", thinking_values, thinking_evidence))
        category_status["thinking"] = "direct"

    return {
        "sampling": sampling,
        "sampling_source": "web-research",
        "sampling_research_status": "confirmed",
        "sampling_sources": sorted({item["url"] for item in evidence if "url" in item}),
        "sampling_evidence": evidence,
        "sampling_category_status": category_status,
    }


def research_sampling(
    model: Mapping[str, Any],
    timeout_s: float = 8.0,
    fetcher: FetchText | None = None,
) -> dict[str, Any] | None:
    """Return only confirmed sampling values for backward-compatible callers."""
    report = research_sampling_report(model, timeout_s=timeout_s, fetcher=fetcher)
    return report if report.get("sampling_research_status") == "confirmed" else None
