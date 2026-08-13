"""CRIT-2 — the MSPDI upload path refuses XXE and billion-laughs, at OUR layer.

Aikido flagged `massingplan/core/mspdi.py:170` (`ElementTree.fromstring`) and instructed us to swap
defusedxml into that file. **That instruction was wrong for this repo**, and following it would have
cost more than the bug:

* the file is VENDORED verbatim from MassingCloud/massingplan at `b703dca4`;
* its `core` is stdlib-only *by contract* — that is the property the whole adoption rests on;
* editing a vendored copy makes it a fork, and every future re-sync becomes a merge.

Upstream had already reasoned it out, in a comment right beside the call: *"`defusedxml` would be the
safer parser for untrusted input, but `core` is pure stdlib by contract so the application layer is
where an untrusted upload gets hardened."* They did their half. **`schedule_import.py` is that
application layer and had not done its half** — it fed uploaded text straight into `read_mspdi`.
The gap was ours, not theirs, and the scanner attributed it to the wrong file.

So the hardening lives at the call site and the vendored tree is byte-identical to upstream.

**What the mutation showed, and it sharpens the claim.** With the hardening removed, the
billion-laughs payload was ACCEPTED while the XXE payload was still refused — Python's stdlib
ElementTree does not fetch external entities, but it does expand internal ones. So the live,
reachable risk on this path was **entity-expansion DoS, not file disclosure**. The fix is right
either way, and "we closed an XXE file read" would have been an overclaim. Both payloads stay in the
suite: the XXE case guards the behaviour we currently get for free, which is exactly the kind of
thing a runtime upgrade can quietly remove.

**Both directions are asserted.** A parser that refuses everything would satisfy every attack case
below and break every real import — so the honest-document case is a first-class assertion, not a
footnote.
"""
from __future__ import annotations

import sys

from aec_api.schedule_import import parse_full

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


# --- the attacks ----------------------------------------------------------------------------------
# Classic XXE: an external entity pointing at a local file. If the parser resolves it, the file's
# contents land in the imported schedule — and on a server, `file:///etc/passwd` is the polite demo.
XXE = """<?xml version="1.0"?>
<!DOCTYPE Project [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<Project xmlns="http://schemas.microsoft.com/project">
  <Name>&xxe;</Name>
  <Tasks><Task><UID>1</UID><Name>A</Name></Task></Tasks>
</Project>"""

# Billion laughs: nested entity expansion. No external fetch at all, so a fix that only blocked
# network access would still fall over here. This is why "blocks XXE" and "blocks entity expansion"
# are two claims, not one.
BILLION = """<?xml version="1.0"?>
<!DOCTYPE Project [
 <!ENTITY a "aaaaaaaaaa">
 <!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">
 <!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">
 <!ENTITY d "&c;&c;&c;&c;&c;&c;&c;&c;&c;&c;">
]>
<Project xmlns="http://schemas.microsoft.com/project">
  <Name>&d;</Name>
  <Tasks><Task><UID>1</UID><Name>A</Name></Task></Tasks>
</Project>"""

# An ordinary, honest MSPDI document — the twin.
HONEST = """<?xml version="1.0" encoding="UTF-8"?>
<Project xmlns="http://schemas.microsoft.com/project">
  <Name>Riverside</Name>
  <Tasks>
    <Task><UID>1</UID><ID>1</ID><Name>Mobilise</Name><Duration>PT40H0M0S</Duration></Task>
    <Task><UID>2</UID><ID>2</ID><Name>Excavate</Name><Duration>PT80H0M0S</Duration></Task>
  </Tasks>
</Project>"""

for label, payload in (("XXE external entity", XXE), ("billion laughs", BILLION)):
    try:
        parse_full(payload)
        refused, why = False, "it was ACCEPTED"
    except Exception as exc:  # noqa: BLE001 — any refusal is a pass; the point is that it stops
        refused, why = True, f"{type(exc).__name__}"
    check(f"an MSPDI upload carrying {label} is refused", refused, why)

# --- the twin: a real document must still import ---------------------------------------------------
try:
    result = parse_full(HONEST)
    ok = result is not None
    detail = f"imported, type={type(result).__name__}"
except Exception as exc:  # noqa: BLE001
    ok, detail = False, f"{type(exc).__name__}: {exc}"
check("an ordinary MSPDI document still imports — the parser refuses attacks, not everything", ok,
      detail)

# --- the vendored file must NOT have been edited ----------------------------------------------------
# The whole point of fixing this at the call site. If someone later "fixes" the vendored copy, this
# is the check that says so — and it is asserted on content, not on a promise in a comment.
import ast  # noqa: E402
import pathlib  # noqa: E402

vendored = pathlib.Path(__file__).parent / "src" / "massingplan" / "core" / "mspdi.py"
tree = ast.parse(vendored.read_text(encoding="utf-8"))

# Asserted over the AST, not over the text. A substring search for "defusedxml" FAILS on the
# unforked file, because upstream's own comment says "`defusedxml` would be the safer parser…" —
# the gate would flag the very documentation that explains the design. This repo has hit that
# shape before; an AST cannot see a comment, so the question it answers is the one being asked.
imports = {
    n.module.split(".")[0] if isinstance(n, ast.ImportFrom) and n.module else
    (n.names[0].name.split(".")[0] if isinstance(n, ast.Import) else "")
    for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
}
check("the vendored mspdi.py imports NO defusedxml — it was not forked",
      "defusedxml" not in imports,
      "if this fails someone edited a vendored file; harden the caller instead")
check("...and still uses the stdlib parser it is supposed to",
      "xml" in imports or any("ElementTree" in ast.dump(n) for n in ast.walk(tree)),
      "the twin — an empty/renamed file would pass the check above on its own")

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_mspdi_xxe OK")
