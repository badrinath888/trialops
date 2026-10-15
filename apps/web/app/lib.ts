export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}
export async function api<T = any>(path: string, body?: unknown): Promise<T> {
  const form = body instanceof FormData;
  const r = await fetch("/api" + path, {
    method: body === undefined ? "GET" : "POST",
    headers: form ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : form ? body : JSON.stringify(body),
    cache: "no-store",
  });
  if (!(r.headers.get("content-type") || "").includes("application/json"))
    throw new ApiError(
      r.status === 413
        ? "Upload must be 2 MB or smaller."
        : "The service returned an unexpected response. Reload and try again.",
      r.status,
    );
  const data = await r.json();
  if (!r.ok)
    throw new ApiError(
      typeof data.detail === "string"
        ? data.detail
        : Array.isArray(data.detail)
          ? "Check the required fields and try again."
          : typeof data.detail?.message === "string" ? data.detail.message : "Request failed",
      r.status,
    );
  if(body !== undefined && typeof window !== "undefined" && !path.endsWith("/next-step/open")) window.dispatchEvent(new Event("trialops-workflow-changed"));
  return data;
}
export const plural = (n: number, one: string, many = one + "s") => `${n} ${n === 1 ? one : many}`;
// Bring a just-opened disclosure into view only when needed; no focus change, instant under reduced motion.
export function revealOpened(el: HTMLElement) {
  requestAnimationFrame(() => {
    let top = 0;
    document.querySelectorAll<HTMLElement>("header,[class*=topbar],[class*=sticky]").forEach((n) => {
      const s = getComputedStyle(n), r = n.getBoundingClientRect();
      if ((s.position === "sticky" || s.position === "fixed") && r.top <= 1 && r.bottom < innerHeight / 2) top = Math.max(top, r.bottom);
    });
    const gap = 12, r = el.getBoundingClientRect(), fits = r.height <= innerHeight - top - 2 * gap;
    const delta = fits ? (r.top < top + gap ? r.top - (top + gap) : r.bottom > innerHeight - gap ? r.bottom - (innerHeight - gap) : 0) : r.top - (top + gap);
    if (Math.abs(delta) > 2) scrollBy({ top: delta, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  });
}
export function stamp(v: string) {
  return new Date(v).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}
export function money(v: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(v);
}
export const categories = [
  ["synchronization", "Synchronization"],
  ["document_workflow", "Document workflow"],
  ["access", "Study access"],
  ["signature", "Electronic signatures"],
  ["training", "Training"],
  ["unknown", "Unknown / needs review"],
];
export function download(name: string, data: unknown) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}
