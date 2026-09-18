import { createOfflineBackend } from "./offline";

const BASE = import.meta.env.VITE_API_BASE ?? "";

// A static deployment has no FastAPI behind it. Rather than show a dead page we
// fall back to an in-browser port of the backend (lib/offline.js) the first time
// a request fails to reach a server at all. Only a transport failure triggers
// this — an HTTP error means a server IS there and answered, so it is surfaced
// as normal and local development and CI behave exactly as before.
let offline = null;

async function req(path, options) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "content-type": "application/json" },
    signal: AbortSignal.timeout(20000),
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail =
        typeof body.detail === "string"
          ? body.detail
          : body.detail?.map((e) => e.msg).join("; ") || detail;
    } catch {}
    throw new Error(detail);
  }
  return res.json();
}

// fetch() rejects with a TypeError when it cannot reach a server at all, and
// an AbortError/TimeoutError when nothing replied in time. Either means there is
// no backend, whatever the endpoint.
const unreachable = (e) =>
  e instanceof TypeError || e.name === "TimeoutError" || e.name === "AbortError";

// `call` names the offline method; `run` performs the real request.
async function withFallback(call, run, args) {
  if (offline) return offline[call](...args);
  try {
    return await run();
  } catch (e) {
    if (unreachable(e) || e.noApi) {
      offline = createOfflineBackend();
      return offline[call](...args);
    }
    throw e;
  }
}

const post = (call, path) => (...args) =>
  withFallback(call, () => req(path(...args), { method: "POST", body: JSON.stringify(args[0]) }), args);

// /api/state always exists when the backend is up, so a 404/405 there means we
// are being served as static files (GitHub Pages, `python -m http.server`) with
// no API behind us. Other endpoints 404 legitimately — an artifact that does not
// exist yet, a cancelled job — so only this probe may switch us offline.
export const getState = () =>
  withFallback("getState", async () => {
    const res = await fetch(`${BASE}/api/state`, {
      headers: { "content-type": "application/json" },
      signal: AbortSignal.timeout(20000),
    });
    if (res.status === 404 || res.status === 405 || res.status === 501) {
      throw Object.assign(new Error("No API at this origin"), { noApi: true });
    }
    if (!res.ok) throw new Error(res.statusText);
    const type = res.headers.get("content-type") || "";
    if (!type.includes("json")) {
      throw Object.assign(new Error("API did not return JSON"), { noApi: true });
    }
    return res.json();
  }, []);
export const previewJob = post("previewJob", () => "/api/preview");
export const createJob = post("createJob", () => "/api/jobs");
export const setSpeed = (speed) =>
  withFallback("setSpeed", () => req("/api/speed", { method: "POST", body: JSON.stringify({ speed }) }), [{ speed }]);
export const seedDemo = () =>
  withFallback("seedDemo", () => req("/api/demo/seed", { method: "POST" }), []);
export const resetAll = () =>
  withFallback("resetAll", () => req("/api/reset", { method: "POST" }), []);
export const refreshGrid = () =>
  withFallback("refreshGrid", () => req("/api/grid/refresh", { method: "POST" }), []);
export const cancelJob = (id) =>
  withFallback("cancelJob", () => req(`/api/jobs/${id}`, { method: "DELETE" }), [id]);
export const getArtifact = (id) =>
  withFallback("getArtifact", () => req(`/api/jobs/${id}/artifact`), [id]);
