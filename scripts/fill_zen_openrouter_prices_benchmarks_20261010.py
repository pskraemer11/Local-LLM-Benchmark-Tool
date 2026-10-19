from __future__ import annotations

import copy
import json
import os
import re
import shutil
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import openpyxl
from openpyxl.comments import Comment

from update_price_benchmark_workbook_20261010 import zen_prices


WORKBOOK = Path(os.environ.get("PRICE_WORKBOOK") or Path.home() / "Documents" / "Computer+Handy" / "AI-Grundsatz_u_Prompting" / "Preise (Online)" / "Preisvergleich OpenCode Go+Zen, Marktplätze_Arbeitskopie_20261010.xlsx")
PRE_EDIT_BACKUP = WORKBOOK.with_name(WORKBOOK.stem + ".before_fill_20261010.xlsx")
AA_URL = "https://artificialanalysis.ai/api/v2/language/models/free"
AA_DOCS = "https://artificialanalysis.ai/data-api/docs#getLanguageModelsFree"
ZEN_DOCS = "https://dev.opencode.ai/docs/zen"
OR_MODELS = "https://openrouter.ai/api/v1/models"
AA_SNAPSHOT = Path(__file__).resolve().parents[1] / "data" / "artificial-analysis-free-snapshot-20261010.json"


def get_json(url: str, headers: dict[str, str] | None = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.load(response)


def norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def fetch_aa() -> tuple[list[dict], dict]:
    key = os.environ.get("ARTIFICIAL_ANALYSIS_API_KEY")
    if not key:
        raise RuntimeError("ARTIFICIAL_ANALYSIS_API_KEY is not available")
    rows: list[dict] = []
    page = 1
    meta: dict = {}
    while True:
        payload = get_json(f"{AA_URL}?page={page}", {"x-api-key": key, "Accept": "application/json"})
        page_rows = payload.get("data") or []
        rows.extend(page_rows)
        meta = payload.get("meta") or {}
        pagination = payload.get("pagination") or {}
        if pagination.get("has_more") is False:
            break
        page += 1
        if page > 20:
            raise RuntimeError("AA pagination did not terminate")
    ids = [str(row.get("slug") or row.get("id") or "") for row in rows]
    if not rows or len(ids) != len(set(ids)):
        raise RuntimeError("AA response has no rows or duplicate model identifiers")
    return rows, meta


def load_aa_with_snapshot() -> tuple[list[dict], dict, str]:
    try:
        rows, meta = fetch_aa()
        return rows, meta, "live API"
    except Exception as exc:
        if not AA_SNAPSHOT.exists():
            raise
        snapshot = json.loads(AA_SNAPSHOT.read_text(encoding="utf-8"))
        rows = snapshot.get("data") or []
        meta = snapshot.get("meta") or {}
        if not rows:
            raise RuntimeError(f"AA live API failed and snapshot is empty: {exc}") from exc
        meta = {**meta, "fallback_reason": type(exc).__name__}
        return rows, meta, f"canonical snapshot fallback ({type(exc).__name__})"


def fetch_or() -> list[dict]:
    payload = get_json(OR_MODELS)
    rows = payload.get("data") or []
    if not rows:
        raise RuntimeError("OpenRouter model catalog is empty")
    return rows


def score(row: dict, key: str) -> object:
    evaluations = row.get("evaluations") or {}
    return evaluations.get(f"artificial_analysis_{key}_index")


def aa_lookup(rows: list[dict]) -> dict[str, dict]:
    return {norm(row.get("slug")): row for row in rows if row.get("slug")}


def or_price(model: dict) -> tuple[object, object, object, object]:
    p = model.get("pricing") or {}

    def convert(key: str) -> object:
        value = p.get(key)
        if value in (None, "", "-1", -1):
            return None
        return float(value) * 1_000_000

    return convert("prompt"), convert("completion"), convert("input_cache_read"), convert("input_cache_write")


def exact_or_for_row(name: str, models_by_id: dict[str, dict]) -> tuple[str | None, dict | None]:
    # Parenthesized Max/High/Xhigh and dated/release variants are intentionally
    # not collapsed to a base model: OpenRouter must expose the same variant.
    if "(" in name or "free" in name.lower():
        return None, None
    target = norm(re.sub(r"\s*[<>≤].*$", "", name).strip())
    candidates: list[tuple[str, dict]] = []
    for model_id, model in models_by_id.items():
        if ":batch" in model_id.lower():
            continue
        base = model_id.split("/", 1)[-1]
        display = str(model.get("name") or "")
        display = display.split(":", 1)[-1].strip()
        if norm(base) == target or norm(display) == target:
            candidates.append((model_id, model))
    if len(candidates) == 1:
        return candidates[0]
    return None, None


def zen_key(name: str) -> str:
    base = name.split("(", 1)[0].strip()
    return norm(base)


def update_zen(ws, aa_rows: list[dict], aa_meta: dict) -> dict[str, int]:
    lookup = aa_lookup(aa_rows)
    # Make the available AA composites explicit; the old headings mixed
    # different benchmark families and made an unverified value misleading.
    headers = {
        7: "AA Coding Index",
        8: "AA Agentic Coding",
        9: "AA Mathematics (MATH-500)",
        10: "AA Agentic Index",
        11: "AA Instruction Following",
    }
    for col, value in headers.items():
        ws.cell(6, col).value = value
    ws["A2"] = ZEN_DOCS
    ws["M2"] = "Stand:"
    ws["N2"] = datetime.now(timezone.utc).date()
    ws["N2"].number_format = "yyyy-mm-dd"
    for col in range(2, 6):
        ws.cell(6, col).comment = Comment(
            f"Quelle: OpenCode Zen pricing table, {ZEN_DOCS}. Preise in USD je 1 Mio. Tokens; Abruf 2026-10-10.",
            "Codex",
        )
    for col in (7, 10):
        ws.cell(6, col).comment = Comment(
            f"Quelle: Artificial Analysis Free Language Models API, {AA_DOCS}; Index-Version {aa_meta.get('intelligence_index_version')}; Abruf 2026-10-10.",
            "Codex",
        )
    filled_prices = 0
    filled_coding = 0
    filled_agentic = 0
    for row in range(7, 73):
        name = str(ws.cell(row, 1).value or "")
        prices = zen_prices().get(zen_key(name)) if "(" not in name or "Free" not in name else zen_prices().get(norm(name))
        # Exact official pricing map; unknown legacy names are left untouched
        # as unverified rather than inheriting a similarly named price.
        if prices is None:
            for col in range(2, 6):
                ws.cell(row, col).value = "unverified"
        else:
            for col, value in zip(range(2, 6), prices):
                ws.cell(row, col).value = value
            filled_prices += 1
        for col in range(7, 12):
            ws.cell(row, col).value = "unverified"
        # Only a current exact AA canonical slug may populate a score. Do not
        # transfer a base score to effort, date, or quality variants.
        slug = zen_key(name).replace(".", "-")
        aa = lookup.get(slug)
        if aa:
            coding = score(aa, "coding")
            agentic = score(aa, "agentic")
            if coding is not None:
                ws.cell(row, 7).value = coding
                filled_coding += 1
            if agentic is not None:
                ws.cell(row, 10).value = agentic
                filled_agentic += 1
    note_row = 74
    notes = [
        f"Aktualisiert 2026-10-10 UTC. Preise: {ZEN_DOCS}; Benchmarks: {AA_DOCS}.",
        f"AA Free API: {len(aa_rows)} Datensätze, Index-Version {aa_meta.get('intelligence_index_version')}; exakte AA-Zuordnung: Coding={filled_coding}, Agentic={filled_agentic}.",
        "AA Coding Index und AA Agentic Index sind Composite-Indizes. MATH-500, ein separater Agentic-Coding-Test und Instruction Following wurden nicht aus anderen Indizes abgeleitet und bleiben unverified, wenn keine exakte Primärquelle vorliegt.",
        "unverified bedeutet: kein verifizierter, vergleichbarer Primärquellenwert für genau diese Modell-/Release-/Qualitätsvariante; es ist kein Nullwert.",
    ]
    for offset, text in enumerate(notes):
        ws.cell(note_row + offset, 1).value = text
        ws.merge_cells(start_row=note_row + offset, start_column=1, end_row=note_row + offset, end_column=14)
    return {"prices": filled_prices, "coding": filled_coding, "agentic": filled_agentic}


def update_comparison(ws, or_models: list[dict]) -> dict[str, int]:
    by_id = {str(model.get("id")): model for model in or_models if model.get("id")}
    filled = 0
    exact_ids = 0
    for row in range(5, ws.max_row + 1):
        name = str(ws.cell(row, 1).value or "")
        model_id, model = exact_or_for_row(name, by_id)
        if not model:
            continue
        values = or_price(model)
        for col, value in zip(range(7, 11), values):
            ws.cell(row, col).value = value
        ws.cell(row, 18).value = model_id
        ws.cell(row, 19).value = "OpenRouter exact model ID"
        ws.cell(row, 20).value = "verified" if any(value is not None for value in values) else "unverified"
        ws.cell(row, 21).value = "OpenRouter public catalog; exact base-model ID; no :batch variant."
        filled += 1
        exact_ids += 1
    ws["A1"] = "Stand: 2026-10-10 – Vergleich OpenCode Zen und OpenRouter"
    ws["A3"] = "AA-Filter: exakte Varianten mit Artificial Analysis Intelligence Index > 40; fehlende oder nicht vergleichbare Preise/Benchmarks bleiben unverified/leer."
    for col in range(7, 11):
        ws.cell(4, col).comment = Comment(f"Quelle: OpenRouter public model catalog, {OR_MODELS}; USD je 1 Mio. Tokens; Abruf 2026-10-10.", "Codex")
    return {"prices": filled, "exact_ids": exact_ids}


def main() -> None:
    if not PRE_EDIT_BACKUP.exists():
        shutil.copy2(WORKBOOK, PRE_EDIT_BACKUP)
    aa_rows, aa_meta, aa_transport = load_aa_with_snapshot()
    or_models = fetch_or()
    wb = openpyxl.load_workbook(WORKBOOK)
    zen_stats = update_zen(wb["OpenCode Zen"], aa_rows, aa_meta)
    or_stats = update_comparison(wb["Vergleich Marktplätze"], or_models)
    wb.save(WORKBOOK)
    print(json.dumps({"zen": zen_stats, "openrouter": or_stats, "aa_records": len(aa_rows), "or_models": len(or_models), "aa_transport": aa_transport}, ensure_ascii=False))


if __name__ == "__main__":
    main()
