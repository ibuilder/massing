import type { ApiClient } from "../api/client";

/**
 * PARCEL-SHAPE — size the building on the parcel's real outline, not on its bounding rectangle.
 *
 * ## What was missing
 *
 * Three halves that never met. `parcel_geometry.analyze` parses a cadastral boundary (GeoJSON or
 * WKT), projects it to metres — and returned only area / perimeter / centroid / bbox, **discarding
 * the projected ring it had just computed**. `massing.compute_massing` accepts `lot_polygon` and
 * does a true inward polygon offset for the buildable footprint, which no client could reach:
 * `MassingParams` had no such field, so the feasibility tab could only ever send
 * `lot_width × lot_depth`. And `parcelAnalyze` had no caller on any screen at all.
 *
 * ## Why it is worth a control
 *
 * A bounding rectangle's area is **always ≥ the parcel's**, and the error is not cosmetic — it
 * runs the whole way down the underwriting: lot area → max GFA → floors → unit count → rent →
 * the acquisition proforma's IRR. Every one of those is biased optimistic, and none of them says
 * so. On an ordinary L-shaped corner lot (1,600 m² inside a 50 × 50 m box) the rectangle yields
 * 5,000 m² of buildable GFA against the parcel's true 3,200 — **56% too much building**, on a
 * number a deal gets priced from.
 *
 * So the control does not silently substitute one for the other. It states both: the parcel's
 * area, the rectangle it replaces, and the percentage between them. A user who then chooses the
 * rectangle has chosen it.
 */

/** What the control needs, so a test can drive it without standing up a client. */
export interface ParcelBoundaryHost {
  api: { parcelAnalyze: ApiClient["parcelAnalyze"] };
}

/** A loaded parcel: the ring the massing engine wants, plus what it is worth saying about it. */
export interface LoadedParcel {
  ring: number[][];
  areaM2: number;
  areaAcres: number;
  rectM2: number;
  widthM: number;
  depthM: number;
  vertices: number;
  /** The server read the ring as longitude/latitude and projected it. Reported, because the rule
   *  that decides is a HEURISTIC on coordinate magnitude — every |x| ≤ 180 and |y| ≤ 90 — and a
   *  parcel sketched in local metres near the origin fits that description exactly. The two
   *  readings differ by a factor of about 111,000, so the mistake is never subtle once named, and
   *  invisible until it is. */
  wasLonLat: boolean;
}

export interface ParcelBoundaryControl {
  el: HTMLElement;
  /** The ring to send as `lot_polygon`, or null while no parcel is loaded. */
  parcel: () => LoadedParcel | null;
}

/**
 * Split from the DOM so the branch that matters can be asserted directly. Returns the sentence the
 * panel shows once a parcel is loaded — both areas and the overstatement between them.
 *
 * The percentage is of the PARCEL, not of the rectangle: "the box is 56% bigger than the lot" is
 * the number that maps onto the GFA error. Expressing it the other way round ("the lot is 36% of
 * the box") is arithmetically fine and answers a question nobody asked.
 */
export function overstatement(p: LoadedParcel): string {
  const n = (v: number) => Math.round(v).toLocaleString();
  const head = `Parcel ${n(p.areaM2)} m² (${p.areaAcres.toFixed(3)} ac) · ${p.vertices} vertices`
    + (p.wasLonLat ? " · read as longitude/latitude and projected to metres" : "");
  if (p.rectM2 <= p.areaM2) {
    // A rectangular parcel: the two agree, and saying "0% larger" invites the reader to hunt for a
    // difference that is not there. Rounding can also put rectM2 a hair under areaM2.
    return `${head} · its ${p.widthM} × ${p.depthM} m bounding box is the same lot — a rectangular`
      + " parcel, so nothing changes.";
  }
  const over = Math.round(((p.rectM2 - p.areaM2) / p.areaM2) * 100);
  return `${head} · the ${p.widthM} × ${p.depthM} m rectangle you would otherwise type is`
    + ` ${n(p.rectM2)} m² — ${over}% larger. Sizing on the rectangle overstates GFA, units and IRR`
    + " by about that much.";
}

/**
 * GeoJSON or WKT, decided by the first character rather than by a guess at the content. Throws with
 * a message worth showing when the text is neither.
 */
export function parseBoundary(text: string): { geojson?: unknown; wkt?: string } {
  const t = text.trim();
  if (!t) throw new Error("paste a parcel boundary first");
  if (t.startsWith("{") || t.startsWith("[")) {
    try {
      return { geojson: JSON.parse(t) };
    } catch (e) {
      throw new Error(`that is not valid JSON: ${(e as Error).message}`, { cause: e });
    }
  }
  // MULTIPOLYGON is named so the refusal is specific, and it is refused here rather than sent: the
  // server's `parse_boundary` takes POLYGON only, so accepting it locally bought a round trip and a
  // generic 422 that never said why. The first draft of this function listed it as accepted syntax
  // — a client advertising support the server does not have, which is the same drift in miniature
  // that this whole item is about. Supporting it is a PRODUCT question, not a cleanup: the buildable
  // footprint comes from offsetting ONE outer ring inward, and a lot split by a right-of-way has no
  // single ring to offset, so which part is "the parcel" is somebody's decision to make.
  if (/^MULTIPOLYGON/i.test(t)) {
    throw new Error("MULTIPOLYGON is not supported — a parcel boundary is one outer ring. Export the"
      + " lot on its own as POLYGON ((x y, x y, ...)).");
  }
  if (/^POLYGON/i.test(t)) return { wkt: t };
  throw new Error("expected GeoJSON (starting with '{') or WKT (starting with 'POLYGON')");
}

function row(): HTMLElement {
  const d = document.createElement("div");
  d.style.cssText = "display:flex;gap:6px;align-items:center;margin-top:4px;flex-wrap:wrap";
  return d;
}

export function parcelBoundaryControl(
  host: ParcelBoundaryHost, onChange: (p: LoadedParcel | null) => void,
): ParcelBoundaryControl {
  let loaded: LoadedParcel | null = null;

  const wrap = document.createElement("div");
  wrap.style.cssText = "margin:6px 0;padding:6px 8px;border:1px solid var(--line);border-radius:6px";
  const title = document.createElement("div");
  title.className = "meta";
  title.textContent = "📐 Real parcel boundary (optional) — paste GeoJSON or WKT, or load a file."
    + " Without one the lot is the width × depth rectangle above.";
  wrap.appendChild(title);

  const ta = document.createElement("textarea");
  ta.rows = 2;
  ta.placeholder = '{"type":"Polygon","coordinates":[[[x,y],…]]}  or  POLYGON ((x y, x y, …))';
  ta.style.cssText = "width:100%;margin-top:4px;font-family:var(--mono,monospace);font-size:11px";
  wrap.appendChild(ta);

  const file = document.createElement("input");
  file.type = "file";
  file.accept = ".geojson,.json,.wkt,.txt,application/geo+json,application/json,text/plain";
  file.style.cssText = "font-size:11px";
  file.onchange = async () => {
    const f = file.files?.[0];
    if (!f) return;
    ta.value = await f.text();
  };

  const useBtn = document.createElement("button");
  useBtn.className = "tool-btn";
  useBtn.textContent = "Use this parcel";
  const clearBtn = document.createElement("button");
  clearBtn.className = "tool-btn";
  clearBtn.textContent = "Clear";
  clearBtn.hidden = true;

  const out = document.createElement("div");
  out.className = "meta";
  out.style.marginTop = "4px";

  const say = (text: string, tone?: string) => {
    out.textContent = text;
    out.style.color = tone ?? "";
  };

  useBtn.onclick = async () => {
    useBtn.disabled = true;
    try {
      const body = parseBoundary(ta.value);
      say("reading the boundary…");
      const r = await host.api.parcelAnalyze(body);
      loaded = {
        ring: r.ring_m, areaM2: r.area_m2, areaAcres: r.area_acres,
        rectM2: r.bounding_rect_m2, widthM: r.lot_width_m, depthM: r.lot_depth_m,
        vertices: r.vertices, wasLonLat: r.coordinates_were_lonlat,
      };
      say(overstatement(loaded), "var(--accent)");
      clearBtn.hidden = false;
      onChange(loaded);
    } catch (e) {
      // The parcel is NOT adopted on a failure, and any previously loaded one is left alone — a
      // half-read boundary silently replacing a good one is worse than a rejected paste.
      say((e as Error).message, "var(--status-crit)");
    } finally {
      useBtn.disabled = false;
    }
  };

  clearBtn.onclick = () => {
    loaded = null;
    clearBtn.hidden = true;
    say("back to the width × depth rectangle.");
    onChange(null);
  };

  const controls = row();
  controls.append(file, useBtn, clearBtn);
  wrap.append(controls, out);
  return { el: wrap, parcel: () => loaded };
}
