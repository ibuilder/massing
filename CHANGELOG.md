# Changelog

All notable changes to the AEC BIM Platform. Releases are signed, auto-updating desktop builds
(Windows / macOS / Linux); the updater always serves the latest. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/).

## v0.1.29 — render mode (M2 start)
- **Viewer render mode** (◓ toolbar) — a directional **sun with soft (PCF) shadows**, hemisphere
  sky/ground fill + fill light, **ACES tone mapping** and sRGB output, and a shadow-catching ground
  plane. Off by default (flat shading stays the cheap default); re-applies as new models load.
  First step toward Revit/Rhino/Matterport-style rendering.

## v0.1.28 — faster large-model loading
- **Download progress** — large models stream with a live "downloading N% (x/y MB) → preparing
  geometry" label instead of a generic spinner that looked frozen.
- **ETag revalidation** — `model.frag` now serves an ETag + `must-revalidate`: unchanged models
  re-open instantly via **304**, while a republished/edited model is always refetched (fixes a
  stale-cache bug where an immutable 1-year cache served the old geometry forever).

## v0.1.27 — computational graph (M4 start)
- **Dynamo-style node graph** over the pure engines: `GET /compute/nodes` (palette) and
  `POST /compute/graph` run a {nodes, edges} graph in dependency order (zoning → structure / takt /
  cost → yield-on-cost). Zero-touch: function params become input ports, dict returns become outputs.

## v0.1.26 — IFC materials & surface colours (M1 start)
- **Materials & surface styles** — generated/dome models get an IfcMaterial + IfcSurfaceStyle colour
  per element class (concrete, glazing, steel, vegetation…), so models carry real material data.

## v0.1.25 — gamified getting-started
- **Getting-started checklist** — a floating progress pill guides new users through the 6 core
  actions (load a model, generate, test-fit, budget, project, memo) with a progress bar + celebration.

## v0.1.22 — 4D & the vertical assembly line
- **4D construction sequencing** — map model elements onto a takt plan; **scrub the build sequence
  in the viewer** (a slider isolates what's built to date).
- **Takt / line-of-balance chart** (SVG) and an **egress check** (two means + travel distance).

## v0.1.21 — lean & multi-period billing
- **Lean / Last-Planner PPC** — a weekly-plan module + Plan-Percent-Complete analytics with reasons
  for non-completion.
- **Multi-period pay apps** — roll completed-to-date across successive draws; retainage release on
  the final application.

## v0.1.20 — underwriting realism (II)
- **Capital reserves above NOI**, **citable guardrail bands** (sourced from the benchmarks), and
  **Test Fit optimize seeded from the live project** (real land + cost budget).

## v0.1.19 — built-world techniques (Willis · Salvadori · CM/RE research)
- **Takt / line-of-balance** scheduling with a just-in-time delivery plan (R2).
- **Lean PPC** engine (R4) and citable **benchmarks + a comparables module** (R5).

## v0.1.18 — structural-system advisor (R3)
- Pick a plausible system by height/span (flat-plate · shear-core · outrigger) with rough member
  sizing + a load-path read — driving the generated frame (after Salvadori).

## v0.1.17 — form follows finance (R1)
- Generative massing / Test Fit reward **daylight-limited rentable depth** + core efficiency — the
  highest rentable yield wins, not max FAR (after Carol Willis).

## v0.1.16 — underwriting realism (I) + Finance revamp
- **Risk-adjusted** specialty/operating revenue + **guardrails** that flag returns outside market
  bands. Finance reorganized into sub-tabs with a sticky live-returns bar.

## v0.1.15 — pitch deck
- One-click **pitch-deck PDF** variant of the investment memo (B6).

## v0.1.14 — generative optimize + real parcels
- **Generative design** sweeps unit-mix × parking and ranks by yield-on-cost (A5); **real lot
  polygons** drive the program by shoelace area (A6).

## v0.1.13 — Test Fit + property/tax
- **Test Fit** — corridor unit-mix layout, parking solver, scheme compare (A1/A3/A4); **property &
  tax assumptions** feeding OPEX (B3).

## v0.1.11 — specialty assets
- On-site **energy** (solar/wind/battery/rainwater) and **vertical-farm (PFAL)** revenue flow into
  capex / revenue / opex (B4).

## v0.1.10 — developer cost portal
- Line-item **hard/soft cost budgets** (B1), **Sources & Uses** (B2), and a one-click **investment
  memo PDF** (B5).

## v0.1.6–0.1.8 — accounts, AI & hardening
- **SSO** (Google / Microsoft / Procore) + a no-admin free-tier model; first-run **onboarding + tour**.
- **"Ask AI"** project assistant over a live snapshot; AI risk summaries + drafted RFIs.
- **Field capture** (offline photo → punchlist/observation, syncs on reconnect).
- Production hardening — rate limiting, security headers, auth-secret fail-safe, takeoff caching.
- Full generative lifecycle from zoning (frame + units + envelope + core).

## v0.1.0–0.1.5 — foundation
- **BIM viewer** (Three.js + Fragments, offline WASM), federation, clash, IDS, 2D drawings/sheets,
  in-viewer authoring round-trip.
- **GC portal** — config-driven modules (RFIs, submittals, change-order chain, daily, QA, safety…),
  CPM, pay apps, dashboards.
- **Development proforma** — S&U with interest-reserve circularity, XIRR/NPV/EM, JV waterfall,
  sensitivity + Monte Carlo.
- **Generative massing + family library**; free single-project **desktop app** with signed,
  auto-updating releases.
