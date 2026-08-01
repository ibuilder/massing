/**
 * Reference OCR adapters.
 *
 * **The viewer has no OCR engine and does not pick one for you.** What it owns is the part that is
 * genuinely its problem: tiling a sheet at a resolution text can survive, de-duplicating across tile
 * overlaps, and mapping results back into page space so search, spec parsing and title-block
 * extraction all see one text layer. The recognition itself is a host decision, because it is the
 * host that knows whether drawings may leave the building, what the budget is, and which languages
 * matter.
 *
 * These adapters exist so that decision is cheap rather than pre-made. Nothing here ships in the
 * package — every engine is loaded through a dynamic import behind an optional dependency, so a
 * consumer who never calls one of these functions downloads none of it, and the built library is the
 * same size either way.
 *
 * Writing your own is four methods' worth of surface; see `OcrProvider` in `./ocr`. Trained weights
 * and an inference runtime are unavoidable for anything that can read 6pt lettering off a scan —
 * that cost belongs to whichever engine you choose, not to this library.
 *
 * ## A word about API keys
 *
 * The cloud adapters all accept a `proxy` URL, and that is the intended way to use them. An API key
 * placed in browser code is a *published* key — it ships in the bundle, it is readable in devtools,
 * and it is billable by anyone who finds it. The `key` fields exist for local development and for
 * genuinely trusted deployments (an internal tool behind SSO on a private network); they log a
 * warning when used in a page that isn't localhost.
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

// ---- PaddleOCR, locally ----------------------------------------------------

export interface PaddleOcrOptions {
  /**
   * ONNX models, as bytes or as a URL the host serves.
   *
   * **Supply these.** Left unset, the library fetches its defaults over the network on first use,
   * which breaks the offline guarantee this viewer is built around and puts a third-party host in
   * the path of your drawings. Bundle the weights and pass them, exactly as the pdf.js worker is
   * bundled rather than pulled from a CDN.
   *
   * The mobile tier is the right one for a browser: detection is about 5 MB and recognition about
   * 7.5 MB, against 84 MB for the server detection model.
   */
  models?: {
    detection?: ArrayBuffer | string;
    recognition?: ArrayBuffer | string;
    /** Character dictionary matching the recognition model. */
    dictionary?: ArrayBuffer | string;
  };
  /**
   * ONNX execution providers, in preference order.
   *
   * Defaults to WebGPU with a WASM fallback where the browser supports it. WebGPU is severalfold
   * faster, and a D-size sheet is enough tiles for that to be the difference between a pause and a
   * coffee break.
   */
  executionProviders?: string[];
  /** Drop words the engine is less sure of than this. `0` keeps everything. */
  minConfidence?: number;
  /**
   * Called once when the engine finishes loading, with how long it took.
   *
   * Initialisation is seconds, not milliseconds — the models have to be fetched and compiled. A
   * host that shows nothing during it looks broken.
   */
  onReady?: (ms: number) => void;
  /**
   * Supply the module yourself, instead of letting this import it.
   *
   * The default import is deliberately opaque to bundlers so that consumers who never call this
   * function do not have to install `ppu-paddle-ocr`. The cost of that is a bare specifier the
   * browser cannot resolve on its own, so a host that bundles the package — or a test that needs it
   * to actually load — passes it in:
   *
   * ```ts
   * import * as paddle from "ppu-paddle-ocr/web";
   * paddleOcrProvider({ load: async () => paddle });
   * ```
   */
  load?: () => Promise<unknown>;
}

/** What the wrapper hands back. Mirrored rather than imported: it is not a dependency here. */
interface PaddleRecognition {
  text: string;
  box: { x: number; y: number; width: number; height: number };
  confidence: number;
}
interface PaddleService {
  initialize(): Promise<void>;
  recognize(
    image: HTMLCanvasElement | ArrayBuffer,
    options?: { flatten?: boolean },
  ): Promise<{ results?: PaddleRecognition[]; text: string; confidence: number }>;
  destroy?(): Promise<void> | void;
}

/**
 * PaddleOCR in the browser, via `ppu-paddle-ocr` and `onnxruntime-web`.
 *
 * Neither is a dependency of this package — install them in the host if you want local OCR. The
 * dynamic import means a consumer who never calls this function never downloads either.
 *
 * The engine is initialised once and reused across every tile of every page. Constructing it per
 * tile would recompile the ONNX graph thousands of times over a drawing set.
 */
export function paddleOcrProvider(options: PaddleOcrOptions = {}): OcrProvider {
  let service: PaddleService | null = null;
  let starting: Promise<PaddleService> | null = null;
  const floor = options.minConfidence ?? 0;

  const ensure = async (): Promise<PaddleService> => {
    if (service) return service;
    // Concurrent tiles must share one initialisation rather than racing to build their own.
    if (starting) return starting;

    starting = (async () => {
      type WebModule = { PaddleOcrService: new (opts?: Record<string, unknown>) => PaddleService };
      let mod: WebModule;
      try {
        // Indirect on purpose: `ppu-paddle-ocr` is not a dependency of this package, so a literal
        // specifier would fail typecheck and make bundlers try to resolve a module most consumers
        // will never install. The cost is that the browser is handed a bare specifier it cannot
        // resolve, which is what `load` exists to solve.
        const specifier = "ppu-paddle-ocr/web";
        mod = (options.load
          ? await options.load()
          : await import(/* @vite-ignore */ specifier)) as WebModule;
        if (!mod?.PaddleOcrService) throw new Error("no PaddleOcrService export");
      } catch (e) {
        // `cause` as well as the message: the message is what a developer reads, the cause is what
        // a stack trace needs to point at the import that actually failed.
        throw new Error(
          "paddleOcrProvider() could not load `ppu-paddle-ocr`. Install it and `onnxruntime-web` in " +
          "the host application (npm install ppu-paddle-ocr onnxruntime-web), or pass `load` to " +
          `supply the module yourself. Cause: ${(e as Error).message}`,
          { cause: e },
        );
      }

      const began = Date.now();
      const built = new mod.PaddleOcrService({
        ...(options.models
          ? {
            model: {
              ...(options.models.detection ? { detection: options.models.detection } : {}),
              ...(options.models.recognition ? { recognition: options.models.recognition } : {}),
              ...(options.models.dictionary ? { charactersDictionary: options.models.dictionary } : {}),
            },
          }
          : {}),
        ...(options.executionProviders ? { executionProviders: options.executionProviders } : {}),
      });
      await built.initialize();
      options.onReady?.(Date.now() - began);
      service = built;
      return built;
    })();

    try {
      return await starting;
    } finally {
      // Cleared either way: a failed start must not be cached as a permanent one.
      if (!service) starting = null;
    }
  };

  return {
    id: "paddle",
    async recognise({ canvas }: OcrInput): Promise<OcrResult> {
      const engine = await ensure();
      // `flatten` gives one entry per recognised item rather than grouped lines. A drawing has no
      // reading order worth preserving — labels are scattered across the sheet, not set in
      // paragraphs — and the tiling layer positions everything by coordinate anyway.
      const out = await engine.recognize(canvas, { flatten: true });
      const words: OcrWord[] = [];
      for (const item of out.results ?? []) {
        if (!item.text) continue;
        if (item.confidence < floor) continue;
        words.push({
          text: item.text,
          x: item.box.x,
          y: item.box.y,
          w: item.box.width,
          h: item.box.height,
          confidence: item.confidence,
        });
      }
      return { words };
    },
    async dispose() {
      // Waits for an initialisation still in flight before releasing. Reading `service` alone missed
      // it — mid-load `service` is still null, so nothing was destroyed, and the initialiser then
      // assigned it *after* dispose returned, leaving an ONNX session and its models owned by a
      // provider the host had already let go of.
      const pending = starting;
      starting = null;
      if (pending) {
        // Swallowed: a start that failed has nothing to release, and dispose is cleanup.
        await pending.catch(() => undefined);
      }
      // Read *after* awaiting, because the initialiser assigns it on the way through. Taking the
      // reference and clearing the field in one step keeps this to exactly one `destroy()` — going
      // through both the pending value and `service` destroyed the same engine twice.
      const live = service;
      service = null;
      await live?.destroy?.();
    },
  };
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
   * Called once when a provider is dropped for the rest of the run, with the reason.
   *
   * Worth surfacing: silently degrading from the local engine to a cloud one is a privacy and
   * billing change the operator did not choose, and it should not be discovered on an invoice.
   */
  onGiveUp?: (provider: OcrProvider, error: Error) => void;
  /**
   * Consecutive failures before a provider is dropped for the remainder of the run.
   *
   * The failure that matters is not a bad tile, it is a provider that cannot work at all — a
   * missing model file, a rejected key, no network. Without this, a drawing set puts that same
   * doomed attempt through every one of its several thousand tiles, and each one has to time out
   * before the fallback runs. Set to `0` to retry forever.
   */
  giveUpAfter?: number;
  /**
   * Treat a tile that recognises *nothing* as a failure and try the next provider. Off by default:
   * a genuinely blank tile is normal on a drawing, and retrying every one of them doubles the bill.
   *
   * An empty result never counts toward {@link FallbackOptions.giveUpAfter}. It says something about
   * the sheet, not about the engine, and on a mostly-white drawing three tiles of margin would
   * otherwise retire the primary provider for the rest of the run.
   */
  emptyIsFailure?: boolean;
}

/**
 * Try providers in order until one succeeds.
 *
 * The intended shape is the local engine first with a cloud one behind it: PaddleOCR handles the
 * sheet on the machine, and a host that has configured a cloud provider gets it as cover for the
 * cases the local models are weak on. The two fail for unrelated reasons, so the pair is
 * meaningfully more available than either alone.
 *
 * A provider that keeps failing is dropped rather than retried forever — see {@link
 * FallbackOptions.giveUpAfter}.
 */
export function fallbackOcrProvider(providers: readonly OcrProvider[], options: FallbackOptions = {}): OcrProvider {
  if (!providers.length) throw new Error("fallbackOcrProvider needs at least one provider.");
  const limit = options.giveUpAfter ?? 3;
  const strikes = new Map<OcrProvider, number>();
  const dropped = new Set<OcrProvider>();

  return {
    id: `fallback(${providers.map((p) => p.id).join(" → ")})`,
    async recognise(input) {
      const failures: string[] = [];
      const live = providers.filter((p) => !dropped.has(p));
      if (!live.length) {
        throw new Error("every OCR provider has been dropped after repeated failures");
      }

      for (let i = 0; i < live.length; i++) {
        const provider = live[i]!;
        let empty = false;
        try {
          const result = await provider.recognise(input);
          if (options.emptyIsFailure && !result.words.length && i < live.length - 1) {
            empty = true;
            throw new Error("recognised nothing");
          }
          // A tile that works clears the record: an intermittent failure should not accumulate
          // across an entire set and eventually retire a provider that is basically fine.
          strikes.delete(provider);
          return result;
        } catch (e) {
          const error = e as Error;
          failures.push(`${provider.id}: ${error.message}`);

          // A blank tile means the *sheet* was blank there, not that the engine is broken, and most
          // of a drawing is blank. Counting it would retire the primary engine after three tiles of
          // margin and quietly send the rest of the set to the fallback.
          if (!empty) {
            const count = (strikes.get(provider) ?? 0) + 1;
            strikes.set(provider, count);
            // `dropped` gates the callback as well as the retry, so concurrent failures that both
            // cross the threshold announce it once rather than once each.
            if (limit > 0 && count >= limit && !dropped.has(provider)) {
              dropped.add(provider);
              options.onGiveUp?.(provider, error);
            }
          }

          const next = live[i + 1];
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
