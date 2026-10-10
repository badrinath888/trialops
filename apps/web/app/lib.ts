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
  return data;
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
