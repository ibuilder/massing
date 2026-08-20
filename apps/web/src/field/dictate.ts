/**
 * R24-FIELD-MODE ① — dictation on the capture note.
 *
 * Gloves and sun make typing a 3-line note the expensive part of a punch item. Missing
 * SpeechRecognition is a hidden button, never a fake mic that does nothing.
 */
export type SpeechRecCtor = new () => {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((ev: { resultIndex: number; results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  start(): void;
  stop(): void;
};

export function speechRecognitionCtor(
  win: Window & { webkitSpeechRecognition?: SpeechRecCtor; SpeechRecognition?: SpeechRecCtor } = window,
): SpeechRecCtor | null {
  return win.SpeechRecognition ?? win.webkitSpeechRecognition ?? null;
}

/** Append spoken text to `target`. Returns the button, or null when the engine is absent. */
export function attachDictation(
  target: HTMLTextAreaElement,
  Ctor: SpeechRecCtor | null = speechRecognitionCtor(),
): HTMLButtonElement | null {
  if (!Ctor) return null;
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "tool-btn";
  btn.textContent = "🎙 Dictate";
  btn.title = "Speak the note (on-device speech recognition when the browser has it)";
  let rec: InstanceType<SpeechRecCtor> | null = null;
  btn.onclick = () => {
    if (rec) { rec.stop(); rec = null; btn.textContent = "🎙 Dictate"; return; }
    rec = new Ctor();
    rec.lang = "en-US";
    rec.continuous = true;
    rec.interimResults = false;
    rec.onresult = (ev) => {
      let chunk = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        chunk += ev.results[i]?.[0]?.transcript ?? "";
      }
      const t = chunk.trim();
      if (!t) return;
      target.value = target.value ? `${target.value.trimEnd()} ${t}` : t;
      target.dispatchEvent(new Event("input"));
    };
    rec.onend = () => { rec = null; btn.textContent = "🎙 Dictate"; };
    rec.onerror = () => { rec = null; btn.textContent = "🎙 Dictate"; };
    rec.start();
    btn.textContent = "■ Stop";
  };
  return btn;
}
