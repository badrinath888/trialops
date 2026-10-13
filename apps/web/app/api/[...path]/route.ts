import { readFileSync } from "node:fs";
export const runtime = "nodejs";
function internalKey() {
  return process.env.INTERNAL_KEY_FILE
    ? readFileSync(process.env.INTERNAL_KEY_FILE, "utf8").trim()
    : process.env.INTERNAL_KEY || "";
}
async function proxy(request: Request) {
  const incoming = new URL(request.url),
    path = incoming.pathname.slice(4);
  if (
    !/^\/(auth|intake|catalog|dashboard|cases|jobs|runs|knowledge|operations|roi|feedback|members|invitations|export|health|metrics|policies|visits|notifications|notification-preferences|evaluations|walkthrough|assessment-demo|contacts|waiting-queue|my-work|external-response|recurrence|prevention-plans|readiness|improvements)(\/|$)/.test(
      path,
    )
  )
    return Response.json({ detail: "Unknown endpoint" }, { status: 404 });
  if (request.method === "POST") {
    const origin = request.headers.get("origin");
    const permitted = process.env.APP_ORIGIN || incoming.origin;
    if (origin !== permitted)
      return Response.json(
        { detail: "Request origin was rejected. Reload the application." },
        { status: 403 },
      );
  }
  const length = request.headers.get("content-length");
  if (length && Number(length) > 2108000)
    return Response.json(
      { detail: "Upload must be 2 MB or smaller." },
      { status: 413 },
    );
  try {
    const body =
      request.method === "POST" ? await request.arrayBuffer() : undefined;
    if (body && body.byteLength > 2108000)
      return Response.json(
        { detail: "Request is too large." },
        { status: 413 },
      );
    const upstream = await fetch(
      `${process.env.API_URL || "http://api:8000"}${path}${incoming.search}`,
      {
        method: request.method,
        headers: {
          "Content-Type":
            request.headers.get("content-type") || "application/json",
          "X-Response-Token": path === "/external-response" ? request.headers.get("x-response-token") || "" : "",
          Cookie: request.headers.get("cookie") || "",
          "X-Internal-Key": internalKey(),
          // Forwarded headers are client-controlled unless a trusted proxy (Caddy, which overwrites them) fronts the app.
          "X-Client-IP": process.env.TRUST_PROXY === "true"
            ? request.headers.get("x-forwarded-for")?.split(",").pop()?.trim() || "local"
            : "local",
        },
        body,
        cache: "no-store",
        signal: AbortSignal.timeout(210000),
      },
    );
    if (upstream.status >= 500)
      return Response.json(
        { detail: "The service is temporarily unavailable. Please try again." },
        { status: 502 },
      );
    const headers = new Headers({
      "Content-Type":
        upstream.headers.get("content-type") || "application/json",
      "Cache-Control": "no-store",
    });
    const disposition = upstream.headers.get("content-disposition");
    if (disposition) headers.set("Content-Disposition", disposition);
    for (const cookie of upstream.headers.getSetCookie())
      headers.append("Set-Cookie", cookie);
    return new Response(await upstream.arrayBuffer(), {
      status: upstream.status,
      headers,
    });
  } catch {
    return Response.json(
      { detail: "The service is temporarily unavailable. Please try again." },
      { status: 502 },
    );
  }
}
export { proxy as GET, proxy as POST };
