/**
 * Licence classification and policy for the npm dependency tree.
 *
 * WHY THIS EXISTS, AND WHAT IT ADDS TO THE GATE WE ALREADY HAD
 *     `services/api/test_license_gate.py` already fails the build on a GPL/AGPL dependency. It is a
 *     real gate and this does not replace it. But its claim is narrower than it reads, in two ways:
 *
 *     1. **It walks Python distributions only** (`importlib.metadata`). The npm tree — 638 packages,
 *        including `three`, `web-ifc` and the whole That Open stack — was never in its population.
 *     2. **It reads DECLARED metadata**: Trove classifiers, the `License` field, the SPDX
 *        expression. That is the badge. The roadmap item that commissioned this exists because a
 *        scan found repositories whose actual LICENSE differs from their README or badge, two of
 *        them forbidding exactly our use. **A declaration cannot catch a lying declaration.**
 *
 *     So this reads the LICENSE FILE and cross-checks it against the declaration. Two independent
 *     statements about one fact; disagreement is the signal. Same shape as the roadmap
 *     self-consistency gate, applied to a different artefact.
 *
 * THE FALSE POSITIVE THIS ALMOST SHIPPED WITH — read before changing `classify`
 *     The first draft tested licence names in PRECEDENCE order, GPL before MPL. It reported three
 *     contradictions, one of them **`web-ifc` declared MPL-2.0 but "actually GPL"** — a core
 *     dependency named in the project's non-negotiables. That was wrong, and alarmingly so.
 *
 *     `web-ifc/LICENSE.md` opens with "Mozilla Public License Version 2.0". MPL-2.0's own text
 *     **defines "Secondary License" by naming the GNU GPL, LGPL and AGPL**, so any MPL-2.0 file
 *     contains the string "GNU General Public License". A precedence-ordered matcher fires on the
 *     definition rather than the title.
 *
 *     The fix is not a longer exclusion list, it is a different rule: **the earliest title wins.**
 *     A licence document announces itself at the top; every later mention is prose about some other
 *     licence. `lightningcss` and its win32 binary were the same false positive.
 *
 *     **An alarming result should raise the bar on the instrument, not lower it** — three hits
 *     including a core dependency was the moment to doubt the classifier, not the supply chain.
 */

/**
 * Ordered by nothing — position in the document decides. Each entry is a phrase a licence uses to
 * NAME ITSELF at the top of its text, not a phrase that merely mentions it.
 */
const TITLES = [
  [/GNU AFFERO GENERAL PUBLIC LICENSE/i, "AGPL"],
  [/GNU LESSER GENERAL PUBLIC LICENSE/i, "LGPL"],
  [/GNU GENERAL PUBLIC LICENSE/i, "GPL"],
  [/Mozilla Public License/i, "MPL"],
  [/PolyForm/i, "PolyForm"],
  [/Server Side Public License/i, "SSPL"],
  [/Business Source License/i, "BUSL"],
  [/Apache License/i, "Apache"],
  [/Permission is hereby granted, free of charge/i, "MIT"],
  [/Redistribution and use in source and binary forms/i, "BSD"],
  [/Permission to use, copy, modify, and(?:\/or)? distribute/i, "ISC"],
  [/\bThe Unlicense\b|placed .{0,40}public domain/i, "PUBLIC-DOMAIN"],
  [/CC0 1\.0 Universal|Creative Commons Zero/i, "CC0"],
  [/Blue Oak Model License/i, "BlueOak"],
];

/** Only the head of the file is considered — a licence titles itself before it says anything else. */
const HEAD_CHARS = 8000;

/** Family of a LICENCE DOCUMENT, by whichever recognised title appears earliest. */
export function classify(text) {
  const head = String(text).slice(0, HEAD_CHARS);
  let best = null;
  let bestAt = Infinity;
  for (const [re, name] of TITLES) {
    const m = re.exec(head);
    if (m && m.index < bestAt) { bestAt = m.index; best = name; }
  }
  return best ?? "UNKNOWN";
}

/** Family of a DECLARED SPDX-ish string. `null`/absent is "NONE", which is not the same as UNKNOWN. */
export function declaredFamily(declared) {
  if (!declared) return "NONE";
  const u = String(declared).toUpperCase();
  if (/AGPL/.test(u)) return "AGPL";
  if (/LGPL/.test(u)) return "LGPL";
  if (/GPL/.test(u)) return "GPL";
  if (/MPL/.test(u)) return "MPL";
  if (/APACHE/.test(u)) return "Apache";
  if (/\bMIT\b/.test(u)) return "MIT";
  if (/BSD/.test(u)) return "BSD";
  if (/\bISC\b/.test(u)) return "ISC";
  if (/POLYFORM/.test(u)) return "PolyForm";
  if (/SSPL/.test(u)) return "SSPL";
  if (/BUSL/.test(u)) return "BUSL";
  if (/BLUEOAK|0BSD|UNLICENSE|CC0|PYTHON-2|ZLIB|WTFPL/.test(u)) return "PERMISSIVE-OTHER";
  return "OTHER";
}

export const PERMISSIVE = new Set(["MIT", "BSD", "ISC", "Apache", "PERMISSIVE-OTHER", "PUBLIC-DOMAIN", "CC0", "BlueOak"]);

/**
 * PERMITTED: MIT / BSD / Apache / ISC / CC0 (and the other permissive family names above).
 * FORBIDDEN outright: GPL, AGPL, PolyForm/noncommercial, BUSL.
 *
 * Those two lines were one sentence until v0.3.1030, and it read "Forbidden outright: MIT / BSD /
 * Apache / ISC / CC0 …" — the permit-list under the ban-list's heading, stating the exact opposite
 * of the rule the code below enforces. It happened while widening the list to add CC0: the word
 * that made it a permit-list was dropped in the edit. Nothing failed, because a comment cannot,
 * and the next person to reconcile policy from prose would have had it backwards.
 *
 * LGPL and MPL are WEAK copyleft and are reported rather than failed, which
 * matches `test_license_gate.py`'s existing policy — `ifcopenshell` and `certifi` sit there and are
 * accepted for our distribution model. Collapsing "disallowed" into "worth a look" makes a gate
 * either useless or permanently red, and a permanently red gate gets switched off.
 */
export const FORBIDDEN = new Set(["AGPL", "GPL", "SSPL", "BUSL", "PolyForm"]);
export const WEAK_COPYLEFT = new Set(["LGPL", "MPL"]);

/**
 * A dual-licensed declaration ("(MIT OR GPL-3.0-or-later)") offers a choice, and we take the
 * permissive one. Without this, `jszip` reads as a GPL dependency — it is not; its LICENSE file is
 * the MIT text, which is exactly the choice being exercised.
 */
export function isDualWithPermissive(declared) {
  if (!declared) return false;
  const parts = String(declared).split(/\s+OR\s+/i).map((p) => p.replace(/[()]/g, "").trim());
  return parts.length > 1 && parts.some((p) => PERMISSIVE.has(declaredFamily(p)));
}

/**
 * The verdict for one package.
 *
 * `reason` is always populated so a failure names *why*, not merely *that*. A gate that says
 * "licence violation" without naming the file it read and what it found reproduces the class of
 * defect it exists to catch.
 */
export function verdict({ name, declared, licenceText, licenceFile }) {
  const decl = declaredFamily(declared);
  const text = licenceText == null ? null : classify(licenceText);
  const dual = isDualWithPermissive(declared);

  // The text is the authority when we have it; the declaration is all we have when we do not.
  const effective = text && text !== "UNKNOWN" ? text : decl;

  // MOST SPECIFIC FIRST. Declared permissive, file says strong copyleft — the badge-vs-reality case
  // this gate exists for. It is a subset of FORBIDDEN and both fail the build, so ordering changes
  // nothing about the verdict and everything about the message: "declares MIT but LICENSE is GPL"
  // tells you the dependency lied, while a bare "GPL — forbidden" reads as our own bookkeeping error
  // and sends you to the wrong place. The generic branch ran first in the first draft.
  if (text && FORBIDDEN.has(text) && PERMISSIVE.has(decl) && !dual) {
    return { name, status: "CONTRADICTION", effective: text, declared, licenceFile,
      reason: `declares ${declared} but ${licenceFile} is ${text}` };
  }
  if (FORBIDDEN.has(effective) && !dual) {
    return { name, status: "FORBIDDEN", effective, declared, licenceFile,
      reason: `${effective} — forbidden by the MIT/BSD/Apache/ISC/CC0 rule` +
              (text ? ` (from the text of ${licenceFile})` : " (declared; no LICENSE file found)") };
  }
  if (WEAK_COPYLEFT.has(effective)) {
    return { name, status: "REPORT", effective, declared, licenceFile,
      reason: `${effective} — weak copyleft, accepted for our distribution model` };
  }
  if (text === "UNKNOWN") {
    return { name, status: "UNCLASSIFIED", effective: decl, declared, licenceFile,
      reason: `${licenceFile} did not match any known licence title` };
  }
  return { name, status: "OK", effective, declared, licenceFile, reason: `${effective}` };
}
