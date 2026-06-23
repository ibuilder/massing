/**
 * Solar position for the render-mode **sun / shadow study**. A NOAA-based algorithm good enough for
 * architectural shadow studies (accurate to a fraction of a degree). Given a date/time + latitude /
 * longitude it returns the sun's altitude & azimuth, and a scene-space direction toward the sun.
 *
 * Scene convention (matches the viewer): Y is up, East = +x, North = −z (see app.ts plan coords).
 */

const RAD = Math.PI / 180;

export interface SunPos {
  altitude: number;  // degrees above the horizon (negative ⇒ below = night)
  azimuth: number;   // degrees, clockwise from North
}

/** Day of year (1–366) for a local date. */
function dayOfYear(d: Date): number {
  const start = Date.UTC(d.getFullYear(), 0, 0);
  const cur = Date.UTC(d.getFullYear(), d.getMonth(), d.getDate());
  return Math.floor((cur - start) / 86400000);
}

/**
 * Sun altitude/azimuth for a wall-clock local time at (lat, lon). `tzHours` is the location's UTC
 * offset; when omitted we estimate it from longitude (round(lon/15)) — fine for a shadow study where
 * relative sun movement matters more than civil-time exactness.
 */
export function sunAltAz(date: Date, latDeg: number, lonDeg: number, tzHours?: number): SunPos {
  const tz = tzHours ?? Math.round(lonDeg / 15);
  const hours = date.getHours() + date.getMinutes() / 60 + date.getSeconds() / 3600;
  const n = dayOfYear(date);
  // fractional year (radians)
  const g = (2 * Math.PI / 365) * (n - 1 + (hours - 12) / 24);
  // solar declination (radians)
  const decl = 0.006918 - 0.399912 * Math.cos(g) + 0.070257 * Math.sin(g)
    - 0.006758 * Math.cos(2 * g) + 0.000907 * Math.sin(2 * g)
    - 0.002697 * Math.cos(3 * g) + 0.00148 * Math.sin(3 * g);
  // equation of time (minutes)
  const eqtime = 229.18 * (0.000075 + 0.001868 * Math.cos(g) - 0.032077 * Math.sin(g)
    - 0.014615 * Math.cos(2 * g) - 0.040849 * Math.sin(2 * g));
  // true solar time (minutes) → hour angle (degrees)
  const tst = hours * 60 + eqtime + 4 * lonDeg - 60 * tz;
  const ha = tst / 4 - 180;

  const lat = latDeg * RAD, haR = ha * RAD;
  const cosZen = Math.sin(lat) * Math.sin(decl) + Math.cos(lat) * Math.cos(decl) * Math.cos(haR);
  const zen = Math.acos(Math.min(1, Math.max(-1, cosZen)));
  const altitude = 90 - zen / RAD;

  // azimuth clockwise from North via atan2 (robust at high sun, no acos-branch degeneracy): the
  // atan2 term is 0 at solar noon and signed by the hour angle, so +180° puts noon due south.
  const az = (Math.atan2(Math.sin(haR), Math.cos(haR) * Math.sin(lat) - Math.tan(decl) * Math.cos(lat)) / RAD
    + 180 + 360) % 360;
  return { altitude, azimuth: az };
}

/**
 * Unit vector *toward* the sun in scene space (Y up, E=+x, N=−z). Use as a DirectionalLight position
 * (× distance), aimed at the scene centre. Below the horizon the y-component is simply negative.
 */
export function sunSceneDir(p: SunPos): { x: number; y: number; z: number } {
  const alt = p.altitude * RAD, az = p.azimuth * RAD;
  const ca = Math.cos(alt);
  return { x: ca * Math.sin(az), y: Math.sin(alt), z: -ca * Math.cos(az) };
}
