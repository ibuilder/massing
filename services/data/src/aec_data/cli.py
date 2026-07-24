"""The headless ``massing`` CLI (guide §8 + RECIPE-MACROS remainder) — exports, authoring, and the
CI model gate, all offline against an IFC file. Examples:

  python -m aec_data.cli index    model.ifc  out/model.props.json
  python -m aec_data.cli qto      model.ifc  out/qto.xlsx       --cost-map costs.json
  python -m aec_data.cli spaces   model.ifc  out/spaces.xlsx
  python -m aec_data.cli cobie    model.ifc  out/cobie.xlsx
  python -m aec_data.cli schedule model.ifc  out/schedule.xlsx  --mapping plan.csv
  python -m aec_data.cli new      out/model.ifc --storeys 3 --height 3.5
  python -m aec_data.cli run      model.ifc --recipe add_wall --params '{"start":[0,0],"end":[8,0]}'
  python -m aec_data.cli check    model.ifc --gate     # the CI gate: exit 1 on constraint ERRORS
"""
from __future__ import annotations

import argparse
import json
import sys

from . import cobie, properties_index, qto, schedule, spaces
from .xlsx import write_sheets


def _rows_to_sheet(rows: list[dict]) -> tuple[list[str], list[list]]:
    headers = list(rows[0].keys()) if rows else []
    return headers, [[r.get(h) for h in headers] for r in rows]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="massing")
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("index", "qto", "spaces", "cobie", "schedule"):
        p = sub.add_parser(name, help=f"export {name} from an IFC")
        p.add_argument("ifc")
        p.add_argument("out")
        p.add_argument("--cost-map", default=None)
        p.add_argument("--mapping", default=None)
    p = sub.add_parser("new", help="write a blank authoring model (levels + ground reference)")
    p.add_argument("out")
    p.add_argument("--name", default="New Model")
    p.add_argument("--storeys", type=int, default=3)
    p.add_argument("--height", type=float, default=3.5)
    p.add_argument("--size", type=float, default=30.0)
    p = sub.add_parser("run", help="apply a GUID-stable edit recipe to an IFC")
    p.add_argument("ifc")
    p.add_argument("--recipe", required=True)
    p.add_argument("--params", default="{}", help="JSON params for the recipe")
    p.add_argument("-o", "--out", default=None, help="output path (default <stem>_edited.ifc)")
    p = sub.add_parser("check", help="constraint/QA check; with --gate exit 1 on errors")
    p.add_argument("ifc")
    p.add_argument("--gate", action="store_true", help="fail (exit 1) when errors are found")
    p.add_argument("--json", action="store_true", dest="as_json", help="print the full JSON report")
    args = ap.parse_args(argv)

    if args.command == "new":
        from . import massing as ms
        path = ms.generate_blank_ifc(args.out, name=args.name, storeys=args.storeys,
                                     storey_height=args.height, ground_size=args.size)
        print(f"new: {args.storeys} storeys @ {args.height} m -> {path}")
        return 0

    if args.command == "run":
        from pathlib import Path

        from . import edit
        try:
            params = json.loads(args.params)
        except ValueError as e:
            print(f"run: --params is not valid JSON: {e}", file=sys.stderr)
            return 2
        if args.recipe not in edit.RECIPES:
            print(f"run: unknown recipe {args.recipe!r}; known: {', '.join(sorted(edit.RECIPES))}",
                  file=sys.stderr)
            return 2
        out = args.out or str(Path(args.ifc).with_name(Path(args.ifc).stem + "_edited.ifc"))
        result = edit.apply_recipe(args.ifc, args.recipe, params, out)
        print(f"run: {args.recipe} -> {out}  {json.dumps(result, default=str)[:200]}")
        return 0

    if args.command == "check":
        from . import constraints
        r = constraints.check_file(args.ifc)
        if args.as_json:
            print(json.dumps(r, indent=1))
        else:
            print(f"check: {r['issue_count']} issue(s) — {r['errors']} error(s), "
                  f"{r['warnings']} warning(s) over {r['checked']['openings']} opening(s), "
                  f"{r['checked']['storeys']} storey(s)")
            for i in r["issues"]:
                print(f"  {i['severity'].upper():7} {i['kind']:22} {i['ifc_class']} "
                      f"{i['name']!r}: {i['detail']}")
        return 1 if (args.gate and r["errors"]) else 0

    if args.command == "index":
        idx = properties_index.index_file(args.ifc, args.out)
        print(f"index: {idx['counts']} -> {args.out}")
        return 0

    if args.command == "qto":
        rows = qto.takeoff_file(args.ifc, args.cost_map)
        total = sum(r["amount"] for r in rows if r.get("amount"))
        write_sheets(args.out, {"QTO": _rows_to_sheet(rows)})
        print(f"qto: {len(rows)} elements, estimate total = {total:,.2f} -> {args.out}")
        return 0

    if args.command == "spaces":
        rows = spaces.space_schedule_file(args.ifc)
        write_sheets(args.out, {"Spaces": _rows_to_sheet(rows)})
        print(f"spaces: {len(rows)} spaces -> {args.out}")
        return 0

    if args.command == "cobie":
        sheets = cobie.cobie_file(args.ifc)
        write_sheets(args.out, {name: _rows_to_sheet(rows) for name, rows in sheets.items()})
        print("cobie: " + ", ".join(f"{k}={len(v)}" for k, v in sheets.items()) + f" -> {args.out}")
        return 0

    if args.command == "schedule":
        acts = schedule.schedule_file(args.ifc, args.mapping)
        rows = [{"id": a["id"], "name": a["name"], "start": a["start"],
                 "finish": a["finish"], "element_count": len(a["guids"]),
                 "guids": json.dumps(a["guids"])} for a in acts]
        write_sheets(args.out, {"Schedule": _rows_to_sheet(rows)})
        print(f"schedule: {len(acts)} activities -> {args.out}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
