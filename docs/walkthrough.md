# Demo walkthrough — script + written tour

A ~3-minute product demo, scene by scene. Use it as a **video script** (narration + on-screen
actions + timing) or follow it as a **written click-through**. Pairs with the
[Guides](guide.html). Everything shown is real, shipped behavior.

> Setup before recording: run the desktop app (or the live demo for the viewer parts), a clean
> window, and the **All roles** persona so every tool is visible. Skip the welcome with the **?**
> button if it appears.

---

## The 3-minute video

**0:00 — Hook (title card → app)**
> *Narration:* "Building a project usually means a feasibility tool, a BIM tool, a construction
> platform, and a handover tool — none of them talking. This is all of it, on one model."
*On screen:* the landing page hero, then cut into the app on the Model workspace.

**0:15 — One model, three workspaces**
> "Everything keys off the building's IFC model — and you can author it right here in the browser, not
> just view it. Three workspaces — Model, Construction, Finance — share it."
*On screen:* click between the Model / Construction / Finance tabs; open a sample, orbit once, click an
element to show its docked Properties; flash the authoring rail — **New model**, the **Draft** tools,
**◈ Edit in place** dragging an element, the **model browser** grouping by discipline.

**0:35 — Generate a building from zoning ⭐**
> "Start from nothing but a lot and its zoning. Enter the lot, FAR, setbacks, a height limit…"
*On screen:* Finance → the **Generate from zoning** panel; type the inputs; tick frame + units +
envelope + core.
> "…click Estimate yield for an instant read, then Generate — and it builds a real IFC building."
*On screen:* click **Estimate yield** (numbers appear), then **Generate IFC model + apply**; cut to
the Model workspace showing the generated tower (or play the generate→build GIF).

**1:05 — Test Fit & optimize**
> "Test Fit fits a unit mix to the floor plate and compares schemes — then finds the highest-yield
> layout automatically."
*On screen:* Test Fit panel → **Compare schemes** (table), then **⚡ Optimize**.

**1:25 — Underwrite the deal**
> "Build the cost budget — hard and soft — balance the capital in Sources & Uses, and watch the
> returns update live. Guardrails flag anything that's too good to be true."
*On screen:* cost budget panel → Apply; Sources & Uses; the sticky returns bar (IRR/EM) + a
guardrail badge.

**1:50 — The investor package**
> "One click turns the live numbers into an investment memo and a pitch deck."
*On screen:* click **📄 Investment memo**, flip through the PDF; then **📊 Pitch deck**.

**2:10 — Run the job**
> "When it's time to build, the GC portal runs construction — RFIs, change orders, pay apps — and a
> 4D slider scrubs the build sequence right on the model."
*On screen:* Construction dashboard; open an RFI; the Schedule **⏱ 4D sequence** slider moving (the
building appears floor by floor); the **Ask AI** box answering "what's overdue?".

**2:25 — Money on the model (Budget + 5D)**
> "The GMP budget builds itself from cost codes, buyout and staffing — budget to forecast, with the
> variance — and you can see the cost right on the model."
*On screen:* **Schedule → Budget** (the GMP table + cash-flow S-curve); back in the Model, click an
element for its **5D** cost readout, then the **cost heatmap** coloring the building by spend.

**2:35 — Hand it over**
> "At the finish, punchlist, commissioning, and a COBie turnover package — closing the loop on the
> same model you started with."
*On screen:* punchlist verify (with photo); export COBie / turnover package.

**2:50 — Close**
> "One IFC model, acquisition to turnover. Open, self-hosted, free to run. Try the live demo."
*On screen:* landing page; URL **massing.build**.

---

## Written click-through (no narration)
1. **Model** workspace → **Open ▾ → a sample** → orbit, click an element for its docked **📋 Properties**
   (Type/Instance). Open the **model browser** (Tree): switch **group-by** (level / discipline / IFC
   class / type) and **search** to filter; click a leaf to select. Save a search as a **selection set**
   (Layers panel) and isolate it in one click.
2. **Author a model from scratch:** **New model** (blank or a starter template) → the **Draft** panel
   draws walls / columns / slabs / rooms on the active level (grid-snap). Turn on **◈ Edit in place**,
   select an element, and **drag the gizmo** to move it. **Manage levels** to rename or set elevations.
   Run **💥 Clash** to coordinate. Every edit re-authors the IFC by GUID, so links survive.
3. **Finance → Generate from zoning** → enter lot/FAR/setbacks → **Estimate yield** → **Generate IFC model + apply**.
4. **Model** → see the building. **Finance → Test Fit → Compare / ⚡ Optimize**.
5. **Finance** → cost budget → **Apply** → **Sources & Uses** → tune drivers → read the returns bar.
6. **📄 Investment memo** + **📊 Pitch deck** PDFs. Then the capital chain: **sync the GMP** to hard cost, model **construction-loan draws**, export the **lender draw-request** PDF.
7. **＋ New** project → **Construction** → create an RFI → **Schedule → 4D sequence** scrub → **Ask AI**.
8. **Schedule → Budget** (GMP table + cash-flow) → back in **Model**, click an element for its **5D** cost → open the **cost heatmap**. Generate a **pay app (G702/G703)**.
9. Invite a teammate (account menu) with a **capability** + **party** role (multi-user).
10. **Punchlist** verify → **COBie / turnover package** export.

## Recording tips
- 1080p, hide the cursor trail, slow the mouse. ~3 min keeps attention; a 60-sec cut (scenes at
  0:35, 1:25, 2:10) works for social.
- The **generate→build GIF** (`docs/img/generate-build.gif`) is a ready-made teaser if you don't
  want to record the generate step live.
