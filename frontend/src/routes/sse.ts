import { Hono } from "hono";
import { streamSSE } from "hono/streaming";

export const sseRoutes = (backendUrl: string) => {
  const app = new Hono();

  // バックエンドの SSE を受け取り、クライアントに中継する
  app.get("/", async (c) => {
    return streamSSE(c, async (stream) => {
      const resp = await fetch(`${backendUrl}/sse`);
      const reader = resp.body?.getReader();
      if (!reader) return;

      const decoder = new TextDecoder();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        // "data: {...}\n\n" 形式を解析してSSEで再送出
        for (const line of chunk.split("\n")) {
          if (line.startsWith("data: ")) {
            try {
              const payload = JSON.parse(line.slice(6));
              await stream.writeSSE({
                event: payload.event ?? "status",
                data:  JSON.stringify(payload),
              });
            } catch {
              // 不正な JSON は無視
            }
          }
        }
      }
    });
  });

  return app;
};
