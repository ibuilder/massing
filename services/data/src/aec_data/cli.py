"""Data service CLI (guide §8). Examples:

  python -m aec_data.cli index    model.ifc  out/model.props.json
  python -m aec_data.cli qto      model.ifc  out/qto.xlsx       --cost-map costs.json
  python -m aec_data.cli spaces   model.ifc  out/spaces.xlsx
  python -m aec_data.cli cobie    model.ifc  out/cobie.xlsx
  python -m aec_data.cli schedule model.ifc  out/schedule.xlsx  --mapping plan.csv
"""
from __future__ import annotations

import argparse
import json

from . import cobie, properties_index, qto, schedule, spaces
from .xlsx import write_sheets


def _rows_to_sheet(rows: list[dict]) -> tuple[list[str], list[list]]:
    headers = list(rows[0].keys()) if rows else []
    return headers, [[r.get(h) for h in headers] for r in rows]


def main() -> None:
    ap = argparse.ArgumentParser(prog="aec_data")
    ap.add_argument("command", choices=["index", "qto", "spaces", "cobie", "schedule"])
    ap.add_argument("ifc")
    ap.add_argument("out")
    ap.add_argument("--cost-map", default=None)
    ap.add_argument("--mapping", default=None)
    args = ap.parse_args()

    if args.command == "index":
        idx = properties_index.index_file(args.ifc, args.out)
        print(f"index: {idx['counts']} -> {args.out}")
        return

    if args.command == "qto":
        rows = qto.takeoff_file(args.ifc, args.cost_map)
        total = sum(r["amount"] for r in rows if r.get("amount"))
        write_sheets(args.out, {"QTO": _rows_to_sheet(rows)})
        print(f"qto: {len(rows)} elements, estimate total = {total:,.2f} -> {args.out}")
        return

    if args.command == "spaces":
        rows = spaces.space_schedule_file(args.ifc)
        write_sheets(args.out, {"Spaces": _rows_to_sheet(rows)})
        print(f"spaces: {len(rows)} spaces -> {args.out}")
        return

    if args.command == "cobie":
        sheets = cobie.cobie_file(args.ifc)
        write_sheets(args.out, {name: _rows_to_sheet(rows) for name, rows in sheets.items()})
        print("cobie: " + ", ".join(f"{k}={len(v)}" for k, v in sheets.items()) + f" -> {args.out}")
        return

    if args.command == "schedule":
        acts = schedule.schedule_file(args.ifc, args.mapping)
        rows = [{"id": a["id"], "name": a["name"], "start": a["start"],
                 "finish": a["finish"], "element_count": len(a["guids"]),
                 "guids": json.dumps(a["guids"])} for a in acts]
        write_sheets(args.out, {"Schedule": _rows_to_sheet(rows)})
        print(f"schedule: {len(acts)} activities -> {args.out}")
        return


if __name__ == "__main__":
    main()
