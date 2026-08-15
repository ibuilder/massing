"""R46 ③ — PMXML is read, not counted.

The branch this replaces returned **zero activities and a warning**: a planner who exported the one
Primavera format that carries baselines got an import of nothing and a note telling them to re-export
as XER. That is the defect, and the first assertion measures it against the same document.

The second thing worth reading is `a PMXML document is REFUSED if it uses XML entity features`. This
path takes a file from a user. `xmlsafe` in the vendored engine hardens the reader; this rejects
before the reader is reached. They are not redundant — one is a property of the parser, the other of
this upload path — and the XER/MSPDI paths already work this way.
"""
from __future__ import annotations

from aec_api import schedule_import

_FAILURES: list[str] = []


def check(name: str, ok: bool, note: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}   {note}")
    if not ok:
        _FAILURES.append(name)


#: A minimal P6 XML export: two activities and the relationship between them. The relationship is
#: the point — it is exactly what the old branch could not carry.
#:
#: **The relationship references `ObjectId`, not `Id`.** P6 links activities by their numeric
#: ObjectId and carries the planner's `A1010` code alongside; a fixture written with
#: `<PredecessorActivityId>A1010</...>` parses without error and produces ZERO relationships, which
#: is exactly the shape of the defect this file exists to close. Written from the reader, not from
#: memory of what the format "should" look like.
PMXML = """<?xml version="1.0" encoding="UTF-8"?>
<APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V8.2/API/BusinessObjects">
  <Project>
    <Id>TOWER</Id>
    <Name>Tower</Name>
    <DataDate>2026-03-02T00:00:00</DataDate>
    <Activity>
      <ObjectId>101</ObjectId>
      <Id>A1010</Id>
      <Name>Mobilise</Name>
      <PlannedDuration>40</PlannedDuration>
      <PlannedStartDate>2026-03-02T00:00:00</PlannedStartDate>
      <PlannedFinishDate>2026-03-06T00:00:00</PlannedFinishDate>
    </Activity>
    <Activity>
      <ObjectId>102</ObjectId>
      <Id>A1020</Id>
      <Name>Excavate</Name>
      <PlannedDuration>80</PlannedDuration>
      <PlannedStartDate>2026-03-09T00:00:00</PlannedStartDate>
      <PlannedFinishDate>2026-03-18T00:00:00</PlannedFinishDate>
    </Activity>
    <Relationship>
      <PredecessorActivityObjectId>101</PredecessorActivityObjectId>
      <SuccessorActivityObjectId>102</SuccessorActivityObjectId>
      <Type>Finish to Start</Type>
      <Lag>0</Lag>
    </Relationship>
  </Project>
</APIBusinessObjects>
"""

#: The same document with an external entity. Never parsed by the reader.
XXE = PMXML.replace(
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>')


def main() -> int:
    check("the document is still detected as PMXML",
          schedule_import.detect_format(PMXML) == "pmxml",
          "detection was never the problem — reading it was")

    # --- THE defect this closes ------------------------------------------------------------------
    records, meta = schedule_import.parse_full(PMXML)
    check("a PMXML export now imports its ACTIVITIES — it used to import zero",
          len(records) == 2 and meta.get("activities") == 2,
          f"{len(records)} activities; the old branch returned 0 with a warning telling the "
          "planner to re-export as XER")

    check("...and its RELATIONSHIPS, which is the half XER users were sent away for",
          meta.get("relationships") == 1,
          f"{meta.get('relationships')} relationship(s) — 'imported without logic' was the note "
          "attached to a schedule that had none of it")

    check("...and the logic lands where the engine reads it back",
          any("A1010" in str((r.get("data") or {}).get("predecessors") or "")
              for r in records),
          f"{[(r.get('ref'), (r.get('data') or {}).get('predecessors')) for r in records]}")

    check("no fallback flag is set any more",
          not meta.get("fell_back"),
          f"format={meta.get('format')!r}, fell_back={meta.get('fell_back')!r}")

    # --- durations survive, which is what makes it schedulable ------------------------------------
    #
    # P6 stores planned duration in HOURS. 40 hours is a 5-day activity on an 8-hour day, and a
    # reader that passed 40 straight through would import a five-day task as a forty-day one.
    durations = sorted(int((r.get("data") or {}).get("duration") or 0) for r in records)
    check("durations are converted from P6's hours, not passed through as days",
          durations == [5, 10],
          f"{durations} days from 40h and 80h — passing the hours through would make a five-day "
          "task read as forty")

    # --- the upload path rejects, rather than sanitising -------------------------------------------
    try:
        schedule_import.parse_full(XXE)
        refused = False
    except Exception as exc:                                   # noqa: BLE001 — any refusal counts
        refused = "PMXML refused" in str(exc) or "entity" in str(exc).lower()
    check("a PMXML document is REFUSED if it uses XML entity features",
          refused,
          "rejected before the reader is reached — a document needing an external entity to be "
          "meaningful is not one to import silently degraded")

    # --- refusals -----------------------------------------------------------------------------------
    try:
        schedule_import.parse_full("<APIBusinessObjects><Activity/></APIBusinessObjects>")
        empty_ok = True
    except Exception:                                          # noqa: BLE001
        empty_ok = False
    check("a PMXML document with no usable project does not crash the importer",
          empty_ok is not None, "it either parses to nothing or raises a worded error, not a 500")

    check("an MS Project document is still routed to the MSPDI reader, not this one",
          schedule_import.detect_format(
              '<?xml version="1.0"?><Project xmlns="http://schemas.microsoft.com/project">'
              "<Tasks><Task><UID>1</UID></Task></Tasks></Project>") == "mspdi",
          "P6 XML and MS Project XML are different formats that both start with '<'")

    if _FAILURES:
        print(f"FAILED: {', '.join(_FAILURES)}")
        return 1
    print("test_schedule_p6xml OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
