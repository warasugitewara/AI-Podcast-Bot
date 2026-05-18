import { Hono } from "hono";
import { apiRoutes } from "./routes/api";
import { sseRoutes } from "./routes/sse";
import { serveStatic } from "hono/bun";
import { authMiddleware, handleLogin, handleLogout } from "./auth";

const BACKEND_URL = process.env.BACKEND_API_URL ?? "http://127.0.0.1:8080";
const PORT        = parseInt(process.env.FRONTEND_PORT ?? "3000");

const app = new Hono();

// ─── 認証ルート (認証不要) ────────────────────────────────────
app.get("/login",       (c) => c.html(Bun.file("./src/ui/login.html")));
app.post("/auth/login", handleLogin);
app.get("/auth/logout", handleLogout);

// ─── 静的ファイル + 認証保護 ─────────────────────────────────
app.use("/*", authMiddleware);
app.use("/", serveStatic({ path: "./src/ui/index.html" }));
app.use("/static/*", serveStatic({ root: "./src/ui" }));

// ─── SSE & API プロキシ (認証済みのみ) ───────────────────────
app.route("/events", sseRoutes(BACKEND_URL));
app.route("/api",    apiRoutes(BACKEND_URL));

console.log(`🎙  AI Podcast Bot Web UI: http://localhost:${PORT}`);

export default {
  port: PORT,
  fetch: app.fetch,
};
