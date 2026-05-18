import { Hono } from "hono";

export const apiRoutes = (backendUrl: string) => {
  const app = new Hono();

  // 汎用プロキシ: /api/* → バックエンド /*
  app.all("/*", async (c) => {
    const path     = c.req.path.replace(/^\/api/, "");
    const url      = `${backendUrl}${path}`;
    const method   = c.req.method;
    const headers  = new Headers(c.req.raw.headers);
    headers.delete("host");

    const body = ["GET", "HEAD"].includes(method) ? undefined : await c.req.raw.arrayBuffer();

    const resp = await fetch(url, { method, headers, body });
    return new Response(resp.body, {
      status:  resp.status,
      headers: resp.headers,
    });
  });

  return app;
};
