"""R22-AGENT-PACKS — the transport must pass the identity, not just the audit accept one.

`test_agent_packs.py` proves `dispatch` audits every run and attributes it "to the effective user,
not the transport". That check passes because **the test supplies `user=` and `pack=`**. The only
production caller — the stdio MCP server, the single path any real agent run takes — supplied
neither, so every row in the governance console read actor `mcp`, user empty, pack empty. The audit
answered "which tools ran" and could not answer "whose agent ran them".

That is the defect a test supplying the inputs cannot see: it exercises the callee with arguments the
caller never sends. So these checks are about the **call site**, and the two halves are asserted
separately:

1. `transport_identity()` — what the transport can honestly claim from the operator's environment,
   including the case where it can claim nothing;
2. **the wiring** — that `main()`'s dispatch call actually forwards all three. A perfect
   `transport_identity` that nothing passes to `dispatch` is the same bug in a new place.

And one refusal: an unconfigured server must **say so**. Recording every run against the transport
silently is indistinguishable from recording it against a user nobody verified.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_mcp_attribution.py
"""
import ast
import sys

sys.path.insert(0, "src")

import mcp_server  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


# --- 1. what the transport can honestly claim -----------------------------------------------------
bare = mcp_server.transport_identity({})
check("with nothing configured the run is NOT attributed", bare["attributed"] is False, bare)
check("  and the actor names the transport rather than inventing a person",
      bare["actor"] == mcp_server.TRANSPORT_ACTOR and bare["user"] is None, bare)
check("  with no pack claimed", bare["pack"] is None, bare)

conf = mcp_server.transport_identity({mcp_server.ENV_USER: "sam@acme.com",
                                      mcp_server.ENV_PACK: "submittal_review"})
check("a configured user IS carried", conf["user"] == "sam@acme.com", conf)
check("  and marks the run attributed", conf["attributed"] is True, conf)
check("  carrying the pack the operator configured", conf["pack"] == "submittal_review", conf)

check("whitespace is not an identity — a blank value is absent, not a user named ' '",
      mcp_server.transport_identity({mcp_server.ENV_USER: "   "})["attributed"] is False)
check("a custom actor is honoured",
      mcp_server.transport_identity({mcp_server.ENV_ACTOR: "ci-runner"})["actor"] == "ci-runner")

# --- the refusal: an unattributed server says so --------------------------------------------------
said: list[str] = []
check("an UNATTRIBUTED server warns at startup", mcp_server._warn_unattributed(bare, said.append))
check("  naming the variable that fixes it", mcp_server.ENV_USER in "".join(said), said)
check("  and saying what the trail can and cannot answer", "not who ran it" in "".join(said), said)
said2: list[str] = []
check("a configured server does NOT nag", mcp_server._warn_unattributed(conf, said2.append) is False)
check("  and stays silent", said2 == [], said2)

# --- 2. THE WIRING — the half the callee's own test cannot see ------------------------------------
# Asserted against the parsed call site, because the alternative is importing FastMCP, which is an
# OPTIONAL dependency. A check that silently skips when the SDK is absent would pass on every
# machine that cannot run it, which is the shape of a gate that never fails.
tree = ast.parse(open(mcp_server.__file__, encoding="utf-8").read())
calls = [n for n in ast.walk(tree)
         if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
         and n.func.attr == "dispatch"]
check("main() really calls mcp_tools.dispatch — exactly once", len(calls) == 1, len(calls))
kw = {k.arg for k in calls[0].keywords} if calls else set()
check("THE CALL SITE FORWARDS THE IDENTITY — actor, user AND pack",
      {"actor", "user", "pack"} <= kw, sorted(kw))
check("  and dispatch actually accepts all three, so the forward is not a silent no-op",
      all(p in __import__("inspect").signature(
          __import__("aec_api.mcp_tools", fromlist=["dispatch"]).dispatch).parameters
          for p in ("actor", "user", "pack")))

print()
if FAILED:
    print(f"mcp_attribution: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("mcp_attribution: all checks passed")
