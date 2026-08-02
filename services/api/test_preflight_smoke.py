"""The production preflight must actually run, and each hard failure must be able to fire.

`scripts/validate_prod_config.py` is the documented go/no-go gate before exposing the stack. Nothing
executed it — not the suite, not a workflow, not a Makefile target. It was a gate in the sense that a
fire extinguisher in a locked case is fire safety: present, documented, pointed at by the checklist,
never once discharged. `test_preflight_covers_settings` closed the *coverage* question statically
(are the documented settings checked at all?); this closes the *behavioural* one — does the script
still exit non-zero when the posture is wrong.

Both halves are needed, and the good-posture case alone would be worse than nothing: a validator
whose every check silently stopped matching would print "all checks passed" and exit 0, which is
exactly what a correct run looks like. So each hard requirement is driven individually — flip one
variable away from a known-good production posture and the run must fail *and name that setting*.
Nothing here asserts the good posture is warning-free: warnings are advisory, and pinning their count
would make this test fail every time somebody adds one.

Two details are load-bearing rather than incidental:

  * **The child gets an explicit env, never the parent's.** The script reads the same `AEC_*` names a
    developer has exported to run the app locally, so an inherited environment silently rewrites the
    posture under test — a machine with `AEC_TRUST_XUSER=1` set for the suite would make the
    good-posture case fail, and a machine with a real `AEC_AUTH_SECRET` would mask its absence. The
    base env carries only what an interpreter needs to start (`SystemRoot`/`PATH` matter on Windows).
  * **The mutation is asserted by name, not by exit code alone.** Any of these flips makes the script
    exit 1, so "exit 1" only proves *something* failed. Requiring the setting's own name in the output
    is what distinguishes "this check fired" from "a different check happened to fire".
"""
import os
import pathlib
import subprocess
import sys

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "validate_prod_config.py"

# A posture that should clear the gate. Deliberately spelled out rather than derived: this is the
# reference "what production looks like", and a derived one would drift with whatever the app does.
GOOD = {
    "DATABASE_URL": "postgresql://aec:a-real-long-password@db:5432/aec",
    "AEC_RBAC": "1",
    "AEC_AUTH_SECRET": "s" * 48,
    "AEC_REQUIRE_SECRET": "1",
    "AEC_HSTS": "1",
    "AEC_COOKIE_SECURE": "1",
    "AEC_CSP": "1",
    "AEC_ALLOWED_HOSTS": "app.example.com,localhost",
    "AEC_RATE_LIMIT_RPM": "120",
    "UVICORN_WORKERS": "1",
    "STORAGE_DIR": "/data/storage",
}

# one flip away from GOOD -> must FAIL, and the message must name the setting
MUTATIONS = [
    ("AEC_RBAC", {"AEC_RBAC": "0"}, "AEC_RBAC"),
    ("AEC_AUTH_SECRET unset", {"AEC_AUTH_SECRET": ""}, "AEC_AUTH_SECRET"),
    ("AEC_TRUST_XUSER on", {"AEC_TRUST_XUSER": "1"}, "AEC_TRUST_XUSER"),
    ("AEC_COOKIE_SECURE off", {"AEC_COOKIE_SECURE": "0"}, "AEC_COOKIE_SECURE"),
    ("default MinIO secret", {"S3_ENDPOINT": "http://minio:9000",
                              "S3_SECRET_KEY": "minioadmin"}, "S3_SECRET_KEY"),
    ("default postgres password",
     {"DATABASE_URL": "postgresql://postgres:postgres@db:5432/aec"}, "DATABASE_URL"),
    ("per-worker rate limit", {"UVICORN_WORKERS": "4", "AEC_REDIS_URL": ""}, "AEC_REDIS_URL"),
]

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


def run(overrides: dict):
    """Run the preflight with an EXPLICIT env — inheriting the parent's would rewrite the posture."""
    base = {k: v for k, v in os.environ.items() if k in ("SystemRoot", "SYSTEMROOT", "PATH", "TEMP")}
    base["PYTHONIOENCODING"] = "utf-8"
    env = {**base, **GOOD, **overrides}
    env = {k: v for k, v in env.items() if v != ""}          # "" means unset, not empty
    p = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, env=env)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


check("the preflight script is where the checklist says it is", SCRIPT.is_file(), str(SCRIPT))

rc, out = run({})
check("a known-good production posture clears the gate", rc == 0,
      out.strip().splitlines()[-1] if out.strip() else "(no output)")

for label, override, must_name in MUTATIONS:
    rc, out = run(override)
    named = must_name in out
    check(f"fires on {label}", rc == 1 and named,
          f"exit={rc} names_{must_name}={named}")

# The whole point of the good-posture case is that it is distinguishable from a broken validator, so
# prove the two are not the same run: at least one mutation must produce output the good one did not.
rc_good, out_good = run({})
rc_bad, out_bad = run({"AEC_RBAC": "0"})
check("good and failing postures are actually distinguishable",
      rc_good != rc_bad and out_good != out_bad, f"exits {rc_good} vs {rc_bad}")

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print(f"preflight_smoke OK — good posture clears, {len(MUTATIONS)} hard requirement(s) each "
      f"verified able to fail by name")
