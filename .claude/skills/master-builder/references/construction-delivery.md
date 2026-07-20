# Construction Delivery

How a project actually gets bought, built, sequenced, and controlled. Read this for delivery-method
selection, contracts, estimating, scheduling, procurement, and construction administration.

## Contents
1. Delivery methods (and when each fits)
2. Contract families (global)
3. Estimating — classes and drivers
4. Scheduling — CPM, pull planning, lookaheads, long-leads
5. Procurement, supply chain, and prefab/DfMA
6. Construction administration & controls
7. Quality, safety, and non-conformance
8. Tooling

---

## 1. Delivery methods (and when each fits)

The delivery method sets who holds which risk and when the price is known. Choose it to match the
owner's priorities among **cost certainty, speed, quality, and design control.**

- **Design-Bid-Build (DBB)** — design fully, then bid to a GC (usually low bid). Max design control,
  lowest collusion risk, but slowest and adversarial on changes. Common for public work.
- **Design-Build (DB)** — one entity for design + construction. Fast, single point of responsibility,
  fewer owner-side gaps; owner cedes some design control. Good for speed and clear programs.
- **Construction Manager at Risk (CMAR / CM/GC)** — CM joins in preconstruction for constructability
  and budgeting, then delivers under a **Guaranteed Maximum Price (GMP)**. Collaboration of DB with
  more owner design control. Common for complex institutional work.
- **Integrated Project Delivery (IPD)** — multiparty relational contract, shared risk/reward, shared
  BIM. Highest collaboration, best for complex projects with sophisticated owners.
- **EPC / turnkey** — Engineer-Procure-Construct, lump-sum, single accountability; dominant for
  industrial, energy, and infrastructure, and common internationally.
- **Public-Private Partnership (P3 / PPP)** — private finance + delivery + often operations (DBFO/M).
  For infrastructure and social assets; shifts lifecycle risk to the concessionaire.

Match to context: cost certainty + public accountability → DBB/GMP; speed → DB; complexity + owner
control → CMAR/IPD; infrastructure → EPC/P3.

---

## 2. Contract families (global)

Know the family; the clauses that fight are always the same: scope, price mechanism, time/EOT,
change/variation, payment, risk allocation, indemnity, LDs, dispute resolution.

- **AIA (US)** — A201 general conditions; A101/A102/A133 owner-contractor; B-series owner-architect.
- **ConsensusDocs (US)** — collaborative alternative to AIA.
- **FIDIC (international)** — the global standard for cross-border work: **Red** (build to employer's
  design), **Yellow** (design-build/plant), **Silver** (EPC/turnkey), **Green** (short form). Rainbow suite.
- **NEC4 (UK/international)** — collaborative, activity/option-based (Options A–F), proactive early-warning
  and programme management.
- **JCT (UK)** — traditional UK building contracts.

Internationally, FIDIC is usually the lingua franca; know which book matches the delivery method and
who carries design risk under it.

---

## 3. Estimating — classes and drivers

Never present an estimate without its **class** and basis; a ROM is not a bid. (AACE-style classes:)
- **Class 5 — ROM/order-of-magnitude** (concept): ±30–50%, from $/area or $/key.
- **Class 3 — budget/semi-detailed** (SD/DD): ±10–20%.
- **Class 1 — definitive / GMP / bid** (CDs): ±5–10%, quantity-take-off + priced subs.

Cost drivers to interrogate: location cost index (labor + material), building type/complexity,
structural system, floor-to-floor and façade ratio, site & foundations (the great cost wildcard),
MEP intensity, finishes level, schedule (acceleration costs money; so does carry), market conditions
(escalation), and procurement route. Always carry **escalation** and a **contingency** sized to the
design maturity and risk. State currency + date on every number.

---

## 4. Scheduling — CPM, pull planning, lookaheads, long-leads

- **CPM (Critical Path Method)** — the master schedule; the **critical path** is the chain with zero
  float that sets the finish date. Manage float, not just activities; protect the critical path.
- **Last Planner / pull planning** — the lean field method: the crews who do the work plan backward
  from milestones, make ready by removing constraints, and commit to weekly work plans. Measured by
  **PPC (Percent Plan Complete)**. Massing includes a Last Planner board for exactly this.
- **Lookaheads** — the rolling **4–6 week** (and 1-month) windows that turn the master schedule into
  actionable constraint-removal; the workhorse of field coordination.
- **Long-lead procurement** — the schedule killer. Switchgear, generators, elevators, chillers,
  curtain wall, structural steel, custom AHUs can carry many-month or year-plus lead times. Maintain
  a **long-lead expediting log** and release these early — often before CDs are complete. (This is a
  deliverable Matt has produced on live projects.)

---

## 5. Procurement, supply chain, and prefab/DfMA

- **Buy-out** — converting the estimate into awarded subcontracts and POs; scope-gap analysis is
  where budgets are won or lost.
- **Prefabrication / modular / DfMA (Design for Manufacture and Assembly)** — move work off the
  critical path and into a controlled factory: volumetric modules, panelized façades, MEP racks,
  bathroom pods. Trades speed, quality, and site-labor risk for early design lock and transport/
  logistics constraints. Increasingly essential where site labor is scarce or expensive.
- **Global supply chain** — lead times, tariffs, currency, and logistics belong in the schedule and
  the estimate, not as an afterthought — especially for cross-border projects.

---

## 6. Construction administration & controls

The daily machinery of building. Each artifact is both a communication and a contractual record:

- **RFI (Request for Information)** — formal question to the design team to resolve a gap/conflict.
  Good RFIs are specific, cite the document, propose a resolution, and flag cost/schedule impact.
- **Submittals** — shop drawings, product data, and samples the contractor submits for the design
  team to review against the contract documents before fabrication/installation. Track against the
  schedule; a late submittal is a late long-lead is a late project.
- **Change management** — change events → potential change orders → **change orders (COs)**, each with
  cost + time impact; track **change-event cost exposure** against contingency.
- **Payment applications** — **AIA G702/G703** (or local equivalent): the schedule of values, percent
  complete, stored materials, and retainage that drive the monthly draw. Ties directly to the lender
  draw (finance ref §5).
- **Coordination** — clash resolution and action items from the coordinated model / BCF (see
  `digital-toolkit.md`); resolve in the model, not in the field.
- **Cost & schedule controls** — earned value where warranted, budget vs. committed vs. forecast,
  and the lookahead as the operating rhythm.

These are exactly the workflows Matt's tools automate (RFI draft generation, submittal-log analysis,
Procore submittal-date automation via API/Selenium, pay-app generation) — reach for them to do the
work, not just describe it.

---

## 7. Quality, safety, and non-conformance

- **QA/QC** — QA is the system (procedures, ITPs, inspections); QC is the checking of the work.
  Benchmark mock-ups and first-of-kind inspections catch systemic defects early.
- **Non-Conformance Reports (NCRs)** and formal notices — document defective/nonconforming work,
  the disposition (rework/repair/accept-by-concession), and prevention. A paper trail that protects
  the project.
- **Safety** — the non-negotiable. OSHA (US, incl. OSHA 30), CDM Regulations (UK), local equivalents.
  Safety is a leading indicator of a well-run job; a chaotic site is an unsafe site and usually a
  late one. Design for safety and constructability, plan the high-risk sequences, and never let
  schedule pressure erode it.

---

## 8. Tooling

To run the work rather than just narrate it, prefer interoperable platforms and reach for the ones
already built:
- **Massing** GC portal (near-100 modules), 5D cost/schedule, ISO 19650 CDE, CPM schedule, TRIR
  safety tracking, Facility Condition Assessment — the integrated command layer on one IFC-keyed model.
- **FieldForge** — pay-per-use RFI Draft Generator and Submittals Log Analyzer for mid-size GCs.
- **gcPanel / ConstructAI** — Next.js + TypeScript + Tailwind construction-management dashboard,
  modular by real workflow (Contracts, Cost, Engineering, Field, Reporting, Resources, Safety) with a
  uniform list/form component structure.
- **Procore** and BuildingConnected in the commercial ecosystem; automate the repetitive workflow via
  their APIs.

Match the tool to the control it serves, and keep the data in open formats so it survives the project.

## Fabrication outputs — the honest boundary on machine formats

Turning a model into a **fabrication instruction** (a rebar bending file for a BVBS/BF2D bending machine,
a DSTV-NC file for a steel CNC line, a CAM toolpath) is a *consequential, near-irreversible* output: a
byte-wrong file makes a machine mis-bend or mis-cut real steel. Treat it like pouring concrete — gate it.
The doctrine (see `build-doctrine.md` §6): ship the **human-read schedule first** — a bar-bending
schedule with per-leg lengths, bend angles, shape family, cut length, and mass, which a detailer reads
and checks — and only emit the **machine format** once it is validated against the *authoritative spec*
(e.g. the BVBS guideline) **and** a real importer/validator, labeled with the exact format version.
Never present an unverified machine-format export as production-ready; a schedule a human catches errors
in is worth more than a machine file that silently mis-fabricates. Massing implements the schedule
(`GET /projects/{pid}/rebar/bbs` with leg/angle bending detail) and holds the BVBS byte-format export
behind that validation gate.
