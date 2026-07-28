/**
 * Concrete OCR providers: Azure, Google, and a fallback chain.
 *
 * ## A word about API keys
 *
 * Every option here accepts a `proxy` URL, and that is the intended way to use them. An API key
 * placed in browser code is a *published* key — it ships in the bundle, it is readable in devtools,
 * and it is billable by anyone who finds it. The `key` fields exist for local development and for
 * genuinely trusted deployments (an internal tool behind SSO on a private network); they log a
 * warning when used in a page that isn't localhost, because the failure is silent and expensive.
 *
 * A proxy is a few lines on the host: accept the image, attach the credential server-side, forward,
 * return the JSON unchanged.
 */
import type { OcrInput, OcrProvider, OcrResult, OcrWord } from "./ocr";

/** Canvas → base64 PNG, without the data-URL prefix. */
function toBase64Png(canvas: HTMLCanvasElement): string {
  const url = canvas.toDataURL("image/png");
  return url.slice(url.indexOf(",") + 1);
}

/** Canvas → PNG bytes, for endpoints that want a binary body. */
function toPngBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("could not encode the tile"))), "image/png");
  });
}

/** Warn once per provider when a credential is about to travel in client code. */
const warned = new Set<string>();
function warnAboutKey(id: string): void {
  if (warned.has(id)) return;
  warned.add(id);
  const local = typeof location !== "undefined"
    && /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname);
  if (local) return;
  console.warn(
    `[massing-pdf] ${id}: an API key is being used directly from the browser. It is readable by ` +
    `anyone who loads this page and billable to you. Use the \`proxy\` option and attach the ` +
    `credential server-side.`,
  );
}

/** Four corners (as 8 numbers, or as points) → an axis-aligned box. */
function polygonToBox(poly: readonly number[] | readonly { x: number; y: number }[]): OcrWord | null {
  const xs: number[] = [];
  const ys: number[] = [];
  if (typeof poly[0] === "number") {
    const flat = poly as readonly number[];
    for (let i = 0; i + 1 < flat.length; i += 2) { xs.push(flat[i]!); ys.push(flat[i + 1]!); }
  } else {
    for (const p of poly as readonly { x: number; y: number }[]) {
      xs.push(p.x ?? 0); ys.push(p.y ?? 0);
    }
  }
  if (!xs.length) return null;
  const x = Math.min(...xs), y = Math.min(...ys);
  return { text: "", x, y, w: Math.max(...xs) - x, h: Math.max(...ys) - y };
}

// ---- Azure -----------------------------------------------------------------

export interface AzureOcrOptions {
  /**
   * Your own endpoint, which forwards to Azure with the credential attached. Strongly preferred —
   * see the note at the top of this file.
   */
  proxy?: string;
  /** Azure resource endpoint, e.g. `https://<name>.cognitiveservices.azure.com`. */
  endpoint?: string;
  /** Subscription key. Development and trusted-network use only. */
  key?: string;
  /** Extra headers, e.g. a bearer token minted by the host. */
  headers?: () => Record<string, string>;
  /** `prebuilt-read` is right for OCR; `prebuilt-layout` also returns tables. */
  model?: string;
  apiVersion?: string;
  /**
   * Ask Azure for a higher-resolution pass. Costs more and is slower, but it is the documented
   * switch for fine print — which is what drawing lettering is.
   */
  highResolution?: boolean;
  pollIntervalMs?: number;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

interface AzureWord { content?: string; polygon?: number[]; confidence?: number }
interface AzureResult {
  status?: string;
  error?: { message?: string };
  analyzeResult?: { pages?: { words?: AzureWord[] }[] };
}

/**
 * Azure AI Document Intelligence, `prebuilt-read`.
 *
 * The recommended engine for drawings: it handles rotated text lines, and `ocrHighResolution`
 * targets exactly the fine lettering a construction sheet is full of.
 *
 * Analysis is asynchronous — the POST returns 202 with an `Operation-Location`, which is polled
 * until it succeeds.
 */
export function azureOcrProvider(options: AzureOcrOptions): OcrProvider {
  const fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  const apiVersion = options.apiVersion ?? "2024-11-30";
  const model = options.model ?? "prebuilt-read";
  const pollInterval = options.pollIntervalMs ?? 1000;
  const timeout = options.timeoutMs ?? 120_000;

  if (!options.proxy && !options.endpoint) {
    throw new Error("azureOcrProvider needs either a `proxy` or an `endpoint`.");
  }

  const analyseUrl = (): string => {
    if (options.proxy) return options.proxy;
    const base = options.endpoint!.replace(/\/$/, "");
    const features = options.highResolution !== false ? "&features=ocrHighResolution" : "";
    return `${base}/documentintelligence/documentModels/${model}:analyze?api-version=${apiVersion}${features}`;
  };

  const headers = (): Record<string, string> => {
    const h: Record<string, string> = { "Content-Type": "application/json", ...(options.headers?.() ?? {}) };
    if (options.key && !options.proxy) { warnAboutKey("azureOcrProvider"); h["Ocp-Apim-Subscription-Key"] = options.key; }
    return h;
  };

  return {
    id: "azure",
    async recognise({ canvas }: OcrInput): Promise<OcrResult> {
      const res = await fetchImpl(analyseUrl(), {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ base64Source: toBase64Png(canvas) }),
      });

      // A proxy may choose to block until the result is ready and answer 200 with the JSON.
      let payload: AzureResult;
      if (res.status === 202) {
        const operation = res.headers.get("Operation-Location") ?? res.headers.get("operation-location");
        if (!operation) throw new Error("Azure accepted the tile but returned no Operation-Location to poll.");
        // The thunk, not a snapshot: a host minting short-lived tokens needs a fresh one per poll,
        // and the poll can run for minutes.
        payload = await pollAzure(fetchImpl, operation, headers, pollInterval, timeout);
      } else if (res.ok) {
        payload = (await res.json()) as AzureResult;
      } else {
        throw new Error(`Azure OCR returned HTTP ${res.status}: ${(await res.text()).slice(0, 200)}`);
      }

      return { words: azureWords(payload) };
    },
  };
}

async function pollAzure(
  fetchImpl: typeof fetch,
  operation: string,
  headers: () => Record<string, string>,
  interval: number,
  timeout: number,
): Promise<AzureResult> {
  const deadline = Date.now() + timeout;
  // The poll GET must not carry the JSON content-type of the POST. Matched case-insensitively,
  // because a host's own `headers` may spell it any way.
  const pollHeaders = (): Record<string, string> => Object.fromEntries(
    Object.entries(headers()).filter(([k]) => k.toLowerCase() !== "content-type"),
  );

  for (;;) {
    if (Date.now() > deadline) throw new Error(`Azure OCR did not finish within ${Math.round(timeout / 1000)}s.`);
    await new Promise((r) => setTimeout(r, interval));
    const res = await fetchImpl(operation, { headers: pollHeaders() });
    if (!res.ok) throw new Error(`Azure OCR poll returned HTTP ${res.status}`);
    const body = (await res.json()) as AzureResult;
    const status = (body.status ?? "").toLowerCase();
    if (status === "succeeded") return body;
    if (status === "failed") throw new Error(`Azure OCR failed: ${body.error?.message ?? "no reason given"}`);
    // "notStarted" / "running" — keep waiting.
  }
}

function azureWords(payload: AzureResult): OcrWord[] {
  const out: OcrWord[] = [];
  for (const page of payload.analyzeResult?.pages ?? []) {
    for (const word of page.words ?? []) {
      if (!word.content || !word.polygon) continue;
      const box = polygonToBox(word.polygon);
      if (!box) continue;
      out.push({ ...box, text: word.content, confidence: word.confidence ?? 1 });
    }
  }
  return out;
}

// ---- Google ----------------------------------------------------------------

export interface GoogleOcrOptions {
  /** Your own endpoint, forwarding to Google with the credential attached. Preferred. */
  proxy?: string;
  /** API key. Development and trusted-network use only. */
  apiKey?: string;
  headers?: () => Record<string, string>;
  /**
   * `TEXT_DETECTION` for drawings, `DOCUMENT_TEXT_DETECTION` for specs.
   *
   * The document mode assumes paragraphs and a reading order. A drawing has neither, and that
   * assumption costs accuracy rather than adding anything — so sparse detection is the default.
   */
  mode?: "TEXT_DETECTION" | "DOCUMENT_TEXT_DETECTION";
  /** Language hints, e.g. `["en"]`. */
  languageHints?: string[];
  fetchImpl?: typeof fetch;
}

interface GoogleAnnotation {
  description?: string;
  boundingPoly?: { vertices?: { x?: number; y?: number }[] };
}
interface GoogleResponse {
  responses?: { textAnnotations?: GoogleAnnotation[]; error?: { message?: string } }[];
}

/**
 * Google Cloud Vision. The fallback in the recommended pairing.
 *
 * Defaults to `TEXT_DETECTION` — the sparse-text mode — because on a drawing that is the correct
 * choice and the difference is not subtle.
 */
export function googleVisionOcrProvider(options: GoogleOcrOptions = {}): OcrProvider {
  const fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  const mode = options.mode ?? "TEXT_DETECTION";

  if (!options.proxy && !options.apiKey) {
    throw new Error("googleVisionOcrProvider needs either a `proxy` or an `apiKey`.");
  }

  const url = (): string => {
    if (options.proxy) return options.proxy;
    warnAboutKey("googleVisionOcrProvider");
    return `https://vision.googleapis.com/v1/images:annotate?key=${encodeURIComponent(options.apiKey!)}`;
  };

  return {
    id: "google-vision",
    async recognise({ canvas }: OcrInput): Promise<OcrResult> {
      const res = await fetchImpl(url(), {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(options.headers?.() ?? {}) },
        body: JSON.stringify({
          requests: [{
            image: { content: toBase64Png(canvas) },
            features: [{ type: mode }],
            ...(options.languageHints?.length
              ? { imageContext: { languageHints: options.languageHints } }
              : {}),
          }],
        }),
      });
      if (!res.ok) {
        throw new Error(`Google Vision returned HTTP ${res.status}: ${(await res.text()).slice(0, 200)}`);
      }

      const body = (await res.json()) as GoogleResponse;
      const first = body.responses?.[0];
      if (first?.error?.message) throw new Error(`Google Vision: ${first.error.message}`);

      // The first annotation is the whole block of text with a bounding box around everything;
      // the individual words follow it.
      const words: OcrWord[] = [];
      for (const a of (first?.textAnnotations ?? []).slice(1)) {
        if (!a.description || !a.boundingPoly?.vertices?.length) continue;
        const box = polygonToBox(a.boundingPoly.vertices.map((v) => ({ x: v.x ?? 0, y: v.y ?? 0 })));
        if (!box) continue;
        // Vision does not report per-word confidence for TEXT_DETECTION.
        words.push({ ...box, text: a.description });
      }
      return { words };
    },
  };
}

// ---- fallback chain --------------------------------------------------------

export interface FallbackOptions {
  /** Called when one provider fails and the next is tried. */
  onFallback?: (failed: OcrProvider, error: Error, next: OcrProvider) => void;
  /**
   * Treat a tile that recognises *nothing* as a failure and try the next provider. Off by default:
   * a genuinely blank tile is normal on a drawing, and retrying every one of them doubles the bill.
   */
  emptyIsFailure?: boolean;
}

/**
 * Try providers in order until one succeeds.
 *
 * The intended shape is Azure first with Google behind it: the two fail for different reasons —
 * quota, regional outage, a tile one engine chokes on — so the pair is meaningfully more available
 * than either alone.
 */
export function fallbackOcrProvider(providers: readonly OcrProvider[], options: FallbackOptions = {}): OcrProvider {
  if (!providers.length) throw new Error("fallbackOcrProvider needs at least one provider.");

  return {
    id: `fallback(${providers.map((p) => p.id).join(" → ")})`,
    async recognise(input) {
      const failures: string[] = [];
      for (let i = 0; i < providers.length; i++) {
        const provider = providers[i]!;
        try {
          const result = await provider.recognise(input);
          if (options.emptyIsFailure && !result.words.length && i < providers.length - 1) {
            throw new Error("recognised nothing");
          }
          return result;
        } catch (e) {
          const error = e as Error;
          failures.push(`${provider.id}: ${error.message}`);
          const next = providers[i + 1];
          if (!next) break;
          options.onFallback?.(provider, error, next);
        }
      }
      throw new Error(`every OCR provider failed — ${failures.join("; ")}`);
    },
    async dispose() {
      await Promise.all(providers.map((p) => p.dispose?.()));
    },
  };
}

/** Exposed for hosts that want to post the tile themselves. */
export { toBase64Png, toPngBlob };
