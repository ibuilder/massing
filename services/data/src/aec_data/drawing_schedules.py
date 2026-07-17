"""Computed door / window / room schedules (W11 C4 / W10-6) — the tabular half of a CD set, extracted
from `drawing.py`.

A pure leaf: values come straight off the model elements (marks, sizes, types, levels, quantities) with
no dependency on the plan/section geometry helpers, so this module imports nothing from `drawing.py` (no
cycle). `drawing.py` imports `schedules` here for its PDF path and re-exports the three public functions
(`schedules` / `schedule_csv` / `schedule_svg`) so `drawing.schedules` etc. keep working unchanged.
"""
from __future__ import annotations

import ifcopenshell


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def schedules(model: ifcopenshell.file) -> dict:
    """W11 C4: compute door / window / room schedules from the model — the tabular half of a CD set.
    Values come straight from the elements (marks, sizes, types, levels, areas). Returns
    {doors, windows, rooms} each {columns:[...], rows:[[...]]}."""
    import ifcopenshell.util.element as ue
    import ifcopenshell.util.unit as uu

    scale = uu.calculate_unit_scale(model)                    # metres per file unit

    def _lvl(el):
        st = ue.get_container(el) or ue.get_aggregate(el)
        return getattr(st, "Name", None) or ""

    def _m(v):
        try:
            return f"{float(v) * scale:.2f}" if v is not None else ""
        except (TypeError, ValueError):
            return ""

    def _type(el):
        t = ue.get_type(el)
        if t is not None and getattr(t, "Name", None):
            return t.Name
        return getattr(el, "PredefinedType", None) or ""

    def _opening(el):                                         # marks default from GUID tail when unnamed
        return getattr(el, "Name", None) or (el.GlobalId[:8])

    doors = [[_opening(d), _m(getattr(d, "OverallWidth", None)), _m(getattr(d, "OverallHeight", None)),
              _type(d), _lvl(d)] for d in model.by_type("IfcDoor")]
    windows = [[_opening(w), _m(getattr(w, "OverallWidth", None)), _m(getattr(w, "OverallHeight", None)),
                _type(w), _lvl(w)] for w in model.by_type("IfcWindow")]
    def _q(v):                                                # a numeric quantity → 2dp text, else blank
        try:
            return f"{float(v):.2f}" if v is not None else ""
        except (TypeError, ValueError):
            return ""

    rooms = []
    for s in model.by_type("IfcSpace"):
        q = ue.get_pset(s, "Qto_SpaceBaseQuantities") or {}    # W10-6: IfcElementQuantity depth
        area = q.get("NetFloorArea") or q.get("GrossFloorArea")
        perim = q.get("NetPerimeter") or q.get("GrossPerimeter")
        vol = q.get("NetVolume") or q.get("GrossVolume")
        rooms.append([getattr(s, "Name", None) or "", getattr(s, "LongName", None) or "",
                      f"{float(area):.2f}" if area else "", _q(perim), _q(vol), _lvl(s)])

    return {
        "doors": {"columns": ["Mark", "Width (m)", "Height (m)", "Type", "Level"],
                  "rows": sorted(doors, key=lambda r: r[0])},
        "windows": {"columns": ["Mark", "Width (m)", "Height (m)", "Type", "Level"],
                    "rows": sorted(windows, key=lambda r: r[0])},
        "rooms": {"columns": ["No.", "Name", "Area (m²)", "Perimeter (m)", "Volume (m³)", "Level"],
                  "rows": sorted(rooms, key=lambda r: r[0])},
    }


_SCHED_TITLE = {"doors": "DOOR SCHEDULE", "windows": "WINDOW SCHEDULE", "rooms": "ROOM SCHEDULE"}


def schedule_csv(model: ifcopenshell.file, kind: str | None = None) -> str:
    """W10-6: the computed door/window/room schedule(s) as **CSV** for spreadsheets / procurement /
    submittals. `kind` = doors|windows|rooms for one; omit for all three (a title row + blank line between).
    Finishes the schedule views into the export pipeline alongside the SVG/PDF."""
    import csv
    import io

    data = schedules(model)
    kinds = [kind] if kind in data else list(data)
    buf = io.StringIO()
    w = csv.writer(buf)
    for i, k in enumerate(kinds):
        if i:
            w.writerow([])
        w.writerow([_SCHED_TITLE.get(k, k.upper())])
        w.writerow(data[k]["columns"])
        for row in data[k]["rows"]:
            w.writerow(row)
    return buf.getvalue()


def schedule_svg(model: ifcopenshell.file, kind: str = "doors") -> dict:
    """Render one schedule (doors|windows|rooms) as a standalone SVG table. Returns {svg, kind, rows}."""
    data = schedules(model).get(kind)
    if data is None:
        raise ValueError(f"unknown schedule {kind!r}; have doors|windows|rooms")
    cols, rows = data["columns"], data["rows"]
    title = _SCHED_TITLE.get(kind, kind.upper())
    col_w = 40.0
    row_h = 6.0
    pad = 8.0
    tw = col_w * len(cols)
    th = row_h * (len(rows) + 1)
    w = tw + 2 * pad
    h = th + 2 * pad + 8

    def cell(cx, cy, text, header=False, anchor="start"):
        cls = "sc-h" if header else "sc-c"
        x = cx + (2 if anchor == "start" else col_w / 2)
        return f'<text class="{cls}" x="{round(x, 2)}" y="{round(cy + 4, 2)}" text-anchor="{anchor}">{_esc(str(text))[:22]}</text>'

    parts = [f'<text class="sc-t" x="{pad}" y="{pad}">{title}</text>']
    y0 = pad + 6
    # header row
    parts.append(f'<rect class="sc-hr" x="{pad}" y="{round(y0, 2)}" width="{tw}" height="{row_h}"/>')
    for i, cname in enumerate(cols):
        parts.append(cell(pad + i * col_w, y0, cname, header=True))
    # body rows + grid
    for r, row in enumerate(rows):
        ry = y0 + (r + 1) * row_h
        for i, val in enumerate(row):
            parts.append(cell(pad + i * col_w, ry, val))
    for i in range(len(cols) + 1):                            # vertical rules
        vx = pad + i * col_w
        parts.append(f'<line class="sc-g" x1="{round(vx, 2)}" y1="{round(y0, 2)}" x2="{round(vx, 2)}" y2="{round(y0 + th, 2)}"/>')
    for r in range(len(rows) + 2):                            # horizontal rules
        ry = y0 + r * row_h
        parts.append(f'<line class="sc-g" x1="{pad}" y1="{round(ry, 2)}" x2="{round(pad + tw, 2)}" y2="{round(ry, 2)}"/>')

    style = (".sc-t{font:bold 4px sans-serif;fill:#000}.sc-h{font:bold 2.6px sans-serif;fill:#000}"
             ".sc-c{font:2.6px sans-serif;fill:#222}.sc-g{stroke:#333;stroke-width:0.2}"
             ".sc-hr{fill:#e8e8e8;stroke:none}")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{round(w, 1)}mm" height="{round(h, 1)}mm" '
           f'viewBox="0 0 {round(w, 2)} {round(h, 2)}"><style>{style}</style>'
           f'<rect x="0" y="0" width="{round(w, 2)}" height="{round(h, 2)}" fill="#fff"/>'
           + "".join(parts) + "</svg>")
    return {"svg": svg, "kind": kind, "rows": len(rows)}
