"""
A size budget on the files that are edited most.

This exists because of a question the user asked on 2026-07-28: is this codebase heading somewhere it
can no longer be worked on? The honest answer needed a measurement rather than a reassurance, and the
measurement found one file:

    api/client.ts   4,956 lines   152 commits/14d   631 methods on one class

Length alone is not the problem — `schema.d.ts` is 32k lines and nobody suffers, because it is
generated and nobody reads it. The problem is **length x churn**: a file that must be opened to add
any endpoint, is opened ~11 times a day, and only ever grows. Every change to it competes with every
other change for the same window of attention.

So the budget is not "files should be small". It is: **the files we edit constantly must stay small
enough to hold in your head at once.** Generated files and vendored copies are exempt by name, not by
size, because exemption-by-size is how a budget dies.

The threshold is deliberately set ABOVE today's worst offender. This test is a ratchet that stops the
problem getting worse while SCALE-SEAM brings it down; tightening the number is part of that work.
Setting it below the current state would have shipped a red test, and a red test that everyone learns
to ignore protects nothing.
"""
import os
import re
import subprocess
import sys

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

#: Hand-written source we own. A file over this is a file nobody can review in one sitting.
CEILING = 5_200

#: Per-file ceilings for the files SCALE-SEAM is actively splitting. **Only ever revised DOWN.**
#: That remains a rule for a reader, not an assertion — down-only is a claim about history and this
#: file measures a working tree. MAX_SLACK below covers the half that CAN be measured, and its own
#: comment is explicit about which half that is.
#:
#: WHY THIS EXISTS, and it is a correction to how the ratchet was understood. `CEILING` above is a
#: single GLOBAL number, so it is pinned by whichever file is worst — today `viewer/app.ts` at 5,106
#: (5,064 when this was written; AUTH-SNAP-OVERRIDE added 42 lines the same day, which is exactly how
#: a number embedded in prose goes stale — the assertion below reads the file, this sentence does not).
#: That means an extraction out of any OTHER file cannot move it: SCALE-SEAM ⑦ took 96 lines out of
#: `client.ts` and the global ceiling was as true at 5,200 afterwards as before. The instruction
#: "lower the ceiling as each extraction lands" is right about the intent and cannot be carried out
#: by this number — lowering it to that figure would ratchet a slack belonging to `viewer/app.ts`, a file
#: in a different lane, and leave it with zero headroom so the next edit there fails the build.
#:
#: **A ratchet has to be per-subject when the work is per-subject.** One global number measures the
#: worst file and is silent about every other, which is the same shape as a gate whose scope is
#: narrower than its claim.
#:
#: A new endpoint added straight to `client.ts` will fail this, and that friction is the point rather
#: 2026-08-07: raised by ONE line, and the exception is stated rather than quietly taken. The
#: line is `import { withRoutines } from "./routines";` — the *mechanism* of an extraction,
#: not an endpoint. The endpoint itself went into `api/routines.ts`, which is what this ratchet
#: asks for. A mixin cannot be composed without one import line, so a file sitting exactly on
#: its pin can never gain one otherwise. If this climbs again for the same reason, the pin is
#: measuring the wrong thing and should count endpoints.
#: than a side effect: the question it forces is "should this live in a domain module instead?", and
#: post-⑦ the answer is usually yes. Raising an entry is therefore a deliberate act that should be
#: argued for in the commit message — the direction of travel is down.
PER_FILE = {
    #: ⑨ contracts/scope-library/esign -> contracts.ts. This entry had ZERO headroom — the file
    #: measured exactly its 3,780 cap and the check is `measured > cap`, so a single added line
    #: failed the build. Three lanes hit that wall the same day; two routed their new methods into
    #: other modules and one got a field in only by appending to an existing line. That is the
    #: friction this ratchet is for, and it asked the intended question — the contract documents had
    #: a whole domain to leave with, so the number goes DOWN by 32 instead of up by one.
    #: REL-4. Pinned the moment the first leaf came out, not later. `portal.ts` had NO per-file entry
    #: and so lived under the global ceiling, which it is nowhere near — meaning an extraction from it
    #: bought nothing a check could see, and the next twelve additions could have put the lines
    #: straight back while the work still read as done. **An extraction without a ratchet is a
    #: rearrangement.** Set at the post-extraction count so it can only come down from here.
    "apps/web/src/portal/portal.ts": 1_238,   # executive portfolio -> panels/portfolio.ts (1_353 -> 1_238), REL-4. Chosen by grepping every candidate's this.* refs FIRST: the two mid-sized methods call five and two SIBLING renders, so only this one is a leaf.   # the dead module catalog DELETED (1,400 -> 1,352); unreachable since 2026-06-24, and its star was the only caller of toggleFav in the app   # REL-4 renderDeveloperHome -> homes/developerHome.ts (1,473 -> 1,400)
    "apps/web/src/api/client.ts": 731,   # SCALE-SEAM (93): the two MEP recipes ⑲ HAD TO leave behind (733 -> 731). connectMep + addMepFitting to mep.ts, whose own header since ⑲ said they "call editIfc (/edit) and stay" — A NOTE THAT RECORDED THE SYMPTOM WITHOUT DIAGNOSING THE CAUSE. They could not come because editIfc is declared on the Authoring mixin rather than on HttpCore, so a mixin typed Ctor<HttpCore> cannot see it and the extraction does not compile. (92) found that; (93) applies it. A METHOD LEFT BEHIND FOR A REASON NOBODY WROTE DOWN STAYS BEHIND INDEFINITELY — ⑲'s note read as a placement decision and was a compiler error. NeedsEditIfc moved from annotate.ts into types.ts so both mixins share ONE definition: two hand-copied signatures are exactly the drift the #409 review had to check by hand, since a copy subtly WIDER than the real editIfc typechecks at the mixin and still breaks at a call site. Mutation-checked: composing withMep inside withAuthoring fails with TS2345 naming NeedsEditIfc. EVIDENCE IS WEAKER THAN (92)'S AND IS STATED AS SUCH: this is NOT a complete authoring_matrix category (create-mep has 11 members, edit-mep 3, of which these are one each). The boundary is "MEP recipe exposed as a TYPED client method" — exactly these two. TWELVE MEP recipes remain in the matrix (11 create-mep + 3 edit-mep, less these two): nine are driven from viewer code through the generic recipe path in draftCatalog.ts and mepSection.ts, and THREE (add_sprinkler, auto_connect_mep, set_system_predefined) are referenced nowhere in apps/web/src at all — backend recipes with no web exposure, recorded rather than fixed. THIS SAID "the other nine" UNTIL REVIEW, AND IT IS THE THIRD CONSECUTIVE SLICE WITH ONE DEFECT IN A THIRD DISGUISE: nine was the number I had ENUMERATED (the viewer-driven ones), twelve is the number that REMAIN. (91) claimed no test_cre_* file reached outside its set while three reached out as fixtures; (92) claimed test_annotation.py exercised four recipes and no others while two more were tag-host fixtures; this enumerated a subset and wrote "the other". A reviewer found all three. THE FIX IS NOT TO BE MORE CAREFUL — IT IS TO DERIVE THE COMPLEMENT, set(all) - set(moved), and only then describe what is in it. test_mep_systems.py covers both AMONG other MEP recipes (corroborates family, does not bound the set) and test_guards.py is cross-cutting — said explicitly because the "no others" error was made in each of the two preceding slices. addMepFitting is callerless and stays on clientCallers.test.ts's allowlist: moving a method does not change its called-ness. 82 above the banner now, still no map.   # SCALE-SEAM (92): ANNOTATION — put a note, a dimension, a cloud or a tag ON the model. Four methods to a new annotate.ts (746 -> 733): addAnnotation, addDimension, addRevisionCloud, addTag, all authoring real IfcAnnotation entities at world [E,N] through editIfc. THE SET IS BOUNDED BY TWO SOURCES SOMEBODY ELSE AUTHORED, not by the marker. (i) authoring_matrix.py, the curated recipe->category map behind the public authoring-coverage endpoint, has an `annotate` category holding EXACTLY these four of its 99 recipes across 15 categories — a complete category, nothing left behind and nothing pulled in. (ii) test_annotation.py exercises all four annotation recipes and no other recipe as its SUBJECT (it calls add_wall and add_column once each as fixtures, to give add_tag a host). That qualification was missing until review, and it is the SECOND CONSECUTIVE SLICE to make the error — (91) claimed no test_cre_* file reached outside its set while test_cre_tier3 reached three routes as fixtures. Both times the claim counted what a test TARGETS and ignored what it SETS UP. A "nothing else" claim about a test must say whether it means assertions or every call the file makes. THE `UX-2` MARKER DOES NOT BOUND THE SET, AND THAT DISTINCTION IS THE POINT: (91)'s `CRE-` occurred only in client.ts so it drew its own boundary, while UX-2 occurs 12 times across three files (client.ts, viewer/app.ts, viewer/tools/annotationSection.ts) and marks a FEATURE WORKSTREAM — it corroborates purpose and is silent on membership. Two markers, two strengths; treating every prefix as a set boundary is how a cluster gets the wrong members. Third corroboration: viewer/tools/annotationSection.ts, the UI these serve, makes exactly four api.* calls and they are these four. NOT markup.ts, the obvious guess: that is 2D SHEET markup (a pin at a sheet x/y carrying a note, stored as a markup record, promotable to RFI, route-group /drawings/markup), while these author MODEL CONTENT that travels with the IFC. A comment layer over a drawing and drawing content authored into the model are different questions sharing the word "annotation". NOT authoring.ts, which is the harder call because it DEFINES editIfc and holds seven recipes, and its header claims "the endpoints that WRITE to the model rather than read from it" — which would take all 24 recipes still in client.ts. A DESCRIPTION BROAD ENOUGH TO TAKE EVERYTHING IS NOT A SEAM: its demonstrated practice is narrower than its sentence, having declined detailing at 8, property-override layers at 33 ("those compose properties, they do not write recipes") and groups at 7. mep.ts settled the principle already — its methods "use editIfc (/edit) and stay" — and the matrix proves it, splitting those 24 recipes across NINE categories, so editIfc cannot be the seam. AND A TECHNICAL FINDING THAT PROBABLY EXPLAINS THE WHOLE BACKLOG: this is the first mixin to call editIfc WITHOUT DECLARING IT (authoring.ts calls it seven times but defines it, so it never needed a base type promising it — which is how eleven slices passed these recipes without hitting this). editIfc is declared on the Authoring mixin rather than on HttpCore, so a mixin typed Ctor<HttpCore> cannot see it and the extraction does not compile — the same shape authoring.ts records blocking the SSE methods. annotate.ts declares the requirement in its type (NeedsEditIfc) and must be composed outside withAuthoring; mutation-checked by composing it inside, which fails with TS2345 naming editIfc rather than failing at runtime. Moving editIfc down into HttpCore would unblock the other 20 recipes and is left for the next recipe slice. **(93) TESTED THAT FORECAST AND IT DOES NOT HOLD.** httpCore.ts's own header says it owns the base URL, the bearer token and the low-level fetch helpers, "keeping transport concerns separate from the endpoint surface", and all eight of its methods are transport; editIfc is a DOMAIN endpoint (POST /projects/{pid}/edit). Moving it there would contradict that file's stated purpose and the layering SCALE-SEAM exists to establish. The answer is the NeedsEditIfc pattern, now shared from types.ts. I wrote that forecast as a plan one slice after (91) recorded that a placement forecast is a hypothesis for the next slice to TEST — and phrasing it as a plan is exactly what makes it read as settled. 84 above the banner now, still no map.   # SCALE-SEAM (91): the R20 CRE DEAL DESK — should we transact on this income property, and on what terms? Thirteen methods to a new creDeal.ts (867 -> 746), one contiguous run: verify the seller's numbers (normalizeT12 — the tie-out is a gate; rentRollScrub — a check without its inputs reports not-run; netEffectiveRent; tieredComps; competitiveSupply), decide (holdSell, decisionGate), set the terms (clausePlaybook + reviewContractClauses, loanCovenants, dealAuthority). THREE INDEPENDENT SIGNALS, DERIVED, AND THEY AGREED — more than any slice in this sequence has had. (i) The source marks them: ten CRE- codes, and grepping apps/web/src showed those eleven occurrences are the ONLY ones in the whole web tree, all in client.ts. (ii) A 1:1 router match: every route these thirteen call (eleven distinct paths — the playbook and the authority table each have a read and a write half on one path) is served by aec_api/routers/realestate.py and by no other router, and its ten (R20) docstrings name the same ten codes — paired @router. line to def beneath it, not read top-to-bottom. (iii) One question runs through all thirteen. A marker alone would NOT have been enough: four shared-word traps (entitlements, view, carbon, lifecycle) are why CRE- counts as one vote of three and the router match carries the weight. THE BOUNDARY THAT DECIDES rent-roll: proforma.ts already holds GET /rent-roll and two of these sit under it on /rent-roll/scrub and /rent-roll/net-effective, so a prefix split would take all three. The backend states the boundary — the plain rent roll carries no CRE- code, no (R20), and its docstring calls it the operating rent roll "from the lease module (the hold phase)", while these two POST a body of numbers the counterparty supplied. What are we earning and is their number true are different questions sharing a prefix. AND (88)'S FORECAST WAS TESTED, NOT EXECUTED, AND IT LOST: (88) left camReconciliation with a note saying it "goes with rentRollScrub, netEffectiveRent and normalizeT12 when a rent-roll slice takes them". This is that slice and it did not take it — no CRE- code, no (R20), and /cam/reconciliation is served by operations.py, not realestate.py; a CAM true-up bills a completed operating year to sitting tenants. A placement forecast is a hypothesis for the next slice to test, not an instruction to carry out — phrased as a plan it reads as settled and invites the next reader to execute it without re-deriving anything. The note at the method now says what was measured. REVIEW OF #408 FOUND TWO THINGS AND THE SECOND WAS BIGGER THAN THE FIRST. (a) The fourth-corroboration caveat named one of test_cre_tier3's out-of-set routes and truncated its path; there are three (POST /proforma/scenarios, POST /proforma/scenarios/{sid}/review, GET /projects/{pid}/reports/ic_memo.pdf), all fixtures rather than assertions, so that claim holds for ASSERTED routes only. (b) The no-behaviour-change claim rested on apps/web/src/api/surface.test.ts, which spot-checks a name list none of the thirteen was on plus a floor of 751 on the total client surface — and the surface MEASURES 788. Losing one of the thirteen leaves 787 and passes; losing the whole mixin leaves 775 and passes. The count guarded nothing, which is precisely the slack that file's own comment at the 696 floor predicted would accumulate as endpoints are added; the review asserted the opposite ("losing any one reduces the count below 751"), off by 37. All thirteen are named there now and mutation-checked both ways (renaming holdSell fails naming it; restoring passes). A FLOOR THAT NEW WORK KEEPS CLEARING STOPS BEING A RATCHET WITHOUT EVER GOING RED — the same decay this item already records for client.ts > 1200 and for the banner-string proxy, now found in a third gate. The fix is to name the group, not to raise the floor. 88 above the banner now, still no map.   # SCALE-SEAM (90): the CLIENT PORTAL — how does someone with no account see this project and answer back? Eight methods to a new clientPortal.ts (906 -> 867): the owner half mints/lists/revokes share tokens and reads what came back, the recipient half is the token-authenticated public surface (page + digest URLs, comment, approve/acknowledge/decline). The TOKEN is the seam — minted on one side, IS the credential on the other, revoking closes both — so splitting owner from recipient would put a capability and its only means of exercise in different files. aec_api/routers/client_portal.py groups the same set: 8 of its 9 routes, checked. The ninth (/shared/{token}/model.frag) has no client method BY DESIGN — the server-rendered share page fetches it, not this SPA. FOUND ON THE WAY, NOT FIXED HERE: that route serves geometry only to a token minted with show_model, an opt-in the backend treats as independent of show_payments — and createShareToken never sends it, nor does the returned row type carry it. Every token this product mints has it false, so the public 3D viewer is dark from the UI. Left alone because an extraction slice's claim is that no behaviour changed; recorded in the mixin header at the method. AND THE EXTRACTION SCRIPT HAD A REAL BUG, caught by docComments.test.ts rather than by me: its brace counter only terminated when j>i, so a ONE-LINE method consumed one line too many and swallowed the NEXT method's doc comment. sharedPageUrl and sharedDigestUrl are one-liners; the first draft dragged spaceUtilBenchmarks's SPACE-UTIL doc out of this file and duplicated sharedPageUrl's. Reverted and re-extracted. Seven of these eight carry /** */ docs, which the walk-back did not handle either until this slice — (88) and (89) survived only because their methods used // banners. THE GATE FOUND WHAT MY OWN ORPHAN CHECK MISSED: mine treated a following comment as an acceptable neighbour, which is exactly the case that defines the defect. 101 above the banner now, still no map.   # SCALE-SEAM (89): TWO clusters, two new mixins, eight methods (953 -> 906). The four /resilience/* to resilience.ts — what could the ENVIRONMENT do to this project, asked of the site (flood/SFHA/design flood elevation), the civil design (runoff, detention) and the programme (weather-sensitive activities, delay days), plus the composite that folds all three into one rating. TENSION NAMED RATHER THAN SMOOTHED: resilienceWeather reads ACTIVITIES with trade/start/finish/percent, which is schedule.ts vocabulary and a subject-matter split would send it there; it stays because climateRisk consumes its weather_delay_days in the same composite as the flood and runoff numbers, and separating an input from the rollup that eats it is the split (87) had to undo. AND THE BANNER OVER-CLAIMED FOR THE SIXTH TIME: "climate & water resilience (flood + stormwater)" named TWO of the four beneath it, weather and the composite filed at whatever header was nearest — same defect as ⓽'s AI-drafting banner, (81)'s ifcClassify under a G704 header and (82)'s RACI banner describing 4 of 13. The four /responsibility/* to responsibility.ts — who is ACCOUNTABLE for what. aec_api/routers/responsibility.py holds those four routes AND NOTHING ELSE, a 1:1 router correspondence, checked rather than assumed. NOT filed on modules.ts even though that router's own docstring says the rows ARE ordinary module records whose CRUD lives there: storage is a HOW, and "they are all module records" is (85)'s "they are all multipart uploads" one layer down. Four methods is a small file and that is fine — risk/dealMemory/assetRights hold two each. ResponsibilityMatrix's type import left client.ts with them; it had no other reader. 109 above the banner now, still no map.   # SCALE-SEAM (88): the OPERATE-PHASE cluster, and the FIRST slice from the 126 methods that were never in any map (1015 -> 953). Nine to a new operations.ts — cmms x2, energyActual, energyBenchmarkStatus, twinReadiness, fca x2, reserveStudy, esgSummary — answering "how is this asset performing in service, and what will it need?". Checked against the backend rather than assumed: all nine are served by aec_api/routers/operations.py, whose docstring names the same cluster. THREE DID NOT COME, and the words say otherwise on every one. lifecycle/lifecycleSeed are DESIGN lifecycle (RIBA/AIA stage gates, design_fee_pct, soft_costs) — the fourth shared-word trap after entitlements, view and carbon. projectCarbon is EMBODIED carbon, a design estimate, while esgSummary GHG comes from meters. camReconciliation shared reserveStudy's banner AND its backend router and still stayed: it allocates recoverable opex across TENANTS and returns balance_due per suite, a lease answer, so it waits for the rent-roll slice with rentRollScrub, netEffectiveRent and normalizeT12. Its banner is rewritten in client.ts rather than left naming a method that has gone. AND THE STAYING BANNER CITED esgSummary as an example of work still above the line — a banner offering, as evidence of what is unfinished, a method this slice moved. Corrected, and it now says to re-derive rather than read.   # SCALE-SEAM (87): the CX-1 residue is FINISHED — 13 methods to elements/entitlements/proforma/estimate/modules/procurement/schedule/evm.ts (1131 -> 1015), and five more types out of client.ts into types.ts. TWO CORRECTIONS OF MY OWN EARLIER WORK. (i) ⓽ moved bidLevelingDetail to procurement.ts reasoning about procurementLevel and never noticed bidLeveling, the SUMMARY its detail belongs to, sitting in the same file — a rollup separated from its detail, the exact split (83) and (84) refused. Reunited. (ii) modules.ts carried a "compliance expiry" banner since SCALE-SEAM ④ (v0.3.803) whose method never came: complianceExpiring stayed in client.ts while its LABEL sat above addEnumOption. docComments.test.ts could not see it — its stranded check looks for /** */ above /** */, and this is a // banner above an undocumented method. AND THE BIG ONE: deriving the whole population showed client.ts has 130 methods, only 4 of them under the banner — 126 above it were never in any map. So (85)'s roadmap_status predicate ("--- UNFILED —" in client.ts) was ALSO a proxy: it would have declared SCALE-SEAM done with 126 methods outstanding. Replaced with a count of methods beyond the file's declared keep-list.   # SCALE-SEAM (86): executivePortfolio + constructionPortfolio -> evm.ts, portfolioPrioritization -> proforma.ts, smart views -> elements.ts (1173 -> 1131). THE PORTFOLIO TRIO SPLIT 2/1: two REPORT status and are the cross-project form of evm.ts's projectHealth ("is the job on track across domains?"); the third RANKS deals and belongs with the pipeline in proforma.ts. And a shared WORD is not a shared domain for the third slice running: modules.ts already had a saved-views family (SavedViewDef = {q, state, sort}, a data-grid filter) and the name matched exactly, but a SmartView is {selector, mode: isolate|color|hide} that resolves to GUIDs — a saved SELECTION, so it went to elements.ts beside colorBy.   # SCALE-SEAM (85): source-model ingest + the RVT bridge -> model.ts, raisePlan -> authoring.ts, takeoffDxf -> estimate.ts (1212 -> 1173). MECHANISM IS NOT A QUESTION: (84) had grouped these five as "how do I get a file into this project?", which is really "they are all multipart uploads" — a HOW. Read for what they answer and they split FOUR ways. rvtBridgeStatus did NOT go to entitlements.ts: that mixin is LAND-USE entitlements (planning approvals), a homonym. Also widened unfiledMap.test.ts, which matched only 2-space method indentation and so could not see authoring.ts (37 methods), assetRights, docqa or library — the async bug again, in the gate written to prevent it; it now asserts every mixin contributes at least one name.   # SCALE-SEAM (84): dev budget + draws -> proforma.ts, pricing/traceability -> cost.ts, subcontractorBilling -> accounting.ts (1292 -> 1212), and the DevBudget* interfaces out of client.ts into types.ts, where a mixin can import them. THE TYPES DECIDED THE SPLIT: gmpReconciliation and syncGmpToHard look like cost.ts work (㉚ put the GMP stack there) but both return DevBudgetLine/DevBudgetSummary, and filing them there would have forced one type family into two mixins. cost.ts gmpBudget is the GC's own GMP; these two are the developer comparing against it. ALSO: (83) recorded the CX-1 banner as 44 methods using a regex that did not match `async` — it was 49. The right number was in the roadmap and (83) "corrected" it to a wrong one. Restored, and the UNFILED map is now derived by apps/web/src/api/unfiledMap.test.ts rather than proofread.   # SCALE-SEAM (83): commissioning -> documents.ts, model checks + rebarCheckCage -> model.ts, qtoByFloor -> estimate.ts (1339 -> 1292). The "CX-1 commissioning loop" banner ran to the END of the file over 44 methods, three of them commissioning; with those three gone it named NOTHING, so it is replaced by an UNFILED map of the 35 that remain rather than narrowed. Two placements came from return shapes, not routes: qtoByFloor looks like a quantity and reads /qto/, but every line carries rate and amount and the payload has a grand_total, so it is priced takeoff; and rebarCheckCage came to model.ts while its two /rebar/ siblings did NOT, because a bar bending schedule is a quantity and an ACI cage check is the same question envelopeAudit asks.   # SCALE-SEAM (82): model-quality audits -> model.ts, namingAudit -> documents.ts (1374 -> 1339). The RACI banner covered THIRTEEN methods and described four. namingAudit was on its way to model.ts until the return shapes were compared with documents.ts's namingConventions — same two subjects, containers and sheets, one stating the pattern and one reporting compliance. The banner is now split, and the three methods still under it that are not RACI are named as unfiled rather than left implicit.   # SCALE-SEAM (81, unnumbered — the ⓵–⓾ glyph range is exhausted and the item carries no mark): turnover/G704 -> documents.ts, ifcClassify -> model.ts, market escalation -> cost.ts (1436 -> 1374). THIRD banner in three slices that over-claimed: ifcClassify sat under "turnover: substantial completion (G704)" separated by a blank line, a model question filed at whatever banner was nearest.   # SCALE-SEAM ⓾: concept-render + aiReadiness -> ai.ts (1462 -> 1436). aiReadiness had been declined TWICE — by ai.ts at ㉑ on route grounds ("it is /ai-readiness"), and by documents.ts at ㉛ on semantic grounds ("it is an AI scorecard, not a CDE question"). The second characterisation is what moved it; the first is the superseded rule. MARKS widened to ⓾ (U+24FE), the last of the double-circled range.   # SCALE-SEAM ⓽: drafting -> ai.ts, extractSheets -> drawingSheets.ts, bidLevelingDetail -> procurement.ts (1512 -> 1462). One banner, THREE questions: the "AI drafting" section labelled where the /draft/ run started and then carried on into sheet extraction and bid levelling — the exact failure procurement.ts's own header recorded at ⑥. No version bump (tag lag at bound).   # v0.3.1143 follow-on SCALE-SEAM ⓺+⓻+⓼: preflight -> documents.ts, types+groups -> authoring.ts (1584 -> 1512).   # v0.3.1143 follow-on SCALE-SEAM ⓷+⓸+⓹: license -> auth.ts, land -> entitlements.ts, pins -> topics.ts (1663 -> 1584).   # v0.3.1143 follow-on SCALE-SEAM ⓴+⓵+⓶: clash import -> clash.ts, jobs -> routines.ts, projects -> auth.ts (1740 -> 1663).   # v0.3.1143 follow-on SCALE-SEAM ⓱+⓲+⓳: inbox+escalations -> routines.ts, versions -> model.ts (1814 -> 1740).   # v0.3.1143 follow-on SCALE-SEAM ⓮+⓯+⓰: roster+audit -> auth.ts, presence -> sync.ts (1867 -> 1814).   # v0.3.1143 follow-on SCALE-SEAM ⓫+⓬+⓭: health -> evm.ts, safety+field-log -> schedule.ts, E57 -> model.ts (1916 -> 1867).   # v0.3.1143 follow-on SCALE-SEAM ❽+❾+❿: bidding -> procurement.ts, quality -> topics.ts, closeout -> documents.ts (1966 -> 1916).   # v0.3.1143 follow-on SCALE-SEAM ❺+❻+❼: actions -> routines.ts, RFI register -> topics.ts, feasibility -> entitlements.ts (2_000 -> 1966).   # v0.3.1143 follow-on SCALE-SEAM ❷+❸+❹: ask -> ai.ts, submittals -> procurement.ts, CO log -> contracts.ts (2_035 -> 2_000).   # v0.3.1143 follow-on SCALE-SEAM ㊾+㊿+❶: reports -> documents.ts, T&M + WH-347 -> cost.ts (2_065 -> 2_035). CJK enclosed numbers end at ㊿; ❶ is 51.   # v0.3.1143 follow-on SCALE-SEAM ㊻+㊼+㊽: verification -> model.ts, rent-roll -> proforma.ts, opendata permits -> entitlements.ts (2_127 -> 2_065).   # v0.3.1143 follow-on SCALE-SEAM ㊸+㊹+㊺: view templates -> model.ts, selections -> contracts.ts, progress -> schedule.ts (2_194 -> 2_127).   # v0.3.1143 follow-on SCALE-SEAM ㊵+㊶+㊷: layout+loads -> model.ts, optioneer -> authoring.ts (2_258 -> 2_194). leftover // banners deleted.   # v0.3.1143 follow-on SCALE-SEAM ㊲+㊳+㊴: graph+layers -> model.ts, macros -> authoring.ts (2_323 -> 2_258).   # v0.3.1143 follow-on SCALE-SEAM ㉞+㉟+㊱: structure -> model.ts, RFI -> topics.ts, logistics -> schedule.ts (2_440 -> 2_323). No version bump (tag lag at bound).   # v0.3.1143 SCALE-SEAM ㉝: Last-Planner pull board -> schedule.ts (2_486 -> 2_440).   # v0.3.1142 SCALE-SEAM ㉜: appraisal/listing -> proforma.ts (2_531 -> 2_486).   # v0.3.1141 SCALE-SEAM ㉛: ISO 19650 CDE/BEP/info-requirements -> documents.ts (2_580 -> 2_531).   # v0.3.1140 SCALE-SEAM ㉚: GMP / pay-app stack -> cost.ts (2_641 -> 2_580).   # v0.3.1139 SCALE-SEAM ㉙: investor capital stack -> finance.ts (2_696 -> 2_641), nine methods, existing withFinance wrapper.   # v0.3.1134: clash group -> clash.ts (2_731 -> 2_696). SOFT-CLASH-RULES added clashClearanceRules + clashMatrix; the pin refused them in this file so the whole /clash cluster moved.   # v0.3.1124: the four refusal-aware response shapes moved to types.ts as named interfaces (2_769 -> 2_731, under the 2_752 pin they had broken). THE RATCHET DID ITS JOB: 18 lines of new response fields went into this file and it went red, which is the whole point — types.ts exists precisely so the type surface lives apart from the client, and its header says so. The pin comes DOWN 21 rather than up, and the file is now 20 lines below where main had it.   # ㉘ SCALE-SEAM ㉘ construction accounting -> accounting.ts (2_816 -> 2_752), ten methods in TWO non-contiguous clusters ~700 lines apart, which is the strongest case for grouping by what methods ANSWER: no prefix split would have found them together, and `journalBatchExportUrl` builds the URL for the batch `createJournalBatch` creates. The 2_837 this replaces was ㉗'s; v0.3.1119 had already taken it to 2_816 under duress from this very check, without lowering the pin — so the ratchet had slack it had not been told about.
    #: R39-DECOMP-VIEWER. Pinned at its CURRENT size before any extraction, deliberately.
    #:
    #: `app.ts` had no per-file entry, so it lived under the 5,200 global — which it also *set*, being
    #: the worst file. That is a ceiling it cannot ratchet against: every extraction from any other
    #: file left the global exactly as true as before, and every feature added here drifted it up
    #: with nothing to notice. Two Lane E features in a row had to route logic into new modules to
    #: fit under it, which is a good outcome reached by an accidental mechanism.
    #:
    #: Pinned BEFORE the split rather than after, so the number the extraction has to beat is the
    #: unimproved one. Pinning afterwards would freeze the improved figure and lose the evidence that
    #: it moved — the history in the line above (3,967 → 3,871 → 3,796) is the thing worth having.
    #: R39-DECOMP-VIEWER, one entry per slice so the movement is the record:
    #:   ① Exports (51)   5,160 -> 5,114
    #:   ② clash/QA (851) 5,114 -> 4,272
    #:   ③ analyse (238) + ④ authoring (91)  4,272 -> 3,953
    #:   ⑤ project-browser panel (216)      3,953 -> 3,751
    #:   ⑥ loadProjectModel (37)            3,751 -> 3,715
    #: The whole `builders` map is now out of app.ts. Ratcheted each time, never reset.
    #:
    #: ⑥ is worth recording because the ratchet CAUSED it rather than merely permitting it.
    #: R39-VIEWER-OBS needed ~5 lines of instrumentation inside `loadProjectModel`, and this entry had
    #: zero headroom, so the choice was to raise the pin or move the routine. The comment above says
    #: the friction is the point and that the question it should force is "should this live in a
    #: domain module instead?" — for a self-contained fetch/parse/show sequence the answer was plainly
    #: yes. The instrumentation went into the new module and app.ts came DOWN 36 lines instead of up.
    #: 3_715 -> 3_717 (v0.3.916). RAISED, which the comment above says must be argued for, so:
    #: R36 slice 3 added one user-facing rail control ("Place this view on a sheet"). The extraction
    #: the ratchet asks for HAPPENED — `sheetSpecs.ts` is 133 lines of new logic that never entered
    #: this file, and it also absorbed the three inline `URLSearchParams` builders that were here
    #: (which were sending `number`/`title`/`scale`, none of which the route accepts). What is left is
    #: two lines of WIRING for a new button, and wiring is what this file is for. The alternative was
    #: to push DOM construction into `sheetSpecs.ts`, whose freedom from the DOM is exactly why its
    #: eleven tests need no browser — that would be trading a real property for a number.
    #: RESTORED 2026-08-29 from 2_865, and the restoration is the reason MAX_SLACK below exists.
    #: Slices ⑭⑮⑯ walked this pin 2_865 -> 2_757 -> 2_630 -> 2_571 on 2026-08-27, and the REL-4
    #: portal commit later the same afternoon put 2_865 back — along with the pre-⑭ comment trail,
    #: which is what makes it read as intentional rather than as the lost hunk it was. Nothing could
    #: go red: the only assertion here is `measured > cap`, so a pin that moves UP is invisible by
    #: construction, and the three slices' friction was spent silently. Pinned at 2_570, the file's
    #: EXACT measured size — ⑯ set 2_571 against a file that already measured 2,570, which is the
    #: off-by-one MAX_SLACK is deliberately loose enough to tolerate.
    "apps/web/src/viewer/app.ts": 2_570,   # detailing -> tools/detailingSection.ts (2_630 -> 2_571).   # content + family library -> tools/contentLibrarySection.ts (2_757 -> 2_630).   # interactive annotation -> tools/annotationSection.ts (2_865 -> 2_757). The file was AT this pin with zero headroom, which is why the roadmap row calling it "97%, ~136 lines" was corrected in the same pass.   # CAD command line -> cadBar.ts, which also gained the R29 prompt loop (2_885 -> 2_865). The 39-line inline block became a 10-line mount call; the ratchet is why the interactive mode went into a new module instead of on top of app.ts.   # clash rail -> tools/clashPanel.ts (2_944 -> 2_885)
    # Pinned at its EXACT measured size, not above it. qaSection.ts became the file every reach fix
    # lands in and reached 1,373 lines while unpinned - the same accumulation app.ts and client.ts
    # already have entries for. Pinned before it needs splitting rather than after: a ratchet added
    # at the point of pain only ratifies the pain.
    # 1_373 -> 1_360: the shared-parameter read + retire moved out to sharedParamsPanel.ts. The pin
    # fired on the commit that added the retire flow (1,439 > 1,373) and the answer was to extract,
    # not to raise - the same call the /finance extraction made earlier the same day. Re-tightened
    # to the new exact count rather than left at 1_373, because 13 lines of slack is 13 lines the
    # next addition spends without anyone deciding to.
    "apps/web/src/viewer/tools/qaSection.ts": 1_334,   # v0.3.1134: blank import gap closed (1_335 -> 1_334) while geometry results now show sourced basis.   # alignment check -> tools/alignmentPanel.ts (1_348 -> 1_335). The ratchet is why: adding the R41 yaw fit inline pushed this file 17 lines over and the gate refused, so the panel was extracted instead and came back three lines.
    # Pinned at its EXACT measured size on 2026-08-09, BEFORE it needs splitting — the third-largest
    # hand-written file in the tree and the only one of that size with no ratchet. The qaSection entry
    # above records why the timing matters: "a ratchet added at the point of pain only ratifies the
    # 2_546 → 2_516 (v0.3.1000): the model-elements block moved to tiedElements.ts so the
    # lifecycle card could mount on every tied GUID without growing this file.
    "apps/web/src/portal/register/register.ts": 2_516,
}

#: Exempt because a human never reads them top-to-bottom. Name them, never infer them.
EXEMPT_SUBSTRINGS = (
    "/vendor/",           # vendored upstream copies — re-synced by overwrite, never hand-edited
    "schema.d.ts",        # generated from the OpenAPI schema
    "/node_modules/",
    "/dist/",
    "/.venv/",
    "package-lock.json",
    "demoData.json",      # a captured snapshot, regenerated by build_demo_data.py
    "/migrations/versions/",   # alembic autogenerate output; hand-editing one is already the bug
)


def tracked_source():
    """Files git knows about — not the working tree, so build output can never enter the budget."""
    out = subprocess.run(
        ["git", "ls-files", "*.py", "*.ts", "*.tsx", "*.js"],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    for rel in out.stdout.splitlines():
        rel = rel.strip().replace("\\", "/")
        if not rel or any(s in "/" + rel for s in EXEMPT_SUBSTRINGS):
            continue
        path = os.path.join(ROOT, rel)
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                yield rel, sum(1 for _ in fh)
        except OSError:
            continue


sizes = sorted(tracked_source(), key=lambda kv: -kv[1])
check("the source tree is readable at all", len(sizes) > 100, f"{len(sizes)} files measured")

over = [(rel, n) for rel, n in sizes if n > CEILING]
check(
    f"no hand-written file exceeds {CEILING} lines",
    not over,
    "; ".join(f"{rel}={n}" for rel, n in over[:5]) or "",
)

measured = dict(sizes)

# A per-file ratchet keyed by PATH silently stops ratcheting the moment the path changes — a rename,
# a move, or an exemption that starts matching would drop the entry and this check would go green by
# measuring nothing. So assert the subjects are present BEFORE asserting their sizes, individually
# rather than in aggregate: an aggregate non-empty check cannot see a dead entry beside a live one.
missing = [rel for rel in PER_FILE if rel not in measured]
check(
    "every per-file ratchet still names a file that exists",
    not missing,
    "; ".join(missing) or f"{len(PER_FILE)} tracked",
)

grew = [(rel, measured[rel], cap) for rel, cap in PER_FILE.items()
        if rel in measured and measured[rel] > cap]
check(
    "no file under an extraction ratchet has grown",
    not grew,
    "; ".join(f"{rel}={n} > {cap}" for rel, n, cap in grew)
    or "; ".join(f"{rel}={measured[rel]}/{cap}" for rel, cap in PER_FILE.items() if rel in measured),
)

#: The check above is one-directional — it asks whether a FILE grew past its pin, and is silent about
#: a PIN that moves up past its file. `PER_FILE`'s own docstring says the numbers are "**Only ever
#: revised DOWN**", and until 2026-08-29 that was prose with nothing behind it. It failed exactly the
#: way prose fails: three shipped extractions (R39-DECOMP-VIEWER ⑭⑮⑯, 2_865 -> 2_571) were undone
#: when an unrelated lane's commit to this shared file carried the pre-⑭ line back in, comment trail
#: and all. Every gate stayed green, because a raised pin is a WIDER bound and no assertion here was
#: looking up. **An extraction without a ratchet is a rearrangement** — the sentence already in this
#: file — and a ratchet that can be silently unwound is the same thing one commit later.
#:
#: Enforced as SLACK rather than as history, so it needs no base ref and works in a fresh clone: a
#: pin that sits far above its file is either a revert or an extraction nobody ratcheted, and both
#: are the defect. The bound is loose on purpose. Measured across the whole map the day this landed,
#: legitimate slack was 0, 0, 0 and 0 lines — every pin sat EXACTLY on its file, which is what the
#: qaSection note ("13 lines of slack is 13 lines the next addition spends without anyone deciding
#: to") asks for. The one non-zero case was ⑯'s own off-by-one. So 25 is roughly an order of
#: magnitude above any observed honest value and an order of magnitude below the 295-line revert it
#: is here to catch: tight enough to fail on the real event, loose enough that nobody has to re-pin
#: for a one-line deletion. Deleting more than that from a ratcheted file and lowering its pin in
#: the same commit is not an obstacle — it is the discipline this whole map exists to impose.
#:
#: **WHAT THIS DOES NOT DO, stated because the first draft of this comment claimed otherwise.** It
#: does *not* enforce "only ever revised DOWN" — it enforces "a pin must not sit far above its
#: file", and those are different assertions. A commit that raises a pin AND grows the file to match
#: passes both checks with slack 0; so would the very incident above, if the same stale copy had
#: carried `app.ts` back to 2,865 lines alongside the pin. Down-only is a claim about HISTORY and
#: cannot be decided from the working tree, which is the price of needing no base ref. What is left
#: uncovered is the case the docstring above already routes to review — "raising an entry is a
#: deliberate act that should be argued for in the commit message" — and a deliberate raise is
#: exactly what a reader can see in a diff. The silent case, a pin moving up under a file that did
#: not, is the one a reader cannot see, and it is the one now covered. *A gate whose scope is
#: narrower than its claim* is a defect this file names one screen up; the fix is the honest label,
#: not a wider promise.
#:
#: **KNOWN FALSE POSITIVE: two concurrent extractions from the same pinned file, merged.** Each
#: branch measures a tree containing only its own cut, so each pin is correct on its branch and
#: neither describes the union — the merged file sits below the surviving pin by the other branch's
#: delta, and this check reds `main` on a merge where no individual change was wrong. That is the
#: mirror image of the case the `client.ts` entry already records, where the five-way seam merge
#: (#316-#320) had to go UP by one post-merge for the same reason, and it is the accepted
#: `strict: false` race in `docs/roadmap-directions.md` wearing a different hat. Left as a failure
#: rather than tuned away: the bound cannot separate it from a single reverted slice (both are
#: 59-127 lines here), the merged pin genuinely IS wrong until someone fixes it, and the message
#: below names the exact number to write. Lower the pin to the merged measurement; do not raise
#: MAX_SLACK, which would spend the whole gate to avoid a one-line correction.
MAX_SLACK = 25
slack = [(rel, measured[rel], cap) for rel, cap in PER_FILE.items()
         if rel in measured and cap - measured[rel] > MAX_SLACK]
check(
    f"no extraction ratchet sits more than {MAX_SLACK} lines above its file",
    not slack,
    "; ".join(f"{rel}: pin {cap} vs {n} lines — {cap - n} slack, lower the pin to {n}"
              for rel, n, cap in slack)
    or "; ".join(f"{rel}=+{cap - measured[rel]}" for rel, cap in PER_FILE.items() if rel in measured),
)

# The ratchet only ratchets if somebody can see the headroom. Print the top of the list every run so
# a file approaching the ceiling is visible BEFORE it crosses and blocks somebody mid-sprint.
print("\n  largest hand-written files:")
for rel, n in sizes[:8]:
    room = CEILING - n
    flag = "  <-- at the ceiling" if room < 400 else ""
    print(f"    {n:>6}  {rel}{flag}")

# A budget nobody can act on is decoration. If the worst file is over the *target*, say what to do —
# the seam is the fix, and the roadmap item that owns it is named so this points somewhere real.
TARGET = 3_000
worst_rel, worst_n = sizes[0]
if worst_n > TARGET:
    print(
        f"\n  NOTE: {worst_rel} is {worst_n} lines, over the {TARGET}-line target.\n"
        f"        Roadmap SCALE-SEAM owns bringing this down by splitting along domain seams.\n"
        f"        Lower CEILING here as each extraction lands — that is what makes it a ratchet."
    )

# --- the public demo snapshot: a BYTE ceiling, because lines are meaningless for captured JSON ----
# `demoData.json` was listed in EXEMPT_SUBSTRINGS above, which read as "deliberately unbounded" and
# was in fact decorative: `tracked_source()` globs *.py *.ts *.tsx *.js, so a .json file was never in
# the population the exemption excludes it from. NOTHING bounded this file's bytes.
#
# It matters because this is a SHIPPED PUBLIC SURFACE — every visitor to the Pages demo downloads it
# on a first impression, much of it on mobile. Widening the register fill loop in build_demo_data.py
# doubles the payload with no signal that anything changed.
#
# A ratchet, in the same spirit as CEILING and PER_FILE above — but deliberately a SEPARATE
# concept, not an entry in PER_FILE: those are LINE counts for hand-written source, this is
# BYTES for a captured artifact. Lines are meaningless for generated JSON. This number comes DOWN
# as the snapshot gets leaner
# and must never be raised to accommodate a bigger capture. If a change needs more bytes, the
# question to answer first is what a reader learns from them.
DEMO_SNAPSHOT = os.path.join(ROOT, "apps", "web", "src", "demo", "demoData.json")
DEMO_MAX_BYTES = 1_500_000
if os.path.exists(DEMO_SNAPSHOT):
    _demo_n = os.path.getsize(DEMO_SNAPSHOT)
    check(f"public demo snapshot is within {DEMO_MAX_BYTES:,} bytes",
          _demo_n <= DEMO_MAX_BYTES,
          f"{_demo_n:,} bytes — regenerate with a smaller `count=` in build_demo_data.py's register "
          f"fill loop rather than raising this ceiling")
    print(f"  demo snapshot: {_demo_n:,} bytes of {DEMO_MAX_BYTES:,} "
          f"({100 * _demo_n // DEMO_MAX_BYTES}% of ceiling)")

print()
#: --- The RATCHET'S OWN NARRATIVE, checked ------------------------------------------------------
#: Each entry above carries a history written by hand — "(1436 -> 1374)", "(1374 -> 1339)", ... —
#: recording what every slice took off the file. The CAP is asserted; that prose was not, and on
#: 2026-09-03 it drifted twice in one afternoon. PR #402 shipped "(1173 -> 1132)" beside a pin of
#: 1131 and a human reviewer caught it, not a test. (87) nearly repeated it, because `wc -l` reads
#: one higher than this file's own newline count on a file ending in a newline.
#:
#: TWO WAYS THIS PATTERN SILENTLY SKIPPED ENTRIES while I wrote it, both found by running it:
#:   1. older entries use underscores ("2_000 -> 1966"), so a plain \\d+ parsed fewer pairs;
#:   2. the v0.3.1124 entry reads "(2_769 -> 2_731, under the 2_752 pin they had broken)", so
#:      requiring a closing paren dropped it and manufactured a gap between its NEIGHBOURS -
#:      a false break in a check whose whole job is reporting breaks.
#: Both produced a smaller set and no error, which is the defect this ratchet exists to catch,
#: committed twice inside the catcher. Match loosely and strip, never require the tidy form.
_NUM = r"\d[\d_]*"


def _history_pairs(comment):
    out = []
    for a, b in re.findall(rf"\(({_NUM}) -> ({_NUM})", comment):
        out.append((int(a.replace("_", "")), int(b.replace("_", ""))))
    return out


#: One file's newest history entry legitimately disagrees with its cap. `viewer/app.ts` records
#: "(2_630 -> 2_571)", which is what slices ⑭⑮⑯ measured on 2026-08-27; the pin was RESTORED to
#: 2_570 on 2026-08-29, and this file's own comment above already calls that off-by-one deliberate
#: and tolerated. Editing the history to 2_570 would make the check pass by falsifying what a slice
#: measured - the mirror image of adjusting a check until it passes. Exempt it and say why.
_CAP_AGREEMENT_EXEMPT = {
    "apps/web/src/viewer/app.ts":
        "pin restored to 2_570 on 2026-08-29 after the ⑭⑮⑯ history was written at 2_571",
}


_SRC_LINES = open(__file__, encoding="utf-8").read().split("\n")
for _path, _cap in PER_FILE.items():
    _line = next((ln for ln in _SRC_LINES if f'"{_path}": ' in ln and "#" in ln), None)
    _pairs = _history_pairs(_line) if _line else []
    if len(_pairs) < 2:
        continue
    #: A newer entry may START above the previous RESULT: files GROW between slices, and the
    #: v0.3.1124 entry records exactly that - 18 lines of new response fields pushed client.ts
    #: from 2_752 to 2_769 and turned this very check red, which is the ratchet working. What
    #: cannot happen is a newer entry starting BELOW the previous result: lines would have left
    #: the file with no slice recording it. Demanding strict equality flags every legitimate
    #: growth, and a check that cries wolf gets ignored - which is how a real off-by-one hides.
    _breaks = [(x, y, a, b) for (x, y), (a, b) in zip(_pairs, _pairs[1:]) if x < b]
    check(f"the {_path} history never loses lines it did not record",
          not _breaks,
          "; ".join(f"{a}->{b}" for a, b in _pairs[:4])
          + f" ... {len(_pairs)} entries. "
          + (f"BREAK: {_breaks[0][0]}->{_breaks[0][1]} follows {_breaks[0][2]}->{_breaks[0][3]} - the "
             "newer entry starts BELOW the older result, so lines left the file with no slice "
             "recording it." if _breaks
             else "no entry starts below the previous result"))
    check(f"the newest {_path} history entry ends at the enforced cap",
          _pairs[0][1] == _cap or _path in _CAP_AGREEMENT_EXEMPT,
          f"newest entry says {_pairs[0][0]} -> {_pairs[0][1]}, cap is {_cap}. THIS IS THE CHECK "
          "PR #402 NEEDED: the assertion was right and the sentence beside it was wrong. Take the "
          "number from this file's own count, never from `wc -l`, which reads one higher on a "
          "trailing newline.")

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_file_sizes OK")
