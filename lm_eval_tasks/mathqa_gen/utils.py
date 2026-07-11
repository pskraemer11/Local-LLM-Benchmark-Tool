import re

import datasets


def process_docs(dataset: datasets.Dataset) -> datasets.Dataset:
    """Parse MathQA options format "a) val1 , b) val2 , ..." into a 5-element list.
    
    The options string uses comma-space as delimiter between choices. Using a simple
    `re.findall("[abcd] \\) .*?, |e \\) .*?$")` breaks on values containing commas
    (e.g. "a) foo, bar, baz , b) ..."). This version splits on `, ` only when
    followed by a letter+")" pattern, preserving commas inside values.
    """
    def _process_doc(doc):
        raw = doc["options"]
        # Split at ", " only when the next token is "letter )" (a) , b) , ...)
        parts = re.split(r"\s*,\s*(?=[a-e] \))", raw.strip())
        choices = []
        for p in parts:
            match = re.match(r"[a-e] \) (.+)", p.strip())
            if match:
                choices.append(match.group(1).rstrip(" ,"))
        # Ensure exactly 5 choices
        while len(choices) < 5:
            choices.append("")
        doc["choices"] = choices
        doc["choice_letters"] = ["A", "B", "C", "D", "E"]
        return doc

    return dataset.map(_process_doc)
