/** ASSET-RIGHTS — sealing a `.mass` with a signed release manifest, and the container download URL.
 *
 *  A mixin rather than two more methods on `client.ts`, for the reason `library.ts` gives: that file
 *  is the named scaling breakpoint and a seam only helps if new work goes through it. Adding
 *  `assetRightsStatus` straight to it took it 2,837 -> 2,844 and the size ratchet went red, which is
 *  the pin working exactly as its comment says it should. `bundleUrl` came out with it rather than
 *  being left behind: it is the other half of the same question — *what kind of container am I
 *  creating?* — and splitting the pair across two files would put one screen's logic in two places.
 *
 *  **Sealing is decided when the file is created.** A release manifest attests to the bytes of one
 *  particular export, so it cannot be added afterwards without producing a different file. That is
 *  why this is a parameter on the download rather than an action on an existing container.
 */
import { HttpCore } from "./httpCore";

type Ctor<T> = new (...args: any[]) => T;

/** Whether this deployment can seal a container, and whether it can *sign* one.
 *
 *  The two are separate on purpose. `enabled` without `signing` means a manifest is written and the
 *  file is tamper-evident, but carries no attribution — it cannot prove who issued it. A UI that
 *  collapses those into one "secure" state tells the user something untrue. */
export interface AssetRightsStatus {
  enabled: boolean;
  signing: boolean;
  /** Public issuer identifier (e.g. a `did:web:` name). Never a key. */
  issuer: string;
}

export function withAssetRights<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class AssetRights extends Base {
    /** Download URL for a project's portable `.mass` container (geometry + all data + blobs).
     *  `assetRights` seals it with a signed release manifest — opt-in, and inert unless the
     *  deployment has the capability switched on. */
    bundleUrl(pid: string, opts: { assetRights?: boolean } = {}) {
      return this.url(`/projects/${pid}/bundle${opts.assetRights ? "?asset_rights=true" : ""}`);
    }

    /** Ask before offering the choice: an option that silently does nothing is worse than no
     *  option, and "sealed" must not be shown as "signed" when no key is configured. */
    assetRightsStatus() {
      return this.json<AssetRightsStatus>("/asset-rights/status");
    }
  };
}
