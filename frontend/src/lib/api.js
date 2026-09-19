import { createOfflineBackend } from "./offline";

const BASE = import.meta.env.VITE_API_BASE ?? "";

// A static deployment (GitHub Pages) has no FastAPI behind it. Rather than show
// a dead page we fall back to an in-browser port of the backend (lib/offline.js)
// the first time a request cannot reach a server at all. Local development and
// CI are unaffected: a real server that answers always wins.
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

// fetch() rejects with a TypeError when it cannot reach a server at all, and an
// AbortError/TimeoutError when nothing replied in time. Either means no backend.
const unreachable = (e) =>
  e instanceof TypeError || e.name === "TimeoutError" || e.name === "AbortError";

async function withFallback(call, run, args) {
  if (offline) {
    if (typeof offline[call] !== "function") {
      throw new Error(`${call} needs the local backend; start it with start.ps1`);
    }
    return offline[call](...args);
  }
  try {
    return await run();
  } catch (e) {
    if (unreachable(e) || e.noApi) {
      offline = createOfflineBackend();
      return withFallback(call, run, args);
    }
    throw e;
  }
}

// /api/state always exists when the backend is up, so a 404/405 there means we
// are being served as static files with no API behind us. Other endpoints 404
// legitimately — an artifact that does not exist yet, a cancelled job — so only
// this probe may switch us offline.
export const getState = () =>
  withFallback("getState", async () => {
    const res = await fetch(`${BASE}/api/state`, {
      headers: { "content-type": "application/json" },
      signal: AbortSignal.timeout(20000),
    });
    if ([404, 405, 501].includes(res.status)) {
      throw Object.assign(new Error("No API at this origin"), { noApi: true });
    }
    if (!res.ok) throw new Error(res.statusText);
    if (!(res.headers.get("content-type") || "").includes("json")) {
      throw Object.assign(new Error("API did not return JSON"), { noApi: true });
    }
    return res.json();
  }, []);

const post = (call, path) => (...args) =>
  withFallback(call, () => req(path, { method: "POST", body: JSON.stringify(args[0]) }), args);

export const createJob = post("createJob", "/api/jobs");
export const previewJob = post("previewJob", "/api/preview");
export const recommendWindows = post("recommendWindows", "/api/recommend");
export const cancelJob = (id) =>
  withFallback("cancelJob", () => req(`/api/jobs/${id}`, { method: "DELETE" }), [id]);
export const setSpeed = (speed) =>
  withFallback("setSpeed", () => req("/api/speed", { method: "POST", body: JSON.stringify({ speed }) }), [{ speed }]);
export const seedDemo = () =>
  withFallback("seedDemo", () => req("/api/demo/seed", { method: "POST" }), []);
export const resetAll = () =>
  withFallback("resetAll", () => req("/api/reset", { method: "POST" }), []);
export const refreshGrid = () =>
  withFallback("refreshGrid", () => req("/api/grid/refresh", { method: "POST" }), []);
export const getArtifact = (id) =>
  withFallback("getArtifact", () => req(`/api/jobs/${id}/artifact`), [id]);

// Region imports and model training need the real backend: they write server
// state and call upstream providers. In a static build they report that plainly
// rather than pretending to work.
export const getRegionForecast = (region) =>
  withFallback("getRegionForecast", () => req(`/api/regions/${encodeURIComponent(region)}/forecast`), [region]);
export const importForecast = (body) =>
  withFallback("importForecast", () => req("/api/regions/import", { method: "POST", body: JSON.stringify(body) }), [body]);
export const trainModel = (dataset) =>
  withFallback("trainModel", () => req("/api/model/train", { method: "POST", body: JSON.stringify({ dataset }), signal: AbortSignal.timeout(45000) }), [dataset]);
export const getModelForecast = () =>
  withFallback("getModelForecast", () => req("/api/model/forecast"), []);
export const startScenario = () =>
  withFallback("startScenario", () => req("/api/demo/scenario", { method: "POST" }), []);
