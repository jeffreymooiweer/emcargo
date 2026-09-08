/** Opt-in visual-test transport to a real isolated FastAPI TestClient.
 * Never registered in production builds; no mock calculations or export responses.
 */
import type { Plugin } from "vite";
import { mkdir, writeFile, readFile, unlink } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { join } from "node:path";

export function reviewBridge(): Plugin {
  const directory = join(process.cwd(), ".review-bridge");
  return {
    name: "emcargo-visual-review-bridge", apply: "serve",
    async configureServer(server) {
      await mkdir(directory, { recursive: true });
      server.middlewares.use(async (req, res, next) => {
        if (!req.url?.startsWith("/api/")) return next();
        const id = randomUUID();
        const input = join(directory, `${id}.request.json`);
        const output = join(directory, `${id}.response.json`);
        try {
          const chunks: Buffer[] = [];
          for await (const chunk of req) chunks.push(Buffer.from(chunk));
          await writeFile(input, JSON.stringify({ method: req.method, url: req.url, body: Buffer.concat(chunks).toString("base64"), contentType: req.headers["content-type"] }));
          const deadline = Date.now() + 25000;
          let response;
          while (Date.now() < deadline) {
            try { response = JSON.parse(await readFile(output, "utf8")); break; } catch { await new Promise(resolve => setTimeout(resolve, 35)); }
          }
          if (!response) throw new Error("Visual review worker is unavailable");
          res.statusCode = response.status;
          for (const [key, value] of Object.entries(response.headers)) res.setHeader(key, String(value));
          res.end(Buffer.from(response.body, "base64"));
        } catch { res.statusCode = 503; res.end("Visual review worker is unavailable"); }
        finally { await Promise.all([unlink(input).catch(() => {}), unlink(output).catch(() => {})]); }
      });
    },
  };
}
