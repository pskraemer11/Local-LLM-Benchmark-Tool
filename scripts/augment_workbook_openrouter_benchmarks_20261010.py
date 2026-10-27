from __future__ import annotations

import copy
import json
import os
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

WORKBOOK = Path.home() / "Documents" / "Computer+Handy" / "AI-Grundsatz_u_Prompting" / "Preise (Online)" / "Preisvergleich OpenCode Go+Zen, Marktplätze_Arbeitskopie_20261010.xlsx"


def get_json(url: str, key: str) -> dict:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def fetch_task(key: str, task: str) -> tuple[dict, dict]:
    url = f"https://openrouter.ai/api/v1/benchmarks?source=artificial-analysis&task_type={task}"
    payload = get_json(url, key)
    meta = payload.get("meta") or {}
    rows = payload.get("data") or []
    if meta.get("source") != "artificial-analysis" or meta.get("task_type") != task:
        raise RuntimeError(f"Invalid OpenRouter benchmark metadata for {task}")
    if meta.get("model_count") != len(rows):
        raise RuntimeError(f"OpenRouter row count mismatch for {task}")
    slugs = [row.get("model_permaslug") for row in rows]
    if not slugs or len(slugs) != len(set(slugs)):
        raise RuntimeError(f"OpenRouter model_permaslug values are not unique for {task}")
    return {str(row.get("display_name")): row for row in rows if row.get("display_name")}, meta


def main() -> None:
    key = os.environ.get("OPENROUTER_MANAGEMENT_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_MANAGEMENT_KEY is not available")
    tasks = {task: fetch_task(key, task) for task in ("intelligence", "coding", "agentic")}
    wb = openpyxl.load_workbook(WORKBOOK)
    ws = wb["Vergleich Marktplätze"]
    # Ensure the newly added columns are available while preserving the existing layout.
    headers = {
        22: "OR AA model_permaslug",
        23: "OR AA Intelligence",
        24: "OR AA Coding",
        25: "OR AA Agentic",
        26: "OR AA as_of",
        27: "OR transport status",
    }
    for col, header in headers.items():
        ws.cell(4, col).value = header
        ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = 20 if col != 27 else 24
        source = ws.cell(4, 21)
        target = ws.cell(4, col)
        target._style = copy.copy(source._style)
        target.font = Font(bold=True, color="FFFFFF")
        target.fill = PatternFill("solid", fgColor="5B9BD5")
        target.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row in range(5, 5 + 73):
        for col in range(22, 28):
            ws.cell(row, col)._style = copy.copy(ws.cell(row, 21)._style)
            ws.cell(row, col).alignment = Alignment(vertical="top", wrap_text=True)
    by_name: dict[str, list[int]] = {}
    for row in range(5, 5 + 73):
        by_name.setdefault(str(ws.cell(row, 1).value), []).append(row)
    matched = 0
    for name, row_numbers in by_name.items():
        if len(row_numbers) != 1:
            continue
        row = row_numbers[0]
        intel = tasks["intelligence"][0].get(name)
        coding = tasks["coding"][0].get(name)
        agentic = tasks["agentic"][0].get(name)
        anchor = intel or coding or agentic
        if not anchor:
            ws.cell(row, 27).value = "unverified: no exact OR AA display-name match"
            continue
        ws.cell(row, 22).value = anchor.get("model_permaslug")
        ws.cell(row, 23).value = intel.get("intelligence_index") if intel else None
        ws.cell(row, 24).value = coding.get("coding_index") if coding else None
        ws.cell(row, 25).value = agentic.get("agentic_index") if agentic else None
        ws.cell(row, 26).value = (tasks["intelligence"][1].get("as_of") or tasks["coding"][1].get("as_of") or tasks["agentic"][1].get("as_of"))
        ws.cell(row, 27).value = "verified transport: artificial-analysis via openrouter"
        matched += 1
        for col in range(23, 26):
            ws.cell(row, col).number_format = "0.0"
    note_row = 5 + 73 + 2
    # The first workbook build already had notes at this location. Remove
    # those old merges/content before writing the expanded provenance block;
    # overlapping merged cells are invalid for Excel/Calc layout handling.
    for merged in list(ws.merged_cells.ranges):
        if merged.min_row >= note_row:
            ws.unmerge_cells(str(merged))
    for row in range(note_row, ws.max_row + 1):
        for col in range(1, ws.max_column + 1):
            ws.cell(row, col).value = None
    notes = [
        f"OpenRouter benchmark transport retrieved: {datetime.now(UTC).isoformat()} UTC.",
        "Queries: /api/v1/benchmarks?source=artificial-analysis&task_type=intelligence|coding|agentic.",
        "The OR AA columns are transported Artificial Analysis evidence, not OpenRouter-native benchmarks; direct AA columns remain primary.",
        "Counts: " + ", ".join(f"{task}={meta['model_count']}" for task, (_, meta) in tasks.items()) + f"; exact display-name matches in this table={matched}.",
        "OpenRouter source URL: https://openrouter.ai/api/v1/benchmarks; citation metadata is retained in the run record, and no API key is stored.",
    ]
    for offset, note in enumerate(notes):
        ws.cell(note_row + offset, 1).value = note
        ws.merge_cells(start_row=note_row + offset, start_column=1, end_row=note_row + offset, end_column=27)
        ws.cell(note_row + offset, 1).alignment = Alignment(wrap_text=True, vertical="top")
    ws.auto_filter.ref = f"A4:AA{4 + 73}"
    wb.save(WORKBOOK)
    print(json.dumps({"workbook": str(WORKBOOK), "matched": matched, "counts": {task: meta["model_count"] for task, (_, meta) in tasks.items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
