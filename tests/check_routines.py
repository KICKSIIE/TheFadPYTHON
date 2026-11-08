"""Static cross-check (no database needed): every routine the Python code calls must be defined in
sql/*.sql (or be one of the routines that already existed in your database) with a matching number
of arguments. Run:  python tests/check_routines.py"""
import ast
import glob
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
# routines that already exist in the THEFAD database (from your stored-routines activity): name -> (min, max)
EXISTING = {"sp_create_discount": (7, 7), "sp_update_discount": (7, 7), "fn_refund_report": (2, 2)}


def split_top(s):
    parts, depth, cur = [], 0, ""
    for ch in s:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return parts


def sql_routines():
    found = {}
    text = "\n".join(open(f).read() for f in sorted(glob.glob(os.path.join(ROOT, "sql", "0*.sql"))))
    for m in re.finditer(r"CREATE OR REPLACE (FUNCTION|PROCEDURE)\s+thefad\.(\w+)\s*\((.*?)\)\s*(?:RETURNS|LANGUAGE|AS)\b",
                         text, re.S | re.I):
        kind, name, params = m.groups()
        plist = split_top(params)
        total = len(plist)
        required = sum(1 for p in plist if " DEFAULT " not in p.upper())
        found[name] = (kind.upper(), required, total)
    return found


def python_calls():
    calls = []
    files = glob.glob(os.path.join(ROOT, "**", "*.py"), recursive=True)
    for f in files:
        rel = os.path.relpath(f, ROOT).replace("\\", "/")
        if rel.startswith("tests/") or rel.startswith(".venv"):
            continue
        tree = ast.parse(open(f).read())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("call_function", "call_procedure")
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                calls.append((os.path.relpath(f, ROOT), node.lineno, node.func.attr, node.args[0].value,
                              len(node.args) - 1))
    return calls


def main():
    defined, problems, seen = sql_routines(), [], set()
    for path, line, how, name, argc in python_calls():
        seen.add(name)
        if name in EXISTING:
            lo, hi = EXISTING[name]
        elif name in defined:
            kind, lo, hi = defined[name]
            if (how == "call_procedure") != (kind == "PROCEDURE"):
                problems.append(f"{path}:{line} {name} is a {kind} but called with {how}")
        else:
            problems.append(f"{path}:{line} {name} is not defined in sql/")
            continue
        if not lo <= argc <= hi:
            problems.append(f"{path}:{line} {name} called with {argc} args, SQL takes {lo}..{hi}")
    unused = sorted(set(defined) - seen)
    print(f"{len(seen)} routines called from Python, {len(defined)} defined in sql/.")
    if unused:
        print("defined but not called from Python (fine for helpers):", ", ".join(unused))
    for p in problems:
        print("PROBLEM:", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
