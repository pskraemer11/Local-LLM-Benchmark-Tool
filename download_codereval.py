#!/usr/bin/env python3
"""Download CoderEval4Python.json, extract self_contained/slib_runnable tasks,
   and convert to simple_evals format with robust test assertions.

   Output: simple_evals/codereval_selfcontained.jsonl
"""

import json, os, re, types, urllib.request

URL = "https://raw.githubusercontent.com/CoderEval/CoderEval/main/CoderEval4Python.json"
DEST = os.path.join(os.path.dirname(__file__), "simple_evals", "codereval_selfcontained.jsonl")

PARAM_RULES = [
    (r"^(n|count|size|num|int|index|port|q|max|min|limit|length|depth|max_results"
     r"|timeout|retry|attempts?)\b", 3),
    (r"^(lo|hi|low|high|threshold|eps|tol|rate|ratio|prob|score|val|value)\b", 42),
    (r"^(flo|percent|frac)\b", 0.5),
    (r"^(name|key|title|label|msg|text|prefix|suffix|sep|separator|delimiter)\b", "world"),
    (r"^(path|dir|folder|file|filename|glob)\b", "/tmp/test"),
    (r"^(url|uri|host|domain|endpoint)\b", "http://example.com"),
    (r"^(user|usr|username|login|author|owner)\b", "admin"),
    (r"^(pass|pwd|password|secret|token|api_key)\b", "secret123"),
    (r"^(email|mail)\b", "test@example.com"),
    (r"^(encoding|charset|lang|locale)\b", "utf-8"),
    (r"^(verb|verbose|debug|quiet|silent|flag|enable|disable)\b", True),
    (r"^(strip|flatten|recursive|overwrite|force|dry_run|follow_links)\b", False),
    (r"^(items|arr|list|seq|entries|elements|values|data|response|find_paths|input_list"
     r"|vertices)\b", [1, 2, 3]),
    (r"^(orderings)\b", [[1, 2], [3, 4]]),
    (r"^(points|coords|polygon)\b", [(0, 0), (1, 0), (1, 1)]),
    (r"^(script|cmd|command|code)\b", "echo hello"),
    (r"^(regex|pattern|expr|expression)\b", r"\d+"),
    (r"^(ignored)\b", "."),
    (r"^(node|element|obj|thing|item)\b", "test"),
    (r"^(pubdate_xpaths|xpaths)\b", [".//date"]),
    (r"^(method|vcs)\b", "test"),
    (r"^(default)\b", None),
]


def _guess_value(param_name):
    for regex, val in PARAM_RULES:
        if re.match(regex, param_name, re.IGNORECASE):
            if isinstance(val, list):
                return list(val)
            if isinstance(val, tuple):
                return tuple(val)
            if isinstance(val, dict):
                return dict(val)
            return val
    return f"test_{param_name}"


def _extract_imports(code):
    return "\n".join(
        line for line in code.strip().split("\n")
        if line.strip().startswith(("import ", "from "))
    )


def _extract_func_name(code):
    m = re.search(r"^def\s+(\w+)\s*\(", code.strip(), re.MULTILINE)
    return m.group(1) if m else None


def _extract_params(code):
    m = re.search(r"^def\s+\w+\s*\((.*)\)\s*:", code.strip(), re.MULTILINE)
    if not m:
        return []
    params_str = m.group(1).strip()
    if not params_str:
        return []
    params = []
    for p in params_str.split(","):
        p = p.strip()
        if not p or p in ("self", "cls"):
            continue
        name = p.split(":")[0].split("=")[0].strip()
        has_default = "=" in p
        params.append((name, has_default))
    return params


def _make_assertion_code(func_name, args, expected, is_generator=False):
    """Generate assertion code. If is_generator, wrap call in list()."""
    arg_reprs = [repr(a) for a in args]
    call = f"{func_name}({', '.join(arg_reprs)})"
    if is_generator:
        call = f"list({call})"

    # Basic types: == comparison
    if isinstance(expected, (type(None), bool, int, float, str)):
        return f"assert {call} == {repr(expected)}"

    # Sequences (list, tuple, set, frozenset)
    if isinstance(expected, (list, tuple, set, frozenset)):
        typename = type(expected).__name__
        lines = [f"_r = {call}"]
        lines.append(f"assert type(_r).__name__ == {repr(typename)}, "
                     f"f'type: got {{type(_r).__name__}}'")
        lines.append(f"assert len(_r) == {len(expected)}, "
                     f"f'len: {{len(_r)}} != {len(expected)}'")
        if len(expected) <= 20:
            try:
                eq_repr = repr(expected)
                lines.append(f"assert _r == {eq_repr}")
            except Exception:
                pass
        return "\n".join(lines)

    if isinstance(expected, dict):
        lines = [f"_r = {call}"]
        lines.append("assert type(_r).__name__ == 'dict', "
                     "f'type: got {type(_r).__name__}'")
        lines.append(f"assert len(_r) == {len(expected)}, "
                     f"f'len: {{len(_r)}} != {len(expected)}'")
        if len(expected) <= 10:
            try:
                eq_repr = repr(expected)
                lines.append(f"assert _r == {eq_repr}")
            except Exception:
                pass
        return "\n".join(lines)

    # Function -> decorator, skip
    if isinstance(expected, types.FunctionType):
        return None  # signal: can't test

    # Fallback
    try:
        er = repr(expected)
        if len(er) <= 500:
            return f"assert {call} == {er}"
    except Exception:
        pass

    return f"assert type({call}).__name__ == {repr(type(expected).__name__)}"


def _is_blocked(code):
    blocked_modules = ["subprocess", "socket", "ctypes", "multiprocessing", "threading"]
    for mod in blocked_modules:
        if re.search(rf"^\s*(import\s+{mod}|from\s+{mod}\s)", code, re.MULTILINE):
            return f"blocked module: {mod}"
    if re.search(r"def\s+\w+\(.*\*", code):
        return "has *args/**kwargs"
    return None


def _check_deps(imp):
    for line in imp.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(?:from\s+(\w+)|import\s+(\w+))", line)
        if m:
            mod = m.group(1) or m.group(2)
            try:
                __import__(mod)
            except ImportError:
                return False
    return True


def download():
    print(f"[INFO] Download {URL} ...")
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    print(f"[OK] {len(data['RECORDS'])} Eintraege geladen")
    return data["RECORDS"]


def main():
    records = download()
    self_contained = [r for r in records
                      if r.get("level", "") in ("self_contained", "slib_runnable")]
    print(f"[INFO] self_contained + slib_runnable: {len(self_contained)} von {len(records)}")

    converted = 0
    skipped = 0
    skip_reasons = {}

    os.makedirs(os.path.dirname(DEST), exist_ok=True)

    with open(DEST, "w", encoding="utf-8") as out:
        for task in self_contained:
            code = task.get("code", "")

            reason = _is_blocked(code)
            if reason:
                skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
                skipped += 1
                continue

            entry_point = _extract_func_name(code)
            params = _extract_params(code)
            if not entry_point or not params:
                skip_reasons["no params/entry_point"] = skip_reasons.get("no params/entry_point", 0) + 1
                skipped += 1
                continue

            imports = _extract_imports(code)
            if not _check_deps(imports):
                skip_reasons["missing dependency"] = skip_reasons.get("missing dependency", 0) + 1
                skipped += 1
                continue

            ns = {}
            try:
                if imports:
                    exec(imports, ns)
                exec(code, ns)
            except Exception as e:
                skip_reasons[f"exec fail: {e}"] = skip_reasons.get("exec fail", 0) + 1
                skipped += 1
                continue

            func = ns.get(entry_point)
            if not func:
                skip_reasons["func not found"] = skip_reasons.get("func not found", 0) + 1
                skipped += 1
                continue

            # Generate 1-2 argument sets
            base = [_guess_value(p[0]) for p in params]
            arg_sets = [base]

            if len(params) > 1 or all(p[1] for p in params):
                alt = [_guess_value(p[0]) for p in params]
                for i in range(min(3, len(alt))):
                    v = alt[i]
                    if isinstance(v, int):
                        alt[i] = v + 10
                    elif isinstance(v, str):
                        alt[i] = v + "_alt"
                    elif isinstance(v, bool):
                        alt[i] = not v
                    elif isinstance(v, list):
                        alt[i] = v + [99]
                if alt != base:
                    arg_sets.append(alt)

            # Execute and build assertions
            assertions = []
            skip_task = False
            for args in arg_sets:
                try:
                    result = func(*args)
                    is_gen = isinstance(result, types.GeneratorType)
                    if is_gen:
                        result = list(result)
                except Exception as e:
                    skip_reasons[f"exec fail: {e}"] = skip_reasons.get("exec fail", 0) + 1
                    skip_task = True
                    skipped += 1
                    break

                assertion = _make_assertion_code(entry_point, args, result, is_generator=is_gen)
                if assertion is None:
                    skip_reasons["returns function (decorator)"] = skip_reasons.get("returns function (decorator)", 0) + 1
                    skip_task = True
                    skipped += 1
                    break
                assertions.append(assertion)

            if skip_task:
                continue

            prompt = (task.get("human_label", "") or task.get("docstring", "") or "").strip()
            if not prompt:
                prompt = f"Implement the function `{entry_point}`."
            if not prompt.endswith("."):
                prompt += "."

            record = {
                "prompt": prompt,
                "entry_point": entry_point,
                "canonical_solution": code,
                "setup_code": imports,
                "tests": assertions,
                "type": "codereval",
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            converted += 1
            print(f"  [{converted:>2}] {entry_point} ({len(arg_sets)} assertion(s))")

    print(f"\n[OK] Konvertiert: {converted}")
    print(f"[SKIP] Uebersprungen: {skipped}")
    for reason, count in sorted(skip_reasons.items(), key=lambda x: -x[1]):
        print(f"  - {reason}: {count}")
    print(f"[OUT] {DEST}")


if __name__ == "__main__":
    main()
