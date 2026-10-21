/// <reference lib="webworker" />
/** Converte um IFC para o formato leve de visualização (fragments), fora da
 *  linha principal: um IFC de 200 MB leva perto de um minuto, e a tela segue
 *  respondendo e mostrando o andamento (TREELE, 21/10/2026). */

import { IfcImporter } from "@thatopen/fragments";
import { analisarIfc, type ResumoIfc } from "./resumo-ifc";

export type PedidoConversao = { bytes: Uint8Array; wasm: string };
export type RespostaConversao =
  | { tipo: "progresso"; valor: number }
  | { tipo: "pronto"; frag: Uint8Array; resumo: ResumoIfc | null; indice: Uint8Array | null }
  | { tipo: "erro"; mensagem: string };

declare const self: DedicatedWorkerGlobalScope;

self.onmessage = async (e: MessageEvent<PedidoConversao>) => {
  const avisar = (r: RespostaConversao, transferir: Transferable[] = []) => self.postMessage(r, transferir);
  try {
    const importer = new IfcImporter();
    importer.wasm = { absolute: true, path: e.data.wasm };
    const frag = await importer.process({
      bytes: e.data.bytes,
      progressCallback: (valor) => avisar({ tipo: "progresso", valor }),
    });
    // O resumo de quantitativos (para o chat) sai do mesmo IFC; se falhar, o
    // modelo 3D vale do mesmo jeito.
    // E o índice completo de parâmetros, já em gzip (20 MB viram ~1 MB).
    let resumo: ResumoIfc | null = null;
    let indice: Uint8Array | null = null;
    try {
      const analise = await analisarIfc(e.data.bytes, { path: e.data.wasm, absolute: true });
      resumo = analise.resumo;
      const bruto = new Blob([JSON.stringify(analise.indice)]).stream();
      indice = new Uint8Array(await new Response(bruto.pipeThrough(new CompressionStream("gzip"))).arrayBuffer());
    } catch {
      resumo = null;
      indice = null;
    }
    avisar({ tipo: "pronto", frag, resumo, indice }, indice ? [frag.buffer, indice.buffer] : [frag.buffer]);
  } catch (erro) {
    avisar({ tipo: "erro", mensagem: erro instanceof Error ? erro.message : String(erro) });
  }
};
