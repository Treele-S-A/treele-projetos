/// <reference lib="webworker" />
/** Converte um IFC para o formato leve de visualização (fragments), fora da
 *  linha principal: um IFC de 200 MB leva perto de um minuto, e a tela segue
 *  respondendo e mostrando o andamento (TREELE, 21/10/2026). */

import { IfcImporter } from "@thatopen/fragments";

export type PedidoConversao = { bytes: Uint8Array; wasm: string };
export type RespostaConversao =
  | { tipo: "progresso"; valor: number }
  | { tipo: "pronto"; frag: Uint8Array }
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
    avisar({ tipo: "pronto", frag }, [frag.buffer]);
  } catch (erro) {
    avisar({ tipo: "erro", mensagem: erro instanceof Error ? erro.message : String(erro) });
  }
};
