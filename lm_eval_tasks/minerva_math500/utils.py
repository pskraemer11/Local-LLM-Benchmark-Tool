import re
import datasets


def doc_to_text(doc: dict) -> str:
    return (
        "Solve the following math problem concisely. Put the final answer in \\boxed{}.\n\n"
        f"Problem: {doc['problem']}\nAnswer:"
    )


def process_docs(dataset: datasets.Dataset) -> datasets.Dataset:
    def _process_doc(doc: dict) -> dict:
        return {
            "problem": doc["problem"],
            "solution": doc["solution"],
            "answer": _extract_boxed(doc["solution"]) or doc.get("answer", ""),
        }
    return dataset.map(_process_doc)


def process_results(doc: dict, results: list[str]) -> dict[str, int]:
    candidates = results[0]
    predicted = _extract_boxed(candidates)
    if predicted is None:
        predicted = _extract_final_answer(candidates)
    if predicted is None:
        predicted = candidates.strip()
    reference = doc["answer"]
    return {"exact_match": 1 if _normalize(predicted) == _normalize(reference) else 0}


def _extract_boxed(text: str) -> str | None:
    m = re.search(r"\\boxed\{", text)
    if not m:
        return None
    start = m.end()
    depth = 1
    i = start
    while i < len(text) and depth > 0:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    if depth == 0:
        return text[start : i - 1]
    return None


def _extract_final_answer(text: str) -> str | None:
    m = re.search(r"final answer is\s*(.+?)\.?\s*I hope", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


def _normalize(text: str) -> str:
    text = text.strip()
    text = text.replace("$", "")
    text = text.replace("\\boxed", "")
    text = text.replace("\\", "")
    text = text.replace("{", "").replace("}", "")
    text = text.replace("(", "").replace(")", "")
    text = text.replace("[", "").replace("]", "")
    text = text.replace(" ", "")
    text = text.replace(",", "")
    text = text.replace(".", "")
    return text.lower()
