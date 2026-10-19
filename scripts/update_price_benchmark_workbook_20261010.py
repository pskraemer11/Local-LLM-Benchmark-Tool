from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side


SOURCE = Path.home() / "Documents" / "Computer+Handy" / "AI-Grundsatz_u_Prompting" / "Preise (Online)" / "Preisvergleich OpenCode Go+Zen, Marktplätze.xlsx"
RUN_DATE = "2026-10-10"
BACKUP = SOURCE.with_name(f"{SOURCE.stem}.backup_{RUN_DATE.replace('-', '')}.xlsx")
WORKCOPY = SOURCE.with_name(f"{SOURCE.stem}_Arbeitskopie_{RUN_DATE.replace('-', '')}.xlsx")
AA_SNAPSHOT = Path("data") / "artificial-analysis-free-snapshot-20261010.json"


def get_json(url: str, headers: dict[str, str] | None = None) -> dict:
    request = urllib.request.Request(url, headers=headers or {"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def fetch_aa() -> tuple[list[dict], dict, bytes]:
    key = os.environ.get("ARTIFICIAL_ANALYSIS_API_KEY")
    if not key:
        raise RuntimeError("ARTIFICIAL_ANALYSIS_API_KEY is not available")
    pages: list[dict] = []
    page = 1
    while True:
        payload = get_json(
            f"https://artificialanalysis.ai/api/v2/language/models/free?page={page}",
            {"x-api-key": key, "Accept": "application/json"},
        )
        pages.append(payload)
        pagination = payload.get("pagination") or {}
        if not pagination.get("has_more"):
            break
        page += 1
        if page > 100:
            raise RuntimeError("AA pagination did not terminate")
    data = [row for payload in pages for row in payload.get("data", [])]
    ids = [row.get("id") for row in data]
    if len(ids) != len(set(ids)) or any(not item for item in ids):
        raise RuntimeError("AA model IDs are not unique")
    versions = {payload.get("intelligence_index_version") for payload in pages}
    if len(versions) != 1:
        raise RuntimeError("AA index version changed during pagination")
    meta = {
        "source_url": "https://artificialanalysis.ai/api/v2/language/models/free",
        "documentation_url": "https://artificialanalysis.ai/data-api/docs#getLanguageModelsFree",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "tier": pages[0].get("tier"),
        "intelligence_index_version": pages[0].get("intelligence_index_version"),
        "pages": len(pages),
        "records": len(data),
        "has_more_final": pages[-1].get("pagination", {}).get("has_more"),
    }
    serialised = json.dumps({"meta": meta, "data": data}, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    meta["sha256"] = hashlib.sha256(serialised).hexdigest()
    return data, meta, serialised


def fetch_openrouter() -> list[dict]:
    # The public model catalogue is readable without an API key. No private
    # benchmark endpoint is used when direct AA data is available.
    payload = get_json("https://openrouter.ai/api/v1/models")
    models = payload.get("data") or []
    ids = [item.get("id") for item in models]
    if len(ids) != len(set(ids)):
        raise RuntimeError("OpenRouter model IDs are not unique")
    return models


def norm(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def score(row: dict, field: str):
    return (row.get("evaluations") or {}).get(field)


def exact_openrouter_match(aa_row: dict, models: list[dict]) -> dict | None:
    slug = norm(aa_row.get("slug", ""))
    exact = []
    for model in models:
        model_id = str(model.get("id", ""))
        tail = model_id.split("/")[-1].split(":")[0]
        if norm(tail) in {slug, slug + "free"}:
            exact.append(model)
    if len(exact) == 1:
        return exact[0]
    return None


def zen_prices() -> dict[str, tuple[float | str | None, float | str | None, float | str | None, float | str | None]]:
    # Exact model names and current prices from the official Zen pricing table.
    # Values are USD per 1M tokens. Free is represented as numeric zero only
    # when the official table explicitly says Free.
    free = (0.0, 0.0, 0.0, None)
    return {
        "bigpickle": free,
        "spacebunnyfree": free,
        "longcat25previewfree": free,
        "mimov26flashfree": free,
        "mimov25free": free,
        "ling30flashfinfree": free,
        "nemotron3ultrafree": free,
        "nemotron35lightningfree": free,
        "musespark13contributorfree": free,
        "jev113free": free,
        "minimaxm3": (0.30, 1.20, 0.06, None),
        "minimaxm27": (0.30, 1.20, 0.06, None),
        "minimaxm25": (0.30, 1.20, 0.06, None),
        "glm53flash": (0.15, 0.50, 0.03, None),
        "glm53": (1.40, 4.40, 0.26, None),
        "glm52": (1.40, 4.40, 0.26, None),
        "glm51": (1.40, 4.40, 0.26, None),
        "glm5": (1.00, 3.20, 0.20, None),
        "kimik27code": (0.95, 4.00, 0.19, None),
        "kimik3": (3.00, 15.00, 0.30, None),
        "kimik26": (0.95, 4.00, 0.16, None),
        "kimik25": (0.60, 3.00, 0.10, None),
        "qwen38max": (2.00, 6.00, 0.25, 2.50),
        "qwen38flash": (0.15, 0.47, 0.016, 0.20),
        "qwen37max": (2.50, 7.50, 0.50, 3.125),
        "qwen37plus": (0.40, 1.60, 0.04, 0.50),
        "qwen36plus": (0.50, 3.00, 0.05, 0.625),
        "qwen35plus": (0.20, 1.20, 0.02, 0.25),
        "deepseekv41flash": (0.30, 1.20, 0.006, None),
        "deepseekv4pro": (1.74, 3.48, 0.145, None),
        "deepseekv4flash": (0.14, 0.28, 0.028, None),
        "deepseekv4flashvisionexp": (0.14, 0.28, 0.028, None),
        "claudefable51": (10.00, 50.00, 0.25, 12.50),
        "claudefable5": (10.00, 50.00, 1.00, 12.50),
        "claudeopus55": (4.00, 20.00, 0.20, 5.00),
        "claudeopus5": (5.00, 25.00, 0.50, 6.25),
        "claudeopus48": (5.00, 25.00, 0.50, 6.25),
        "claudeopus47": (5.00, 25.00, 0.50, 6.25),
        "claudesonnet55": (2.00, 10.00, 0.20, 2.50),
        "claudesonnet46": (3.00, 15.00, 0.30, 3.75),
        "claudehaiku55": (1.00, 5.00, 0.10, 1.25),
        "grok47": (2.00, 6.00, 0.50, None),
        "grok46": (2.00, 6.00, 0.50, None),
        "musespark13": (1.25, 4.25, 0.15, None),
        "gpt6astra": (10.00, 50.00, 1.00, 12.50),
        "gpt6sol": (2.00, 10.00, 0.20, 2.50),
        "gpt61sol": (2.00, 10.00, 0.10, 2.50),
        "gpt56sol": (4.00, 20.00, 0.40, 5.00),
        "gpt56terra": (2.00, 12.00, 0.20, 2.50),
        "gpt56luna": (0.20, 1.20, 0.02, 0.25),
        "gpt55": (5.00, 30.00, 0.50, None),
        "gpt55pro": (30.00, 180.00, 30.00, None),
        "gpt54": (2.50, 15.00, 0.25, None),
        "gpt54pro": (30.00, 180.00, 30.00, None),
        "gpt54mini": (0.75, 4.50, 0.075, None),
        "gpt54nano": (0.20, 1.25, 0.02, None),
        "gpt53codex": (1.75, 14.00, 0.175, None),
        "gpt52": (1.75, 14.00, 0.175, None),
        "gpt52codex": (1.75, 14.00, 0.175, None),
        "gpt51": (1.07, 8.50, 0.107, None),
        "gpt51codex": (1.07, 8.50, 0.107, None),
        "gpt5": (1.07, 8.50, 0.107, None),
        "gpt5nano": (0.05, 0.40, 0.005, None),
        "gemini38flash": (1.50, 7.50, 0.15, None),
        "gemini37flash": (1.50, 7.50, 0.15, None),
        "gemini35flash": (1.50, 9.00, 0.15, None),
        "gemini35flashlite": (0.30, 2.50, 0.03, None),
    }


def copy_style(source_cell, target_cell) -> None:
    if source_cell.has_style:
        target_cell._style = copy.copy(source_cell._style)
    if source_cell.number_format:
        target_cell.number_format = source_cell.number_format
    if source_cell.alignment:
        target_cell.alignment = copy.copy(source_cell.alignment)


def weighted_formula(row: int, first_col: str) -> str:
    return f'=IF(COUNTA({first_col}{row}:{chr(ord(first_col)+3)}{row})>0,{first_col}{row}+({chr(ord(first_col)+1)}{row}+{chr(ord(first_col)+3)}{row})/2.66+79.3*{chr(ord(first_col)+2)}{row},"")'


def rebuild_comparison(wb: openpyxl.Workbook, aa_rows: list[dict], or_models: list[dict], aa_meta: dict) -> dict:
    if "Vergleich Marktplätze" in wb.sheetnames:
        old = wb["Vergleich Marktplätze"]
        template = old
        wb.remove(old)
    else:
        template = wb[wb.sheetnames[0]]
    ws = wb.create_sheet("Vergleich Marktplätze", wb.sheetnames.index("Benchmarks") if "Benchmarks" in wb.sheetnames else len(wb.sheetnames))
    ws.freeze_panes = "A5"
    widths = [34, 12, 12, 12, 12, 15, 14, 14, 14, 14, 15, 13, 13, 13, 13, 13, 28, 28, 28, 18, 48]
    for idx, width in enumerate(widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(idx)].width = width
    ws.sheet_view.showGridLines = False
    ws["A1"] = f"Stand: {RUN_DATE} – Vergleich OpenCode Zen und OpenRouter"
    ws["A2"] = "Nur die Anbieter OpenCode Zen und OpenRouter sind enthalten. Go, Together AI, DeepInfra und OpenAI direkt wurden aus dieser Übersicht entfernt."
    ws["A3"] = "AA-Filter: exakte Varianten mit Artificial Analysis Intelligence Index > 40; fehlende Preise oder Benchmarks bleiben unverified/leer."
    ws["A4"] = "Model / exakte Variante"
    headers = [
        "Zen Input $/1M", "Zen Output $/1M", "Zen Cached Read $/1M", "Zen Cached Write $/1M", "Zen gewichtete Summe",
        "OpenRouter Input $/1M", "OpenRouter Output $/1M", "OpenRouter Cached Read $/1M", "OpenRouter Cached Write $/1M", "OpenRouter gewichtete Summe",
        "AA Intelligence", "AA Coding", "AA Agentic", "MATH-500", "Release", "AA slug / variant", "OpenRouter model ID", "Match / source", "Status", "Notes",
    ]
    for c, value in enumerate(headers, 2):
        ws.cell(4, c).value = value
    # Reuse the old workbook's visual language for title, metadata, and header rows.
    for c in range(1, 22):
        for r in (1, 2, 3, 4):
            source_cell = template.cell(min(r, template.max_row), min(c, template.max_column))
            copy_style(source_cell, ws.cell(r, c))
    ws["A1"].font = Font(bold=True, size=14, color="FFFFFF")
    ws["A1"].fill = PatternFill("solid", fgColor="1F4E78")
    ws.merge_cells("A1:U1")
    ws.merge_cells("A2:U2")
    ws.merge_cells("A3:U3")
    header_fill = PatternFill("solid", fgColor="5B9BD5")
    for cell in ws[4]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[4].height = 42

    aa_rows = sorted(aa_rows, key=lambda row: score(row, "artificial_analysis_intelligence_index") if isinstance(score(row, "artificial_analysis_intelligence_index"), (int, float)) else -1, reverse=True)
    prices = zen_prices()
    or_lookup: dict[str, dict] = {}
    for item in or_models:
        model_id = str(item.get("id", ""))
        tail = model_id.split("/")[-1].split(":")[0]
        or_lookup.setdefault(norm(tail), item)
    for row_idx, aa in enumerate(aa_rows, 5):
        evaluations = aa.get("evaluations") or {}
        name = aa.get("name") or aa.get("slug")
        slug = aa.get("slug") or ""
        ws.cell(row_idx, 1).value = name
        # Effort-/release-specific AA variants are not silently assigned a
        # base-model Zen price. The slug must be an exact current Zen model
        # identity; otherwise the provider value stays unverified.
        zen = prices.get(norm(slug)) if "(" not in str(name) else None
        exact_or = exact_openrouter_match(aa, or_models)
        or_price = (exact_or or {}).get("pricing") or {}
        vals = [
            *(zen or (None, None, None, None)),
            None,
            float(or_price.get("prompt")) * 1_000_000 if or_price.get("prompt") not in (None, "-1") else None,
            float(or_price.get("completion")) * 1_000_000 if or_price.get("completion") not in (None, "-1") else None,
            float(or_price.get("input_cache_read")) * 1_000_000 if or_price.get("input_cache_read") not in (None, "-1") else None,
            float(or_price.get("input_cache_write")) * 1_000_000 if or_price.get("input_cache_write") not in (None, "-1") else None,
            None,
            evaluations.get("artificial_analysis_intelligence_index"),
            evaluations.get("artificial_analysis_coding_index"),
            evaluations.get("artificial_analysis_agentic_index"),
            None,
            aa.get("release_date"),
            slug,
            (exact_or or {}).get("id"),
            "AA exact; Zen exact" if zen else "AA exact; Zen not exact",
            "verified" if zen or exact_or else "unverified",
            "OpenRouter price exact only; AA composite scores are primary."
            if exact_or
            else "No exact OpenRouter model ID found in public catalog; provider price unverified.",
        ]
        for col, value in enumerate(vals, 2):
            ws.cell(row_idx, col).value = value
        ws.cell(row_idx, 6).value = weighted_formula(row_idx, "B")
        ws.cell(row_idx, 11).value = weighted_formula(row_idx, "G")
        for col in range(1, 22):
            copy_style(template.cell(4 if col > 1 else 4, min(col, template.max_column)), ws.cell(row_idx, col))
            ws.cell(row_idx, col).alignment = Alignment(vertical="top", wrap_text=col in (1, 17, 18, 19, 20, 21))
        for col in (2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14):
            ws.cell(row_idx, col).number_format = "0.0000"
    note_row = 5 + len(aa_rows) + 2
    notes = [
        f"AA source: {aa_meta['source_url']}",
        f"AA documentation: {aa_meta['documentation_url']}",
        f"AA retrieval: {aa_meta['retrieved_at_utc']} | tier={aa_meta['tier']} | index v{aa_meta['intelligence_index_version']} | pages={aa_meta['pages']} | records={aa_meta['records']} | sha256={aa_meta['sha256']}",
        "OpenCode Zen source: https://dev.opencode.ai/docs/zen (official pricing table, USD per 1M tokens).",
        "OpenRouter price source: https://openrouter.ai/api/v1/models (public model catalog, exact model ID only).",
        "Method: AA Intelligence Index > 40; Coding and Agentic are separate AA composite columns; no Knowledge index and no inferred Mathematics score.",
        "unverified means no exact current provider price/model-ID match was verified; it is not a zero price and is excluded from cost ranking.",
    ]
    for offset, note in enumerate(notes):
        ws.cell(note_row + offset, 1).value = note
        ws.merge_cells(start_row=note_row + offset, start_column=1, end_row=note_row + offset, end_column=21)
        ws.cell(note_row + offset, 1).alignment = Alignment(wrap_text=True, vertical="top")
    ws.auto_filter.ref = f"A4:U{4 + len(aa_rows)}"
    return {"rows": len(aa_rows), "openrouter_exact": sum(1 for row in aa_rows if exact_openrouter_match(row, or_models))}


def main() -> None:
    if not SOURCE.exists():
        raise FileNotFoundError(SOURCE)
    update_existing = os.environ.get("UPDATE_EXISTING_WORKCOPY") == "1"
    if BACKUP.exists() and not update_existing:
        raise FileExistsError("Backup already exists; refusing to overwrite it")
    if WORKCOPY.exists() and not update_existing:
        raise FileExistsError("Working copy already exists; refusing to overwrite it")
    aa_rows, aa_meta, raw_snapshot = fetch_aa()
    high = [row for row in aa_rows if isinstance(score(row, "artificial_analysis_intelligence_index"), (int, float)) and score(row, "artificial_analysis_intelligence_index") > 40]
    or_models = fetch_openrouter()
    selected_slugs = {norm(row.get("slug", "")) for row in high}
    # Include every current OpenRouter :free model as a separate exact catalog
    # row, even when AA has no score for it. This is intentionally unverified
    # for AA rather than a transfer from a similarly named base model.
    for model in or_models:
        model_id = str(model.get("id", ""))
        if not model_id.endswith(":free"):
            continue
        tail = model_id.split("/")[-1].split(":")[0]
        slug = tail
        if norm(slug) in selected_slugs:
            continue
        high.append(
            {
                "id": f"openrouter:{model_id}",
                "name": model.get("name") or model_id,
                "slug": slug,
                "release_date": None,
                "model_creator": {"name": model_id.split("/", 1)[0]},
                "evaluations": {},
                "pricing": {},
                "openrouter_free_catalog": True,
            }
        )
        selected_slugs.add(norm(slug))
    if not BACKUP.exists():
        shutil.copy2(SOURCE, BACKUP)
    shutil.copy2(SOURCE, WORKCOPY)
    AA_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    AA_SNAPSHOT.write_bytes(raw_snapshot)
    wb = openpyxl.load_workbook(WORKCOPY)
    if "OpenCode Go" in wb.sheetnames:
        wb.remove(wb["OpenCode Go"])
    result = rebuild_comparison(wb, high, or_models, aa_meta)
    if "Benchmarks" in wb.sheetnames:
        wb["Benchmarks"]["A2"] = f"Primärquellen: Artificial Analysis API und offizielle OpenCode-Zen-/OpenRouter-Preisquellen; Stand {RUN_DATE}."
    wb.save(WORKCOPY)
    print(json.dumps({"backup": str(BACKUP), "workcopy": str(WORKCOPY), "aa_meta": aa_meta, "aa_high_count": len(high), **result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
