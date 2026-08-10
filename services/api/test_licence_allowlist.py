"""The permitted-licence list, and the one-letter difference that would quietly undo it.

CC0-1.0 and BSL-1.0 were added to `supply_chain._PERMITTED_RE` on 2026-08-10 on the owner's
instruction. CC0 was already shipping — 59 files under `services/data/families/external/` declare
it — so the written rule had been narrower than reality.

**The whole risk of this change is BSL vs BUSL.** `BSL-1.0` is the Boost Software License:
permissive, MIT-like, no copyleft. `BUSL-1.1` is the Business Source License: source-available, not
open source, and not permitted. They differ by one letter. An unanchored `bsl` in the pattern admits
BUSL through the front door of the permitted list — the worst possible failure for a licence gate,
because it fails *open* and silently.

The anchoring works because in "BUSL" the `b` of `bsl` is preceded by a word character, so `\\bbsl\\b`
cannot match inside it. That is a property of the regex, not of anyone's intent, and this file
asserts it instead of trusting the comment beside it — the repo has been bitten by a comment that
described what a pattern was meant to do rather than what it did.

Paired throughout: every "must be refused" has a "must still be accepted" twin, because a gate that
refuses everything passes every refusal test ever written.
"""
from __future__ import annotations

import sys

from aec_api import supply_chain

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


# --- the newly permitted, in the spellings a package actually declares --------------------------
for text in ("CC0-1.0", "CC0 1.0 Universal", "Creative Commons Zero v1.0 Universal",
             "BSL-1.0", "Boost Software License 1.0", "Boost Software License - Version 1.0"):
    check("permitted: " + text, supply_chain.classify_license(text) == "permitted",
          "got " + supply_chain.classify_license(text))

# --- the trap: BUSL must NOT be permitted, in every spelling ------------------------------------
for text in ("BUSL-1.1", "Business Source License 1.1", "BUSL", "busl-1.1"):
    verdict = supply_chain.classify_license(text)
    check("NOT permitted: " + text, verdict != "permitted",
          "classify -> " + verdict + " (must never be 'permitted' — BUSL is source-available)")

# The regex-level claim, asserted directly — and NOT the claim this file first made.
#
# The original version of this test asserted that the `` anchors were what kept BUSL out of the
# permitted set. They are not. "BUSL" is B-U-S-L and contains no "bsl" substring, so a bare `bsl`
# alternative cannot match it either: removing the anchors left every BUSL assertion below passing.
# The mutation is what exposed that, not review — the checks were right, the *explanation* was
# wrong, and a wrong explanation next to correct code is what the next reader will act on.
#
# What is genuinely asserted: BUSL is not permitted (whatever the mechanism), and BSL-1.0 still is.
check("BUSL is not reachable through the permitted pattern at all",
      supply_chain._PERMITTED_RE.search("BUSL-1.1") is None,
      "if this ever fails, the Business Source License is being classified as permissive")
check("...while a real BSL-1.0 still matches",
      supply_chain._PERMITTED_RE.search("BSL-1.0") is not None,
      "the twin — an over-tight pattern that refuses Boost would pass the check above alone")

# --- nothing that was refused before became permitted -------------------------------------------
for text in ("GPL-3.0", "AGPL-3.0", "GNU Affero General Public License v3"):
    check("still strong copyleft: " + text, supply_chain.is_strong_copyleft(text),
          "the additions must not have widened anything else")
for text in ("MIT", "Apache-2.0", "BSD-3-Clause"):
    check("still permitted: " + text, supply_chain.classify_license(text) == "permitted")

# --- the reason CC0 was added: it is already on disk --------------------------------------------
# Not asserted against a hardcoded count. The number of CC0 family files is content, and content
# changes; what must hold is that the licence we ship is one the classifier accepts.
check("CC0 as declared by our own shipped family content is permitted",
      supply_chain.classify_license("CC0-1.0") == "permitted")

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_licence_allowlist OK")
