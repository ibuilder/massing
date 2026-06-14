// RVT → IFC via Autodesk APS Model Derivative (guide §4b).
//
// ⚠️ PAID CLOUD + REQUIRES AUTODESK CREDENTIALS. There is NO open-source RVT reader.
// This is isolated behind a feature flag so the rest of the platform stays free/offline.
// Costs accrue PER TRANSLATION — surface that in the UI before invoking.
//
// Flow: 2-legged OAuth -> OSS bucket upload -> POST translation job (output ifc)
//       -> poll manifest until success -> download IFC derivative -> feed into ifcToFrag.
//
// Caveats to show users: supported RVT ~ current four majors; IFC export is IFC2x3/IFC4;
// georeferencing depends on the RVT having Survey Point / Project Base Point set.

const APS_BASE = "https://developer.api.autodesk.com";

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

/**
 * Translate an RVT to IFC and return the IFC bytes. Throws if APS is not configured.
 * @param {Uint8Array} rvtBytes
 * @param {string} objectName e.g. "model.rvt"
 * @returns {Promise<Uint8Array>} IFC bytes (then pass to ifcToFragments)
 */
export async function rvtToIfc(rvtBytes, objectName) {
  if (!apsEnabled()) {
    throw new Error("APS not configured (set APS_CLIENT_ID / APS_CLIENT_SECRET). RVT is a paid bridge.");
  }
  const token = await getToken();
  const auth = { Authorization: `Bearer ${token}` };
  const bucketKey = process.env.APS_BUCKET || `aec-bim-${Date.now()}`;

  // 1. ensure bucket
  await fetch(`${APS_BASE}/oss/v2/buckets`, {
    method: "POST", headers: { ...auth, "Content-Type": "application/json" },
    body: JSON.stringify({ bucketKey, policyKey: "transient" }),
  }); // 409 if exists — ignore

  // 2. upload object (signed-s3-upload flow omitted for brevity — see APS docs)
  // 3. POST job: output.formats = [{ type: "ifc", advanced: {...} }] with urn = base64(objectId)
  // 4. poll GET /modelderivative/v2/designdata/{urn}/manifest until status === "success"
  // 5. GET the IFC derivative bytes

  void rvtBytes; void objectName; void bucketKey;
  throw new Error("rvtToIfc: implement the OSS upload + Model Derivative polling per APS docs. " +
                  "This skeleton documents the flow; wiring requires your Autodesk account.");
}
