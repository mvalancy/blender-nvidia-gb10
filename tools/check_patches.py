#!/usr/bin/env python3
"""
Structural validation for the Blender build patches.

These cannot be applied here — that needs a Blender source tree and an hour of
build time on a GB10. What can be checked is that each file is a well-formed
git patch, because the failure this guards against is silent and expensive:
a truncated or mangled patch fails partway through `setup.sh --force patch`
after the reader has already spent time on the earlier steps.

Checks per patch:
  * a `From <sha>` header, i.e. it really is git format-patch output
  * at least one `@@` hunk
  * matching `---` / `+++` file headers
  * every hunk header parses, and its line counts match the hunk body
"""
import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def check(path: pathlib.Path, verbose: bool) -> list[str]:
    problems: list[str] = []
    lines = path.read_text(errors="replace").split("\n")

    if not lines or not lines[0].startswith("From "):
        problems.append("no 'From <sha>' header — not git format-patch output")

    hunks = [i for i, l in enumerate(lines) if HUNK.match(l)]
    if not hunks:
        problems.append("no @@ hunks")

    minus = sum(1 for l in lines if l.startswith("--- "))
    plus = sum(1 for l in lines if l.startswith("+++ "))
    if minus != plus:
        problems.append(f"unbalanced file headers: {minus} '---' vs {plus} '+++'")

    for i in hunks:
        m = HUNK.match(lines[i])
        old_n = int(m.group(2) or 1)
        new_n = int(m.group(4) or 1)
        old_seen = new_seen = 0
        for l in lines[i + 1:]:
            if l.startswith("@@") or l.startswith("diff --git") or l.startswith("-- "):
                break
            if l.startswith("-"):
                old_seen += 1
            elif l.startswith("+"):
                new_seen += 1
            elif l.startswith(" ") or l == "":
                old_seen += 1
                new_seen += 1
            else:
                break
        if old_seen < old_n or new_seen < new_n:
            problems.append(
                f"hunk at line {i + 1} claims -{old_n}/+{new_n} "
                f"but body has {old_seen}/{new_seen} — patch looks truncated"
            )

    if verbose and not problems:
        print(f"  ok {path.name}: {len(hunks)} hunk(s), {plus} file header(s)")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    patches = sorted((ROOT / "patches").glob("*.patch"))
    if not patches:
        print("no patches found — nothing to validate", file=sys.stderr)
        return 1

    failed = 0
    for p in patches:
        problems = check(p, args.verbose)
        if problems:
            failed += 1
            print(f"FAIL {p.name}")
            for problem in problems:
                print(f"     {problem}")

    print(f"{len(patches)} patches checked, {failed} malformed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
