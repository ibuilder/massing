"""R22-ROUTINES — due work actually gets enqueued, and the same window never fires twice.

`routines.due()` already decides correctly and refuses well; `jobs.enqueue` already rejects an
unregistered kind; `worker.py` already runs the queue. **Nothing joined them** — both `/routines/due`
endpoints are read-only, so "what should run now" was computed, returned and dropped. That is the
entry's own complaint: a tool you remember to use rather than infrastructure.

**The defect worth the test is the one that was latent.** `routines.from_project(db, pid, now,
in_flight)` takes `in_flight` as a parameter and **no caller supplied it**, so the one refusal in the
chain that needs outside knowledge — "the previous run has not finished" — could never fire. With the
default empty set a monthly report that takes an hour is re-enqueued on every sweep for that hour.

So these run against a real session and the real `jobs.enqueue`, not a stub: the join is the subject,
and a fake queue would agree with whatever I wrote.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_routines_run.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_routines_run.db"
os.environ["STORAGE_DIR"] = "./test_storage_routines_run"
for _f in ("./test_routines_run.db",):
    if os.path.exists(_f):
        os.remove(_f)

sys.path.insert(0, "src")

from datetime import datetime, timezone  # noqa: E402

from aec_api import jobs, modules_registry, routines_run  # noqa: E402
from aec_api import modules as me  # noqa: E402
from aec_api.db import Base, SessionLocal, engine  # noqa: E402
from aec_api.models import Job, Project  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


# The register must be loaded explicitly outside the app lifespan. Skipping this is the same trap as
# a TestClient built outside a `with` block: every module reads as absent and the failure looks like a
# missing feature rather than an unstarted registry.
modules_registry.load_registry()
Base.metadata.create_all(engine)
db = SessionLocal()
PID = "p-routines"
db.add(Project(id=PID, name="Routines")); db.commit()

# `echo` is a registered kind; `not_a_kind` is not. Both are needed: the refusal only means something
# if a real kind succeeds beside it in the same sweep.
check("the queue really registers `echo`, so a success here is not vacuous", "echo" in jobs.KINDS,
      sorted(jobs.KINDS))


def routine(name, kind, cadence="daily", state="active", last_run=None, **extra):
    """Create a routine in a given workflow state.

    `create_record` files new records as **draft**, and `from_project` deliberately evaluates only
    `active` ones — draft was never switched on, retired was switched off. So the state has to be set
    explicitly here; a test that skipped it would assert on routines the scheduler correctly ignores
    and prove nothing.
    """
    rec = me.create_record(db, "routine", PID,
                           {"data": {"name": name, "kind": kind, "cadence": cadence,
                                     **({"last_run": last_run} if last_run else {}), **extra}},
                           "tester", None)
    rid = rec["id"]
    t = me.TABLES["routine"]          # a Core Table, so columns are t.c.*, not attributes
    db.execute(t.update().where(t.c.id == rid).values(workflow_state=state))
    db.commit()
    return rid


NOW = datetime(2026, 8, 7, 9, 0, tzinfo=timezone.utc)

r_ok = routine("Nightly model CI", "echo")
r_bad = routine("Broken", "not_a_kind")
r_draft = routine("Never switched on", "echo", state="draft")

# --- 1. THE JOIN: due work becomes queued work ----------------------------------------------------
# Called inside a guard on purpose. If a misconfigured routine aborts the sweep, `run_due` raises and
# every check below would die with a traceback instead of one named failure — a gate that crashes
# still gates, but it stops saying WHAT is wrong. This turns that case into a named FAIL.
try:
    out = routines_run.run_due(db, PID, now=NOW, actor="test")
    _raised = None
except Exception as _e:                                    # noqa: BLE001
    out, _raised = {"enqueued": [], "enqueued_count": 0, "refused": [], "note": "",
                    "in_flight_kinds": []}, _e
check("THE SWEEP SURVIVES A MISCONFIGURED ROUTINE — it must not raise out of run_due",
      _raised is None, repr(_raised))
check("a due routine is ENQUEUED, not merely reported as due",
      [e["routine_id"] for e in out["enqueued"]] == [r_ok], out["enqueued"])
check("  and a real job row exists for it",
      db.query(Job).filter(Job.id == out["enqueued"][0]["job_id"]).one().state == "queued")
check("  carrying the routine and window it came from, so the job is traceable",
      (db.query(Job).filter(Job.id == out["enqueued"][0]["job_id"]).one().params or {}
       ).get("routine_id") == r_ok)

# --- 2. AN UNKNOWN KIND IS REPORTED, NOT FATAL ----------------------------------------------------
check("THE MISCONFIGURED ROUTINE DID NOT ABORT THE SWEEP — the good one still ran",
      out["enqueued_count"] == 1 and any(f["routine_id"] == r_bad for f in out["refused"]),
      (out["enqueued_count"], out["refused"]))
check("  and it is refused by name with the registered kinds listed",
      out["refused"][0]["status"] == routines_run.STATUS_UNKNOWN_KIND
      and "not_a_kind" in out["refused"][0]["reason"], out["refused"])
check("a draft routine is never fired", all(e["routine_id"] != r_draft for e in out["enqueued"]))

# --- 3. THE SAME WINDOW DOES NOT FIRE TWICE -------------------------------------------------------
again = routines_run.run_due(db, PID, now=NOW, actor="test")
check("A SECOND SWEEP IN THE SAME WINDOW ENQUEUES NOTHING — the window was consumed at enqueue",
      again["enqueued_count"] == 0, again["enqueued"])
check("  and the queue did not grow",
      db.query(Job).filter(Job.project_id == PID, Job.kind == "echo").count() == 1)

# --- 4. THE LATENT ONE: in_flight is DERIVED, so unfinished work blocks the next fire --------------
# Move to the next window so the routine is due again, but leave its job unfinished.
NEXT = datetime(2026, 8, 8, 9, 0, tzinfo=timezone.utc)
busy = routines_run.in_flight_kinds(db, PID)
check("in-flight kinds are read from the JOBS TABLE, not assumed empty", "echo" in busy, busy)

third = routines_run.run_due(db, PID, now=NEXT, actor="test")
check("A ROUTINE WHOSE PREVIOUS JOB IS STILL QUEUED IS NOT RE-ENQUEUED",
      third["enqueued_count"] == 0, third["enqueued"])
check("  and the sweep says which kinds it is waiting on",
      third["in_flight_kinds"] == ["echo"], third["in_flight_kinds"])

# finish the job; now the next window may fire
db.query(Job).filter(Job.project_id == PID, Job.kind == "echo").update({"state": "done"}); db.commit()
fourth = routines_run.run_due(db, PID, now=NEXT, actor="test")
check("ONCE THE JOB FINISHES the next window fires — the block was in-flight, not permanent",
      fourth["enqueued_count"] == 1, fourth["enqueued"])

# --- 5. missed windows fire ONCE, never one job per window ----------------------------------------
r_old = routine("Monthly, dormant a year", "echo", cadence="monthly", last_run="2025-08-01")
db.query(Job).filter(Job.project_id == PID).update({"state": "done"}); db.commit()
LATER = datetime(2026, 8, 9, 9, 0, tzinfo=timezone.utc)
n_before = db.query(Job).filter(Job.project_id == PID).count()
fifth = routines_run.run_due(db, PID, now=LATER, actor="test")
n_after = db.query(Job).filter(Job.project_id == PID).count()
fired = [e for e in fifth["enqueued"] if e["routine_id"] == r_old]
check("A ROUTINE DORMANT FOR TWELVE WINDOWS FIRES ONCE, not twelve times",
      len(fired) == 1, fired)
check("  and the missed count is reported rather than replayed",
      (fired[0]["missed_windows"] or 0) >= 1, fired[0])
check("  so the queue grew by the number of DUE routines, not by windows missed",
      n_after - n_before == fifth["enqueued_count"], (n_before, n_after, fifth["enqueued_count"]))
check("the note names the flood it is preventing", "flood the queue" in fifth["note"])

# --- 6. A KIND THAT NEEDS ARGUMENTS CAN NOW BE SCHEDULED, AND IS REFUSED WITHOUT THEM -------------
#
# R24-REPORTS-BY-MOMENT ③. Until `job_params` existed the sweep built ONE params dict for every kind —
# `{routine_id, window_start}` plus the project — so `report_package` could not be scheduled at all,
# and `modules/routine/module.json` had to leave it off the picklist and say why in its help text.
# "The owner's package, every month" is the plainest thing anyone wants from a scheduler sitting on a
# report catalog, and it was the one thing this scheduler could not do.
#
# **The success and the two refusals are checked in the SAME sweep, on purpose.** A refusal-only test
# passes just as happily when nothing can ever run — the lesson `test_routines.py` check 5 was written
# from, where every kind a user could pick was refused and every refusal test was green.
from aec_api import report_moments  # noqa: E402

db.query(Job).filter(Job.project_id == PID).update({"state": "done"}); db.commit()
PKG = datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc)

r_pkg = routine("Owner package, monthly", "report_package", moment="owner_monthly")
r_nomoment = routine("Package of what?", "report_package")
r_badmoment = routine("Package of nonsense", "report_package", moment="quarterly_vibes")
r_moot = routine("Nightly CI with a stray moment", "echo", moment="owner_monthly")

sixth = routines_run.run_due(db, PID, now=PKG, actor="test")
_by_routine = {e["routine_id"]: e for e in sixth["enqueued"]}
_refused = {f["routine_id"]: f for f in sixth["refused"]}

check("A SCHEDULED REPORT PACKAGE IS ENQUEUED — the gap R22 left open",
      r_pkg in _by_routine, sorted(_by_routine))
_pkg_params = (db.query(Job).filter(Job.id == _by_routine[r_pkg]["job_id"]).one().params or {}
               ) if r_pkg in _by_routine else {}
check("  and the JOB ROW carries the moment's reports, which is what makes it runnable",
      _pkg_params.get("reports") == report_moments.MOMENTS["owner_monthly"][2], _pkg_params)
check("  named by moment, so a scheduled package and a clicked one are the same job",
      _pkg_params.get("moment_id") == "owner_monthly", _pkg_params)
check("  without losing the routine and window it came from",
      _pkg_params.get("routine_id") == r_pkg and _pkg_params.get("window_start"), _pkg_params)

check("A PACKAGE ROUTINE THAT NAMES NO MOMENT IS REFUSED, not queued to fail later",
      _refused.get(r_nomoment, {}).get("status") == routines_run.STATUS_BAD_PARAMS,
      sixth["refused"])
check("  and the refusal lists the moments it could have named",
      "owner_monthly" in (_refused.get(r_nomoment, {}).get("reason") or ""),
      _refused.get(r_nomoment))
check("AN UNKNOWN MOMENT IS REFUSED THE SAME WAY — a typo is not a package",
      _refused.get(r_badmoment, {}).get("status") == routines_run.STATUS_BAD_PARAMS,
      sixth["refused"])
check("  and neither refusal left a job row behind",
      db.query(Job).filter(Job.project_id == PID, Job.kind == "report_package").count() == 1,
      db.query(Job).filter(Job.project_id == PID, Job.kind == "report_package").count())

check("A MOMENT ON A KIND THAT HAS NO USE FOR ONE STILL RUNS", r_moot in _by_routine,
      sorted(_by_routine))
check("  but says it ignored it, rather than silently changing what ran",
      "ignored" in (_by_routine.get(r_moot, {}).get("note") or ""), _by_routine.get(r_moot))
check("  and the plain routines carry no params key at all",
      "params" not in _by_routine.get(r_moot, {}), _by_routine.get(r_moot))

# The unit-level table, checked directly: the sweep above proves the wiring, this proves the mapping.
_extra, _refusal, _note = routines_run.job_params("report_package", {"moment": "lender_draw"})
check("job_params expands a moment into exactly the reports that moment names",
      _extra == {"moment_id": "lender_draw", "reports": report_moments.MOMENTS["lender_draw"][2]}
      and _refusal is None and _note is None, (_extra, _refusal, _note))
check("  and hands back a COPY, so a caller cannot mutate the table",
      _extra["reports"] is not report_moments.MOMENTS["lender_draw"][2])

# --- 7. THE SCHEDULED JOB IS RUN, NOT MERELY ENQUEUED --------------------------------------------
#
# **This section exists because everything above it passed while the sweep produced jobs that could
# not run.** Section 6 asserted the Job ROW — right kind, right reports, right moment. It never called
# the handler. And a handler is invoked as `fn(db, j.params)` (`jobs.py`, `_run_one`) and never sees
# the Job row, so `Job.project_id` is invisible to it: every registered kind reads
# `params.get("project_id")`, and two of them read `params.get("actor")` as an identity claim recorded
# against the coordination issues they create.
#
# `routers/jobs.py` writes both into `params` LAST, after the caller's, so neither can be spoofed from
# a request body. The sweep wrote neither. So a scheduled job queued cleanly, ran, and died on an
# empty project — and the whole Routines feature was inert one layer below the layer that had just
# been fixed. Nothing above caught it, because **"it was enqueued" and "it can run" are different
# claims and only the first was ever asserted.**
#
# So this runs the real handler on the real params the sweep produced. Half a second, one 11-report
# PDF, and the class of defect cannot come back silently.
_pkg_job = db.query(Job).filter(Job.id == _by_routine[r_pkg]["job_id"]).one() if r_pkg in _by_routine \
    else None

check("every scheduled job carries the project it runs against — handlers never see the Job row",
      all((j.params or {}).get("project_id") == PID for j in
          db.query(Job).filter(Job.project_id == PID, Job.kind != "not_a_kind").all()),
      sorted({str((j.params or {}).get("project_id")) for j in
              db.query(Job).filter(Job.project_id == PID).all()}))

check("  and the actor, which two kinds record as an identity against what they write",
      (_pkg_job.params or {}).get("actor") == "test", (_pkg_job.params or {}) if _pkg_job else None)

try:
    _artifact = jobs.KINDS["report_package"](db, dict(_pkg_job.params or {}))
    _pkg_err = None
except Exception as _e:                                    # noqa: BLE001
    _artifact, _pkg_err = {}, _e

check("A SCHEDULED PACKAGE ACTUALLY ASSEMBLES — the handler runs on the params the sweep wrote",
      _pkg_err is None, repr(_pkg_err))
check("  producing a PDF artifact rather than an empty one",
      str(_artifact.get("media_type")) == "application/pdf" and int(_artifact.get("bytes") or 0) > 1000,
      {k: _artifact.get(k) for k in ("media_type", "bytes", "filename")})
check("  named for the moment, and holding every report that moment lists",
      _artifact.get("filename") == "owner_monthly.pdf"
      and _artifact.get("reports") == report_moments.MOMENTS["owner_monthly"][2],
      (_artifact.get("filename"), _artifact.get("reports")))

# --- 8. A SCHEDULED ARTIFACT REACHES ITS RECIPIENTS ------------------------------------------------
#
# R24-REPORTS-BY-MOMENT's last remainder. Section 7 proved a scheduled package ASSEMBLES; assembling
# it and leaving it in the job tray is most of a feature, because the whole reason to schedule the
# owner's monthly package is that nobody has to remember it.
#
# These run the REAL worker (`jobs._run_one`) on the REAL job the sweep enqueued, with only
# `mailer.send_email` swapped for a recorder — the same lesson section 7 was written from, applied
# one layer further out. A test that asserted `deliver_to` reached `params` would pass just as
# happily if nothing ever mailed it.
from aec_api import mailer  # noqa: E402

_sent: list = []
_real_send = mailer.send_email


def _recording_send(to, subject, body, html=None, attachments=None):
    """Stand in for `mailer.send_email`, recording what would have been sent and reporting success.

    Only the SMTP call is faked. Everything above it — the sweep, the worker, the handler, the
    delivery core's caps and de-duplication — is the real code path, which is the point: the
    interesting failures live there, not in smtplib.
    """
    _sent.append({"to": to, "subject": subject, "attachments": attachments})
    return "sent"


def _run_next() -> None:
    """Claim and run exactly one queued job on a fresh session, the way the worker does."""
    jobs._run_one(SessionLocal)
    db.expire_all()                      # this session predates the worker's commit


def _drain_to_done() -> None:
    """Finish every outstanding job, so the next sweep is not blocked by an earlier section's queue.

    `run_due` skips a routine whose KIND already has queued or running work — correct behaviour, and
    it would otherwise make these sections depend on the order the ones above them left things in.
    """
    db.query(Job).filter(Job.state.in_(("queued", "running"))).update({"state": "done"},
                                                                     synchronize_session=False)
    db.commit()


DELIVER = datetime(2026, 8, 11, 9, 0, tzinfo=timezone.utc)
mailer.send_email = _recording_send
try:
    _drain_to_done()
    r_mail = routine("Owner package, mailed", "report_package", moment="owner_monthly",
                     deliver_to="owner@example.test, lender@example.test")
    r_quiet = routine("Owner package, tray only", "echo")
    eighth = routines_run.run_due(db, PID, now=DELIVER, actor="scheduler")
    _mail_job = {e["routine_id"]: e["job_id"] for e in eighth["enqueued"]}

    check("the sweep carries the routine's recipients into the job",
          "deliver_to" in (db.query(Job).filter(Job.id == _mail_job[r_mail]).one().params or {}),
          sorted(db.query(Job).filter(Job.id == _mail_job[r_mail]).one().params or {}))

    for _ in range(len(eighth["enqueued"])):
        _run_next()

    _mj = db.query(Job).filter(Job.id == _mail_job[r_mail]).one()
    _qj = db.query(Job).filter(Job.id == _mail_job[r_quiet]).one()
    _delivery = (_mj.result or {}).get("delivery") or {}

    check("A SCHEDULED PACKAGE IS MAILED, not just left in the tray", len(_sent) == 2,
          [s["to"] for s in _sent])
    check("  to the addresses the routine named, parsed out of one text field",
          sorted(s["to"] for s in _sent) == ["lender@example.test", "owner@example.test"],
          sorted(s["to"] for s in _sent))
    check("  with the assembled PDF actually attached, not an empty notification",
          bool(_sent) and _sent[0]["attachments"]
          and _sent[0]["attachments"][0][0] == "owner_monthly.pdf"
          and len(_sent[0]["attachments"][0][1]) > 1000,
          _sent[0]["attachments"][0][:1] if _sent and _sent[0]["attachments"] else None)
    check("  and the outcome is recorded on the job, so a silent non-delivery is impossible",
          _delivery.get("recipients") == 2 and _delivery.get("results") == {"sent": [
              "owner@example.test", "lender@example.test"]}, _delivery)
    check("  while the job itself is done — delivery is not what the job was for",
          _mj.state == "done", (_mj.state, _mj.error))

    check("A ROUTINE THAT NAMES NOBODY MAILS NOBODY — the default is off",
          "delivery" not in (_qj.result or {}), (_qj.result or {}).get("delivery"))

    # Rule 2: `deliver_to` is not a side-channel on the public enqueue endpoint. Without a
    # routine_id — which only the sweep sets — the worker does not mail, whatever params say.
    _sent.clear()
    _direct = jobs.enqueue(db, "echo", PID, {"project_id": PID, "deliver_to": "nobody@example.test"},
                           actor="tester")
    _run_next()
    check("A JOB WITH RECIPIENTS BUT NO ROUTINE DOES NOT MAIL — params are caller-supplied",
          _sent == [] and "delivery" not in (db.query(Job).filter(Job.id == _direct.id).one().result or {}),
          _sent)

    # Rule 1: the artifact was produced; a mail failure must not turn that into a failed run.
    _sent.clear()
    _boom = routine("Package, SMTP down", "report_package", moment="lender_draw",
                    deliver_to="x@example.test")
    _drain_to_done()
    mailer.send_email = lambda *a, **k: (_ for _ in ()).throw(OSError("smtp unreachable"))
    ninth = routines_run.run_due(db, PID, now=datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc),
                                 actor="scheduler")
    for _ in range(len(ninth["enqueued"])):
        _run_next()
    _bj = db.query(Job).filter(
        Job.id == {e["routine_id"]: e["job_id"] for e in ninth["enqueued"]}[_boom]).one()
    check("A DELIVERY FAILURE LEAVES THE JOB DONE — the package exists either way",
          _bj.state == "done", (_bj.state, _bj.error))
    check("  and the failure is on the row rather than swallowed",
          "smtp unreachable" in str(((_bj.result or {}).get("delivery") or {}).get("error")),
          (_bj.result or {}).get("delivery"))
    check("  with the artifact still recorded, so it can be re-sent by hand",
          bool((_bj.result or {}).get("artifact_key")), sorted(_bj.result or {}))
finally:
    mailer.send_email = _real_send

check("recipients are split on commas, semicolons and newlines — however someone typed them",
      jobs._split_recipients("a@x.test, b@x.test; c@x.test\nd@x.test")
      == ["a@x.test", "b@x.test", "c@x.test", "d@x.test"],
      jobs._split_recipients("a@x.test, b@x.test; c@x.test\nd@x.test"))
check("  and an empty field is no delivery, not an empty send",
      jobs._split_recipients("") == [] and jobs._split_recipients(None) == [])

db.close()
engine.dispose()

print()
if FAILED:
    print(f"routines_run: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("routines_run: all checks passed")
