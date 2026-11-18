import { cp, mkdir, readdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
const web = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = resolve(web, "presentation");
const target = resolve(web, process.env.MACROLAB_BUILD_DIR ?? "dist");
const allowed = new Set([
  "demo",
  "case-study",
  "publication",
  "presentation.css",
]);
for (const name of await readdir(source)) {
  if (!allowed.has(name))
    throw new Error(`Unexpected presentation path: ${name}`);
  await mkdir(target, { recursive: true });
  await cp(resolve(source, name), resolve(target, name), { recursive: true });
}
