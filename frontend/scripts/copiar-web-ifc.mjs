// Copia para public/web-ifc/ o que o visualizador 3D carrega em tempo de
// execução pelo nome original: o WASM do web-ifc (leitor de IFC) e o worker
// do fragments (o pacote não o exporta para o bundler). Roda antes do build e
// do dev (scripts "prebuild" e "predev").
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const raiz = join(dirname(fileURLToPath(import.meta.url)), "..");
const destino = join(raiz, "public", "web-ifc");
mkdirSync(destino, { recursive: true });
for (const nome of ["web-ifc.wasm", "web-ifc-mt.wasm"]) {
  copyFileSync(join(raiz, "node_modules", "web-ifc", nome), join(destino, nome));
}
copyFileSync(
  join(raiz, "node_modules", "@thatopen", "fragments", "dist", "Worker", "worker.min.mjs"),
  join(destino, "fragments-worker.mjs"),
);
console.log("web-ifc e worker do fragments copiados para public/web-ifc/");
