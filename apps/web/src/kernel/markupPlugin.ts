/**
 * KERNEL-ADOPT ② — markup/pins as a real kernel plugin.
 *
 * The first adoption (`elementRef`) took the identity boundary because everything else crosses it.
 * This one takes a **feature**, and picks markup for a concrete reason rather than a tidy one:
 * `reloadModelPins` is `await`ed unguarded on the panel-build path, so a pins failure — a network
 * blip, one malformed record, a project whose module pins 404 — propagates out of pin loading and
 * aborts whatever the caller had queued after it. The blast radius of "the pins did not load" is
 * currently "the rest of that setup did not run either", and nothing on screen explains why.
 *
 * That is precisely the failure the kernel's plugin host exists to contain: *no plugin can crash the
 * host*. Routing pins through a command means a throw comes back as a `Result` the caller can report
 * instead of an exception that unwinds it. The kernel is doing real work here — this is not a
 * feature moved behind a token to be able to say a feature was moved behind a token.
 *
 * Deliberately NOT done: pins are not rewritten. `PinOverlay` keeps its behaviour, its DOM and its
 * tests; the plugin owns *when it is called and what happens when it fails*. Adoption is meant to be
 * implementing an interface over working code, not rewriting it.
 */
import { createCapabilityToken, type Result } from "@massingifc/core-kernel";
import { definePlugin } from "@massingifc/plugin-sdk";

/**
 * What a host must supply to run pins. Structural and **generic over the pin type**, so `PinOverlay`
 * satisfies it without this module importing the viewer or its DTOs.
 *
 * The generic is not decoration. Declaring the callback as a narrower shape made `PinOverlay`
 * unassignable — a handler that accepts only `{ref}` cannot stand in for one the overlay will call
 * with a full record. Parameter positions are contravariant, and typing the seam loosely to "make it
 * fit" would have pushed a cast into the caller, which is where a wrong assumption stops being
 * checked.
 */
export interface PinSource<TPin = unknown> {
  /** Loads model pins; resolves to how many were placed. */
  load(projectId: string): Promise<number>;
  /** Loads module-record pins (RFIs, PCOs, CORs…); resolves to how many were placed. */
  loadModulePins(projectId: string, onClick: (pin: TPin) => void): Promise<number>;
}

export interface MarkupService {
  /** Load both pin sets, reporting how many of each were placed. */
  reload(projectId: string): Promise<{ model: number; module: number }>;
}

export const MarkupToken = createCapabilityToken<MarkupService>("massing.markup");

/** Command id, exported so a caller cannot drift from the registration by retyping the string. */
export const MARKUP_RELOAD = "massing.markup.reload";

export interface MarkupPluginOptions<TPin> {
  pins: PinSource<TPin>;
  /** Called when a module pin is clicked — the viewer selects the element and updates the status. */
  onPinClick: (pin: TPin) => void;
}

export function markupPlugin<TPin>(options: MarkupPluginOptions<TPin>) {
  return definePlugin({
    id: "massing.markup",
    version: "1.0.0",
    permissions: [MARKUP_RELOAD],
    activate(context) {
      const service: MarkupService = {
        async reload(projectId: string) {
          // The counts are carried through rather than discarded: "0 pins" and "pins failed to
          // load" look identical on an empty overlay, and only one of them is a problem.
          const model = await options.pins.load(projectId);
          const mod = await options.pins.loadModulePins(projectId, options.onPinClick);
          return { model, module: mod };
        },
      };
      context.capabilities.provide(MarkupToken, service);
      context.commands.register({
        id: MARKUP_RELOAD,
        title: "Reload markup pins",
        permission: MARKUP_RELOAD,
        handler: ({ projectId }: { projectId: string }) => service.reload(projectId),
      });
    },
  });
}

/**
 * Run the reload through the kernel and report failure instead of propagating it.
 *
 * The whole point of the seam: a rejected command comes back as a failed `Result`, so a caller that
 * used to be unwound by an exception now gets a value it can act on. Pins failing is worth telling
 * the user about; it is not worth abandoning the rest of the panel build.
 */
export async function reloadMarkup(
  commands: { execute(id: string, params: unknown): Promise<Result<unknown>> },
  projectId: string,
): Promise<{ ok: boolean; detail: string }> {
  const result = await commands.execute(MARKUP_RELOAD, { projectId });
  if (!result.ok) return { ok: false, detail: result.error?.message ?? "pins failed to load" };
  const counts = result.value as { model?: number; module?: number } | undefined;
  const total = (counts?.model ?? 0) + (counts?.module ?? 0);
  return { ok: true, detail: `${total} pin${total === 1 ? "" : "s"} placed` };
}
