import re

import datasets


def process_docs(dataset: datasets.Dataset) -> datasets.Dataset:
    def _process_doc(doc):
        choices = [c[4:].rstrip(" ,") for c in re.findall(r"[abcd] \) .*?, |e \) .*?$", doc["options"])]
        doc["choices"] = choices
        doc["choice_letters"] = ["A", "B", "C", "D", "E"]
        return doc

    return dataset.map(_process_doc)
