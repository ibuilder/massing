# E-signatures on PDFs — options & decision

Research + the approach we took for signing contracts, change orders, and other documents. Pairs with
the contract lifecycle (generate → markup → sign) in the GC portal.

## Electronic vs digital signature
- **Electronic signature** — a typed/drawn name + intent + audit trail. Legally valid for most
  business contracts under the US **ESIGN Act / UETA**. Easy; not cryptographically bound to the file.
- **Digital signature** — a cryptographic signature using an X.509 certificate + private key, embedded
  in the PDF. Makes the document **tamper-evident** and verifiable offline. The PDF profile is
  **PAdES** (PDF Advanced Electronic Signatures): it packages the certificate chain, a timestamp, and
  validation data **into the PDF**, so the signature stays verifiable over time without a live service.
  This is the model established PDF review tools use (Windows Certificate Store / PKCS#12 / Adobe CDS).
- **AdES vs QES** — an *advanced* signature (AdES/PAdES) proves integrity + signer key. A *qualified*
  signature (QES, eIDAS) additionally uses a certificate from a qualified Trust Service Provider and
  has the legal weight of a handwritten signature in the EU. QES requires a public/qualified CA.

## What we ship
1. **Typed signatures** (built) — per-party typed name + date recorded on the record, rendered into the
   generated document, with an audit-log entry. Right for routine internal approvals.
2. **PAdES digital signatures** (built, `esign.py` via **pyHanko**) — one-click **"Digitally sign
   (PAdES)"** on a contract/CO: renders the document, applies a certificate-based signature, attaches
   the signed (tamper-evident) PDF, and records the signer + cert **fingerprint** + timestamp.
   - Signer certificate: a **self-signed platform certificate** generated + cached locally by default
     (no cost, fully offline — an *advanced* signature). Set **`ESIGN_P12`** (+ `ESIGN_P12_PASS`) to a
     PKCS#12 to sign with your organisation's / a CA-issued certificate instead.
3. **3rd-party bridge** (feature-flagged, `esign_bridge.py`) — for legally-binding, multi-party signing
   when a project requires it. Off unless `ESIGN_PROVIDER` (+ `ESIGN_API_KEY` / `ESIGN_BASE_URL`) is set;
   `GET /esign/status` reports availability (incl. whether the chosen provider is `implemented`).
   - **DocuSeal** (self-hosted OSS) is **implemented end-to-end** (stdlib `urllib`, no SDK): a
     **"Send for signature"** action on a contract/CO renders the document, creates a DocuSeal template
     from the PDF, opens a submission with the signers, and stores the submission id + per-signer signing
     URLs on the record (`data.esign_submission`, audited). Set `ESIGN_PROVIDER=docuseal`,
     `ESIGN_API_KEY`, and `ESIGN_BASE_URL` (your DocuSeal instance). Completion is reflected via
     **`POST /esign/webhook`** (point DocuSeal's webhook there).
   - Documenso / DocuSign / Adobe / Dropbox Sign: the bridge surface + status are in place; each
     provider's submission/envelope flow is wired per credentialed deployment (we don't ship dead SDKs).

## 3rd-party platform options (for the bridge)
| Option | Type | Notes |
|---|---|---|
| **DocuSign** | SaaS | Industry standard, 400+ integrations, CLM (redline/negotiation). Highest cost. |
| **Adobe Acrobat Sign** | SaaS | Native PDF editing, deep Acrobat integration. |
| **Dropbox Sign** | SaaS | Simple, lower cost, unlimited docs; fewer features. |
| **DocuSeal / Documenso / OpenSign / LibreSign** | Self-hosted OSS | Full data control, on-prem; pairs with our offline-first stance. DocuSeal/Documenso are the most turnkey. |

## Recommendation
- **Routine internal approvals →** typed signatures (built).
- **Tamper-evident execution of our own contracts/COs →** the built-in **PAdES** digital signature
  (no cost, offline; upgrade to your own/CA cert via `ESIGN_P12`).
- **Legally-binding multi-party / QES →** enable the feature-flagged bridge. For a self-hosted shop,
  **DocuSeal or Documenso**; for an enterprise already on it, **DocuSign**.

## Out of scope (for now)
Running our own qualified CA / trust chain; a live DocuSign/Adobe integration (scoped behind the flag);
real-time hosted-session co-markup (multiple reviewers marking up one PDF live).
