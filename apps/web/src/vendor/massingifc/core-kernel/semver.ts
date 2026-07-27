/**
 * Minimal semantic-version handling.
 *
 * Deliberately dependency-free and deliberately small: the kernel only ever needs to answer
 * "is this provider new enough for this consumer", which is a comparison plus a caret range. A
 * full semver implementation (pre-release ordering, complex range grammars) would be more surface
 * to keep correct than the question warrants.
 */

export interface SemVer {
  readonly major: number;
  readonly minor: number;
  readonly patch: number;
  /** Pre-release tag, e.g. `beta.1`. Compared only for equality, never ordered. */
  readonly prerelease: string | undefined;
}

const PATTERN = /^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$/;

export function parseSemVer(value: string): SemVer | undefined {
  const match = PATTERN.exec(value.trim());
  if (!match) return undefined;
  return {
    major: Number(match[1]),
    minor: Number(match[2]),
    patch: Number(match[3]),
    prerelease: match[4],
  };
}

/** Returns a negative number if `a < b`, positive if `a > b`, `0` when equal. */
export function compareSemVer(a: SemVer, b: SemVer): number {
  if (a.major !== b.major) return a.major - b.major;
  if (a.minor !== b.minor) return a.minor - b.minor;
  if (a.patch !== b.patch) return a.patch - b.patch;
  // A pre-release sorts below its own release (1.0.0-beta < 1.0.0), matching the semver spec's
  // ordering rule without implementing the full identifier comparison.
  if (a.prerelease === b.prerelease) return 0;
  if (a.prerelease === undefined) return 1;
  if (b.prerelease === undefined) return -1;
  return a.prerelease < b.prerelease ? -1 : 1;
}

/**
 * Tests `version` against a range.
 *
 * Supported forms: `*` (any), `1.2.3` (exact), `>=1.2.3`, `>1.2.3`, `<=1.2.3`, `<1.2.3`,
 * and `^1.2.3` (compatible-with: same major, at least this version — for `0.x`, same minor).
 */
export function satisfies(version: string, range: string): boolean {
  const trimmed = range.trim();
  if (trimmed === "*" || trimmed === "") return true;

  const parsed = parseSemVer(version);
  if (!parsed) return false;

  const operatorMatch = /^(\^|>=|<=|>|<|=)?\s*(.+)$/.exec(trimmed);
  if (!operatorMatch) return false;
  const operator = operatorMatch[1] ?? "=";
  const target = parseSemVer(operatorMatch[2] ?? "");
  if (!target) return false;

  const comparison = compareSemVer(parsed, target);
  switch (operator) {
    case "=":
      return comparison === 0;
    case ">":
      return comparison > 0;
    case ">=":
      return comparison >= 0;
    case "<":
      return comparison < 0;
    case "<=":
      return comparison <= 0;
    case "^":
      if (comparison < 0) return false;
      // Below 1.0.0 the minor acts as the breaking-change axis, so ^0.3.1 must not match 0.4.0.
      return target.major === 0
        ? parsed.major === 0 && parsed.minor === target.minor
        : parsed.major === target.major;
    default:
      return false;
  }
}
