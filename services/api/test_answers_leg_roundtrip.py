"""R22-PROVENANCE — the ANSWERS leg fills itself, end to end.

v0.3.975 gave the leg somewhere to live. It stayed empty on every real project, because the only
thing that produces a cited answer never filed one — so `admissible` was reachable in principle and
unreachable in practice, which is a subtler version of the same defect.

**The assertion that carries this file is the ROUND TRIP**: ask a question, and the provenance report
for that project counts the answer. Both halves have their own tests; neither can see the seam
between them, and the seam is where a mapping quietly loses everything (`answer` vs `text`,
`{"data": ...}` vs a flat field map — the second inserts a record with every field empty and does not
raise).

**One producer, deliberately.** The roadmap said `decision_gate`, `persona_answer` and `rfi_qa`
answer. Reading them says otherwise: `decision_gate.evaluate` consumes a cited answer as evidence and
`persona_answer.shape` re-renders one for a reader. Only `rfi_qa` calls `cited_answer.build`. Wiring
all three would have filed one answer three times under three engine names — and a provenance report
is a count, so that is worse than not filing at all. This file asserts the population, not just the
behaviour.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_answers_leg_roundtrip.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, "src")
# `DATABASE_URL`, not `AEC_DB_URL` — the first version of this file used the wrong name, so it
# silently wrote to the shared ./aec.db instead of an isolated file. Every assertion still
# passed; it was a UNIQUE-constraint collision on the SECOND run that gave it away. A test
# that claims isolation and does not have it poisons whatever runs beside it.
os.environ["DATABASE_URL"] = "sqlite:///./test_answers_leg.db"
os.environ["STORAGE_DIR"] = "./test_storage_answers"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_answers_leg.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import modules as me  # noqa: E402
from aec_api import modules_registry as mr  # noqa: E402
from aec_api import provenance_report as pr  # noqa: E402

mr.load_registry()

from aec_api.db import Base, SessionLocal, engine  # noqa: E402
from aec_api.models import Project  # noqa: E402

Base.metadata.create_all(engine)

_FAILURES: list[str] = []


def check(name: str, ok: bool, note: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}   {note}")
    if not ok:
        _FAILURES.append(name)


#: What `cited_answer.build` returns, in the shape `record_answer` consumes. Two claims: one cited,
#: one not. The uncited one is the point — it must survive filing.
CITED = {
    "claims": [
        {"text": "Type X gypsum, 5/8 in, per 09 29 00",
         "citations": [{"source_type": "document", "document_id": "SPEC-092900", "page": 4,
                        "revision": "C"}]},
        {"text": "No fire rating is called out at this location", "citations": []},
    ],
}


def main() -> int:
    with SessionLocal() as db:
        db.add(Project(id="ans1", name="Answers"))
        db.commit()

        # ================= THE ROUND TRIP =================
        out = pr.record_answer(db, "ans1", "What board is called for?", CITED, engine="rfi_qa")
        check("an answer files to the register",
              out.get("recorded") is True and out.get("filed") == 2,
              f"{out} — two claims, two records")

        rep = pr.from_project(db, "ans1")
        answers = next(x for x in rep["legs"] if x["leg"] == "answers")
        check("...and the provenance report COUNTS it — the round trip",
              answers["counted"] == 2,
              f'{answers} — this is the seam neither side\'s own test can see. `answer` vs `text`, '
              'or a flat field map where create_record reads body["data"], both lose everything '
              "here without raising")

        check("...naming the uncited claim, which is the whole job",
              answers["uncited_count"] == 1
              and answers["uncited"] == ["No fire rating is called out at this location"],
              f'{answers.get("uncited")} — an answer nobody cited is exactly what this report exists '
              "to surface; dropping it at filing time would improve every report by hiding it")

        check("the citation survives the write with its page and revision",
              (rows := me.list_records(db, "answer_record", "ans1", limit=10))
              and any((c.get("page") == 4 and c.get("revision") == "C")
                      for r in rows for c in ((r.get("data") or {}).get("citations") or [])),
              "a citation stored without its page reads back as one nobody can open")

        # ================= REFUSALS, AS DATA =================
        empty = pr.record_answer(db, "ans1", "q", {"claims": []})
        check("an answer with no claims is not filed, and says so rather than raising",
              empty.get("recorded") is False and "nothing to file" in empty.get("reason", ""),
              f"{empty} — recording must never be able to break answering")

        check("...and nothing was written for it",
              len(me.list_records(db, "answer_record", "ans1", limit=100)) == 2,
              "a refusal that still writes is worse than one that raises")

        # ================= the citation key mapping =================
        #
        # `cited_answer` emits `guid` for an IFC cite and `rule_id` for a rule; the register's table
        # declares `document_id`. A module `table` field keeps the columns it knows and DROPS the
        # rest, so an unmapped key does not raise — it stores a citation with nothing to open.
        check("an IFC citation's `guid` maps onto the register's document column",
              pr.citation_row({"source_type": "ifc", "guid": "3kJf9"})
              == {"source_type": "ifc", "document_id": "3kJf9"},
              f'{pr.citation_row({"source_type": "ifc", "guid": "3kJf9"})}')

        check("...and a rule citation's `rule_id` does too",
              pr.citation_row({"source_type": "rule", "rule_id": "IBC-1011.5"})
              == {"source_type": "rule", "document_id": "IBC-1011.5"},
              "same column, because both are the thing a reader would open")

        check("...while a key the register does not declare is dropped, not invented",
              "nonsense" not in pr.citation_row({"source_type": "document", "nonsense": "x"}),
              "the table field would drop it anyway; doing it here makes it visible")

    # ================= ONE PRODUCER, asserted from the tree =================
    src = Path(__file__).resolve().parent / "src" / "aec_api"
    producers = sorted(p.name for p in src.glob("*.py")
                       if "cited_answer" in (t := p.read_text(encoding="utf-8"))
                       and ("ca.build(" in t or "cited_answer.build(" in t))
    check("exactly one module BUILDS a cited answer, and it is the one that records",
          producers == ["rfi_qa.py"],
          f"{producers} — `decision_gate` consumes one as evidence and `persona_answer` re-renders "
          "one. Recording in all three would file one answer three times, and a provenance report "
          "is a count")

    recorders = sorted(p.name for p in src.glob("*.py")
                       if "record_answer(" in p.read_text(encoding="utf-8")
                       and p.name != "provenance_report.py")
    check("...and exactly one module CALLS record_answer — the twin",
          recorders == ["rfi_qa.py"],
          f"{recorders} — if this ever names two, the leg is double-counting and the report reads "
          "better than the project is")

    if _FAILURES:
        print(f"FAILED: {', '.join(_FAILURES)}")
        return 1
    print("answers_leg_roundtrip: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
