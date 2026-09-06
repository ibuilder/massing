/**
 * The transition field-gate, as a pure function — which `requires` entries a record has not met.
 *
 * A `requires` entry may name ALTERNATIVES separated by `|`, satisfied when ANY of them is filled.
 * That exists for the MOD-SWEEP additive pattern: a reference field is added BESIDE its text field
 * and the text is retired later, so a gate naming only the text half blocks the very migration the
 * pattern is for. `entitlement.submit` hit it the moment `agency_company` was added — the new field's
 * help text tells the user to pick a company instead of typing a name, and then submit demanded the
 * typed name.
 *
 * **This logic exists on both sides on purpose, and that is the hazard.** The server enforces it in
 * `services/api/src/aec_api/modules.py`; this disables the button. If only one learns about `|`, the
 * UI greys out a transition the server would accept (or offers one it will refuse) — so this is
 * extracted and tested rather than left inline, which is how it was when the divergence was
 * introduced.
 *
 * Note the two emptiness tests are NOT identical: the server also treats `[]` and `{}` as empty.
 * That difference predates this function and is left alone here rather than changed silently — it
 * only shows up for list/object-valued required fields, of which there are none today.
 */
export function unmetRequires(requires: string[], data: Record<string, unknown>): string[] {
  const filled = (f: string) => {
    const v = data[f];
    return v !== undefined && v !== null && v !== "";
  };
  return requires.filter((entry) => !entry.split("|").some(filled));
}
