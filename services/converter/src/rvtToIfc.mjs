// RVT → IFC via Autodesk APS Model Derivative (guide §4b).
//
// ⚠️ PAID CLOUD + REQUIRES AUTODESK CREDENTIALS. There is NO open-source RVT reader.
// Isolated behind a feature flag (APS_CLIENT_ID/SECRET) so the rest of the platform stays
// free/offline. Costs accrue PER TRANSLATION — surface that in the UI before invoking.
//
// Flow: 2-legged OAuth → OSS bucket → signed-S3 upload → POST translate job (output: ifc)
//       → poll manifest until success → download the IFC derivative → (caller feeds ifcToFrag).
//
// Caveats to show users: supported RVT ≈ current four majors; IFC export is IFC2x3/IFC4;
// georeferencing depends on the RVT having Survey Point / Project Base Point set.

const APS_BASE = "https://developer.api.autodesk.com";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export function apsEnabled() {
  return Boolean(process.env.APS_CLIENT_ID && process.env.APS_CLIENT_SECRET);
}

async function getToken() {
  const res = await fetch(`${APS_BASE}/authentication/v2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: process.env.APS_CLIENT_ID,
      client_secret: process.env.APS_CLIENT_SECRET,
      grant_type: "client_credentials",
      scope: "data:read data:write data:create bucket:create bucket:read",
    }),
  });
  if (!res.ok) throw new Error(`APS auth failed: ${res.status}`);
  return (await res.json()).access_token;
}

async function ensureBucket(auth, bucketKey) {
  const res = await fetch(`${APS_BASE}/oss/v2/buckets`, {
    method: "POST", headers: { ...auth, "Content-Type": "application/json" },
    body: JSON.stringify({ bucketKey, policyKey: "transient" }),
  });
  if (!res.ok && res.status !== 409) throw new Error(`APS bucket create failed: ${res.status}`);
}

// signed-S3-upload flow: init → PUT to the signed URL → complete → returns objectId
async function uploadObject(auth, bucketKey, objectName, bytes) {
  const base = `${APS_BASE}/oss/v2/buckets/${bucketKey}/objects/${encodeURIComponent(objectName)}/signeds3upload`;
  const init = await fetch(base, { headers: auth });
  if (!init.ok) throw new Error(`APS signed-upload init failed: ${init.status}`);
  const { uploadKey, urls } = await init.json();
  const put = await fetch(urls[0], { method: "PUT", body: bytes });
  if (!put.ok) throw new Error(`APS S3 PUT failed: ${put.status}`);
  const done = await fetch(base, {
    method: "POST", headers: { ...auth, "Content-Type": "application/json" },
    body: JSON.stringify({ uploadKey }),
  });
  if (!done.ok) throw new Error(`APS upload complete failed: ${done.status}`);
  return (await done.json()).objectId; // urn:adsk.objects:os.object:bucket/name
}

const toUrn = (objectId) =>
  Buffer.from(objectId).toString("base64").replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");

async function startTranslation(auth, urn) {
  const res = await fetch(`${APS_BASE}/modelderivative/v2/designdata/job`, {
    method: "POST", headers: { ...auth, "Content-Type": "application/json", "x-ads-force": "true" },
    body: JSON.stringify({ input: { urn }, output: { formats: [{ type: "ifc", advanced: {} }] } }),
  });
  if (!res.ok) throw new Error(`APS translate job failed: ${res.status}`);
}

async function pollManifest(auth, urn, { timeoutMs = 900_000, intervalMs = 5_000 } = {}) {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    const res = await fetch(`${APS_BASE}/modelderivative/v2/designdata/${urn}/manifest`, { headers: auth });
    if (res.ok) {
      const m = await res.json();
      if (m.status === "success") return m;
      if (m.status === "failed" || m.status === "timeout") throw new Error(`APS translation ${m.status}`);
    }
    await sleep(intervalMs);
  }
  throw new Error("APS translation timed out");
}

function findIfcDerivativeUrn(manifest) {
  for (const d of manifest.derivatives || []) {
    if ((d.outputType || "").toLowerCase() !== "ifc") continue;
    const stack = [...(d.children || [])];
    while (stack.length) {
      const c = stack.pop();
      if (c.urn && /\.ifc$/i.test(c.urn)) return c.urn;
      if (c.children) stack.push(...c.children);
    }
    if (d.urn) return d.urn;
  }
  throw new Error("no IFC derivative found in the APS manifest");
}

async function downloadDerivative(auth, urn, derivativeUrn) {
  const res = await fetch(
    `${APS_BASE}/modelderivative/v2/designdata/${urn}/manifest/${encodeURIComponent(derivativeUrn)}`,
    { headers: auth }); // follows the redirect to the signed download URL
  if (!res.ok) throw new Error(`APS derivative download failed: ${res.status}`);
  return new Uint8Array(await res.arrayBuffer());
}

/**
 * Translate an RVT to IFC and return the IFC bytes. Throws if APS is not configured.
 * @param {Uint8Array} rvtBytes
 * @param {string} objectName e.g. "model.rvt"
 * @param {(stage:string)=>void} [onStage] progress callback
 * @returns {Promise<Uint8Array>} IFC bytes (then pass to ifcToFragments)
 */
export async function rvtToIfc(rvtBytes, objectName, onStage = () => {}) {
  if (!apsEnabled()) {
    throw new Error("APS not configured (set APS_CLIENT_ID / APS_CLIENT_SECRET). RVT is a paid bridge.");
  }
  const token = await getToken();
  const auth = { Authorization: `Bearer ${token}` };
  const bucketKey = process.env.APS_BUCKET || "aec-bim-rvt";
  const name = objectName.replace(/[^\w.\-]/g, "_");

  onStage("bucket");
  await ensureBucket(auth, bucketKey);
  onStage("upload");
  const objectId = await uploadObject(auth, bucketKey, name, rvtBytes);
  const urn = toUrn(objectId);
  onStage("translate");
  await startTranslation(auth, urn);
  onStage("poll");
  const manifest = await pollManifest(auth, urn);
  onStage("download");
  return downloadDerivative(auth, urn, findIfcDerivativeUrn(manifest));
}
