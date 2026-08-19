import { toast } from "../ui/feedback";

/** POST a PDF and save it. Cookie-bearing GET is how SameSite=Lax leaks a session. */
export async function downloadPostedPdf(
  api: { url(path: string): string; authHeaders(): Record<string, string> },
  path: string,
  fallbackName: string,
): Promise<void> {
  const r = await fetch(api.url(path), { method: "POST", headers: api.authHeaders() });
  if (!r.ok) throw new Error((await r.text()) || `HTTP ${r.status}`);
  const blob = await r.blob();
  const a = document.createElement("a");
  const cd = r.headers.get("Content-Disposition") || "";
  const named = /filename="([^"]+)"/.exec(cd)?.[1];
  a.href = URL.createObjectURL(blob);
  a.download = named || fallbackName;
  a.click();
  URL.revokeObjectURL(a.href);
}

export function camStatementPath(pid: string, rid: string): string {
  return `/projects/${pid}/cam/statement/${rid}.pdf`;
}

export async function downloadCamStatement(
  api: { url(path: string): string; authHeaders(): Record<string, string> },
  pid: string,
  rid: string,
): Promise<void> {
  try {
    await downloadPostedPdf(api, camStatementPath(pid, rid), `cam-statement-${rid}.pdf`);
  } catch (e) {
    toast(`Statement failed: ${(e as Error).message}`, "error");
  }
}
