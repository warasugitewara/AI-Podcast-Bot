import { Context, Next } from "hono";
import { getCookie, setCookie, deleteCookie } from "hono/cookie";
import { crypto } from "bun";

const BACKEND_URL    = process.env.BACKEND_API_URL ?? "http://127.0.0.1:8080";
const SESSION_TTL_MS = 30 * 24 * 60 * 60 * 1000; // 30日

// ─── サーバー側セッションストア ──────────────────────────────
// { sessionId → { ip: string, createdAt: number } }
const sessions = new Map<string, { ip: string; createdAt: number }>();

// 期限切れセッションを定期的に掃除 (1時間ごと)
setInterval(() => {
  const now = Date.now();
  for (const [id, s] of sessions) {
    if (now - s.createdAt > SESSION_TTL_MS) sessions.delete(id);
  }
}, 60 * 60 * 1000);

// ─── IPアドレス取得 ──────────────────────────────────────────
function getIp(c: Context): string {
  return (
    c.req.header("CF-Connecting-IP") ??   // Cloudflare Tunnel 経由
    c.req.header("X-Forwarded-For")?.split(",")[0].trim() ??
    "unknown"
  );
}

// ─── セッション検証 ──────────────────────────────────────────
export function isAuthenticated(c: Context): boolean {
  const sid = getCookie(c, "sid");
  if (!sid) return false;
  const session = sessions.get(sid);
  if (!session) return false;
  if (Date.now() - session.createdAt > SESSION_TTL_MS) {
    sessions.delete(sid);
    return false;
  }
  // IP一致確認
  return session.ip === getIp(c);
}

// ─── 認証ミドルウェア ────────────────────────────────────────
export async function authMiddleware(c: Context, next: Next) {
  if (isAuthenticated(c)) return next();
  return c.redirect("/login");
}

// ─── OTP ログイン処理 ────────────────────────────────────────
export async function handleLogin(c: Context) {
  const body = await c.req.parseBody();
  const code = String(body["code"] ?? "").trim();

  if (!code) return c.redirect("/login?error=1");

  // バックエンドでOTPを検証
  const resp = await fetch(`${BACKEND_URL}/otp/verify`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ code }),
  });
  const { ok } = await resp.json() as { ok: boolean };

  if (!ok) return c.redirect("/login?error=1");

  // セッション発行
  const sid = crypto.randomUUID();
  sessions.set(sid, { ip: getIp(c), createdAt: Date.now() });

  setCookie(c, "sid", sid, {
    httpOnly:  true,
    secure:    true,
    sameSite:  "Strict",
    maxAge:    SESSION_TTL_MS / 1000,
    path:      "/",
  });
  return c.redirect("/");
}

// ─── ログアウト ──────────────────────────────────────────────
export async function handleLogout(c: Context) {
  const sid = getCookie(c, "sid");
  if (sid) sessions.delete(sid);
  deleteCookie(c, "sid", { path: "/" });
  return c.redirect("/login");
}
