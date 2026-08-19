import { describe, expect, it } from "vitest";

import { attachDictation, speechRecognitionCtor, type SpeechRecCtor } from "./dictate";

describe("speechRecognitionCtor", () => {
  it("returns null when the engine is absent — the mic must not appear", () => {
    expect(speechRecognitionCtor({} as Window & { SpeechRecognition?: SpeechRecCtor })).toBeNull();
  });

  it("prefers the standard name, then the webkit prefix", () => {
    const Std = class {} as unknown as SpeechRecCtor;
    const Webkit = class {} as unknown as SpeechRecCtor;
    expect(speechRecognitionCtor({ SpeechRecognition: Std } as never)).toBe(Std);
    expect(speechRecognitionCtor({ webkitSpeechRecognition: Webkit } as never)).toBe(Webkit);
  });
});

describe("attachDictation", () => {
  it("returns null when there is no constructor", () => {
    const ta = document.createElement("textarea");
    expect(attachDictation(ta, null)).toBeNull();
  });

  it("appends spoken text to the note", () => {
    class FakeRec {
      lang = "";
      continuous = false;
      interimResults = false;
      onresult: ((ev: { resultIndex: number; results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null = null;
      onend: (() => void) | null = null;
      onerror: (() => void) | null = null;
      start(): void {
        this.onresult?.({ resultIndex: 0, results: [[{ transcript: "crack at grid C" }]] });
      }
      stop(): void { /* noop */ }
    }
    const ta = document.createElement("textarea");
    ta.value = "Punch:";
    const btn = attachDictation(ta, FakeRec as unknown as SpeechRecCtor);
    expect(btn).not.toBeNull();
    expect(btn!.textContent).toBe("🎙 Dictate");
    btn!.click();
    expect(ta.value).toBe("Punch: crack at grid C");
  });
});
