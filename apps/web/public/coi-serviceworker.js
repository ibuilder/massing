/*! coi-serviceworker v0.1.7 — Guido Zuidhof and contributors, MIT.
 * Enables cross-origin isolation (COOP/COEP) on hosts that can't set headers (e.g. GitHub
 * Pages), so web-ifc / @thatopen/fragments multithreaded WASM (SharedArrayBuffer) works.
 * Used only by the Pages build; the deployed nginx/Tauri builds set the headers natively. */
let coepCredentialless = false;
if (typeof window === "undefined") {
  self.addEventListener("install", () => self.skipWaiting());
  self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

  self.addEventListener("message", (ev) => {
    if (!ev.data) return;
    if (ev.data.type === "deregister") {
      self.registration.unregister()
        .then(() => self.clients.matchAll())
        .then((clients) => clients.forEach((client) => client.navigate(client.url)));
    } else if (ev.data.type === "coepCredentialless") {
      coepCredentialless = ev.data.value;
    }
  });

  self.addEventListener("fetch", (event) => {
    const r = event.request;
    if (r.cache === "only-if-cached" && r.mode !== "same-origin") return;
    const request = (coepCredentialless && r.mode === "no-cors")
      ? new Request(r, { credentials: "omit" }) : r;
    event.respondWith(fetch(request).then((response) => {
      if (response.status === 0) return response;
      const headers = new Headers(response.headers);
      headers.set("Cross-Origin-Embedder-Policy", coepCredentialless ? "credentialless" : "require-corp");
      if (!coepCredentialless) headers.set("Cross-Origin-Resource-Policy", "cross-origin");
      headers.set("Cross-Origin-Opener-Policy", "same-origin");
      return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
    }).catch((e) => console.error(e)));
  });
} else {
  (() => {
    const reloadedBySelf = window.sessionStorage.getItem("coiReloadedBySelf");
    window.sessionStorage.removeItem("coiReloadedBySelf");
    const coepDegrading = reloadedBySelf === "coepdegrade";
    const n = navigator;
    if (n.serviceWorker && n.serviceWorker.controller) {
      n.serviceWorker.controller.postMessage({ type: "coepCredentialless", value: coepDegrading });
    }
    if (!window.crossOriginIsolated && !coepDegrading) {
      if (!n.serviceWorker) return;
      n.serviceWorker.register(window.document.currentScript.src).then((registration) => {
        registration.addEventListener("updatefound", () =>
          window.sessionStorage.setItem("coiReloadedBySelf", "updatefound"));
        if (registration.active && !n.serviceWorker.controller) {
          window.sessionStorage.setItem("coiReloadedBySelf", "notcontrolling");
          window.location.reload();
        }
      });
    }
  })();
}
