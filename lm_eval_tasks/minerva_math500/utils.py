import re
import datasets


def doc_to_text(doc: dict) -> str:
    return (
        "Solve the following math problem. Put the final answer in \\boxed{}.\n\n"
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
    m = re.search(r"\\boxed\{([^}]+)\}", text)
    return m.group(1) if m else None


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
