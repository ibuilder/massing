# User guide

How to use Massing. If you have not installed it yet, start with
[getting started](../getting-started.md).

Read in this order the first time — each page assumes the one before it.

| # | Page | What you will be able to do |
| --- | --- | --- |
| 1 | **[The seven rooms](rooms.md)** | Find anything. Understand why the navigation is the same for every role. |
| 2 | **[Authoring the model](authoring.md)** | Start a model from nothing and draw real IFC; edit somebody else's without breaking it. |
| 3 | **[Drawings and specs](drawings.md)** | Generate a permit-ready document set, schedules and a spec manual from the model. |
| 4 | **[Records and registers](modules.md)** | Run RFIs, submittals, change orders, pay apps — and anchor them to elements. |
| 5 | **[Files in and out](files.md)** | Get your data in, and get it back out. |
| 6 | **[Troubleshooting](troubleshooting.md)** | Fix it when it does not work. |

## The three ideas the rest follows from

**One model, addressed by GUID.** Every element carries its IFC GlobalId, and every artifact — a pin, an
RFI, a cost line, a schedule activity, a work order — points at that GlobalId. Nothing is keyed to a
transient viewer id, which is why those artifacts still agree after the model is edited.

**IFC is the source of truth.** Not a proprietary database with IFC export bolted on. Drawings,
quantities, COBie and the proforma are all *derived*, so they are regenerable and cannot silently
disagree with the building.

**Breadth, deferred rather than deleted.** There are 133 registers. Nobody uses 133 things; roughly one
in eight features carries most daily use. So the product routes you to the ten things you touch today
and keeps the rest one keystroke away — reachable from a room, from an element, from the work queue, or
from **⌘K** by name.

## Related reading

- [Walkthrough](../walkthrough.md) — a guided 3-minute tour, if you would rather be shown.
- [Authoring a module](../authoring-modules.md) — add your own record type, no code.
- [Roles → views](../roles-views.md) — which role owns which room.
- [API reference](../reference/api.md) — driving it programmatically.
- [Architecture](../reference/architecture.md) — how the pieces fit.
