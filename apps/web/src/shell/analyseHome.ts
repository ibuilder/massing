import { ANALYSE_TASK_KEYS } from "./destinations";

/**
 * UX-DUP-DESTINATIONS — one Analyse home with three named tasks.
 *
 * Model Health, Model Analysis and BIM KPIs were three rail destinations whose names did not say
 * which question they answered. The renderers stay; the rail shows one Analyse entry. Each task
 * hops to the existing dest (`navigate`), so readiness deep-links keep working.
 */

export const ANALYSE_TASKS: readonly {
  key: (typeof ANALYSE_TASK_KEYS)[number];
  icon: string;
  label: string;
  question: string;
}[] = [
  { key: "__modelqa__", icon: "✅", label: "Check the model",
    question: "Completeness, clashes, IDS — is the model coordinated enough to issue from?" },
  { key: "__modelanalysis__", icon: "🔬", label: "Read the model",
    question: "What is in it — quantities, elements, the facts the other rooms consume." },
  { key: "__bimkpi__", icon: "📊", label: "ISO 19650 scorecard",
    question: "Information-management KPIs against the CDE / delivery plan, not a second health check." },
];

type AnalyseCtx = {
  root: HTMLElement;
  activeKey: string | null;
  bar(title: string, back: () => void): HTMLElement;
  buildNav(): void;
  renderHome(): Promise<void>;
  navigate(key: string): void;
  hasDest(key: string): boolean;
};

export function renderAnalyseHome(ctx: AnalyseCtx): void {
  const root = ctx.root;
  root.replaceChildren();
  root.appendChild(ctx.bar("🔬 Analyse", () => {
    ctx.activeKey = null;
    void ctx.renderHome();
    ctx.buildNav();
  }));
  const intro = document.createElement("div");
  intro.className = "meta";
  intro.style.margin = "2px 0 12px";
  intro.textContent = "Three jobs, one place. Pick the question — each opens the panel that already "
    + "answers it. Nothing here is a fourth scorecard.";
  root.appendChild(intro);
  const list = document.createElement("div");
  list.style.cssText = "display:flex;flex-direction:column;gap:8px";
  for (const t of ANALYSE_TASKS) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "dash-card";
    card.style.cssText = "cursor:pointer;text-align:left;display:block;width:100%";
    card.disabled = !ctx.hasDest(t.key);
    const title = document.createElement("div");
    title.style.fontWeight = "600";
    title.textContent = `${t.icon} ${t.label}`;
    const q = document.createElement("div");
    q.className = "meta";
    q.textContent = t.question;
    card.append(title, q);
    card.onclick = () => { if (ctx.hasDest(t.key)) ctx.navigate(t.key); };
    list.appendChild(card);
  }
  root.appendChild(list);
}
