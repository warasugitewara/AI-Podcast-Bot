import { Hono } from "hono";
import { apiRoutes } from "./routes/api";
import { sseRoutes } from "./routes/sse";
import { serveStatic } from "hono/bun";

const BACKEND_URL = process.env.BACKEND_API_URL ?? "http://127.0.0.1:8080";
const PORT        = parseInt(process.env.FRONTEND_PORT ?? "3000");

const app = new Hono();

// ─── 静的ファイル (Web UI) ───────────────────────────────
app.use("/", serveStatic({ path: "./src/ui/index.html" }));
app.use("/static/*", serveStatic({ root: "./src/ui" }));

// ─── SSE (バックエンドからのステータスを中継) ───────────────
app.route("/events", sseRoutes(BACKEND_URL));

// ─── API プロキシ ────────────────────────────────────────
app.route("/api", apiRoutes(BACKEND_URL));

console.log(`🎙  AI Podcast Bot Web UI: http://localhost:${PORT}`);

export default {
  port: PORT,
  fetch: app.fetch,
};
