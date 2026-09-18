const BASE = import.meta.env.VITE_API_BASE ?? "";
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
export const getState = () => req("/api/state");
export const createJob = (body) =>
  req("/api/jobs", { method: "POST", body: JSON.stringify(body) });
export const previewJob = (body) =>
  req("/api/preview", { method: "POST", body: JSON.stringify(body) });
export const cancelJob = (id) => req(`/api/jobs/${id}`, { method: "DELETE" });
export const setSpeed = (speed) =>
  req("/api/speed", { method: "POST", body: JSON.stringify({ speed }) });
export const seedDemo = () => req("/api/demo/seed", { method: "POST" });
export const resetAll = () => req("/api/reset", { method: "POST" });
export const refreshGrid = () => req("/api/grid/refresh", { method: "POST" });
export const getArtifact = (id) => req(`/api/jobs/${id}/artifact`);
