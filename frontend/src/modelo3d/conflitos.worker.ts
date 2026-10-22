/// <reference lib="webworker" />
/** O teste exato dos conflitos (TREELE, 22/10/2026), fora da linha principal:
 *  a triagem pelas caixas (conflitos.ts) manda só os pares que se tocam, e
 *  aqui cada par é testado pelas malhas de triângulos, com uma árvore de
 *  busca (three-mesh-bvh) por elemento — é o que faz o teste de milhares de
 *  pares levar segundos.
 *
 *  As geometrias chegam já nas coordenadas da cena, então o teste não precisa
 *  de matriz entre os dois elementos. */

import * as THREE from "three";
import { MeshBVH, type HitPointInfo } from "three-mesh-bvh";

export type PedidoTeste =
  | { tipo: "itens"; itens: { chave: number; posicoes: Float32Array; indices: Uint32Array }[] }
  | { tipo: "pares"; pares: Int32Array; modo: "interferencia" | "folga"; folga: number };

/** `achados`: [índice do par, distância, x, y, z do ponto mais próximo] por
 *  conflito confirmado. Na interferência, a distância é 0 e o ponto, NaN. */
export type RespostaTeste =
  | { tipo: "progresso"; valor: number }
  | { tipo: "pronto"; achados: Float64Array }
  | { tipo: "erro"; mensagem: string };

declare const self: DedicatedWorkerGlobalScope;

const geometrias = new Map<number, THREE.BufferGeometry>();
const arvores = new Map<number, MeshBVH>();
const IDENTIDADE = new THREE.Matrix4();
// Raio levemente torto: um raio exatamente no eixo passa por arestas e
// vértices dos modelos (alinhados aos eixos) e conta errado.
const DIRECAO = new THREE.Vector3(1, 0.000713, 0.000291).normalize();

function arvore(chave: number): MeshBVH | null {
  let a = arvores.get(chave);
  if (!a) {
    const g = geometrias.get(chave);
    if (!g) return null;
    a = new MeshBVH(g);
    arvores.set(chave, a);
  }
  return a;
}

/** Um ponto de `g` dentro do sólido da árvore: o raio a partir dele cruza as
 *  faces um número ímpar de vezes. É o caso do tubo inteiro dentro da viga,
 *  em que nenhum triângulo cruza o outro. */
function dentro(g: THREE.BufferGeometry, outra: MeshBVH): boolean {
  const p = g.getAttribute("position");
  if (!p || !p.count) return false;
  const ponto = new THREE.Vector3().fromBufferAttribute(p, 0);
  const batidas = outra.raycast(new THREE.Ray(ponto, DIRECAO), THREE.DoubleSide);
  return batidas.length % 2 === 1;
}

self.onmessage = (e: MessageEvent<PedidoTeste>) => {
  try {
    const pedido = e.data;
    if (pedido.tipo === "itens") {
      for (const item of pedido.itens) {
        const g = new THREE.BufferGeometry();
        g.setAttribute("position", new THREE.BufferAttribute(item.posicoes, 3));
        g.setIndex(new THREE.BufferAttribute(item.indices, 1));
        geometrias.set(item.chave, g);
      }
      return;
    }
    const { pares, modo, folga } = pedido;
    const achados: number[] = [];
    const t1: HitPointInfo = { point: new THREE.Vector3(), distance: 0, faceIndex: 0 };
    const t2: HitPointInfo = { point: new THREE.Vector3(), distance: 0, faceIndex: 0 };
    const total = pares.length / 2;
    for (let i = 0; i < total; i++) {
      const chaveA = pares[2 * i];
      const chaveB = pares[2 * i + 1];
      const ga = geometrias.get(chaveA);
      const gb = geometrias.get(chaveB);
      const ab = arvore(chaveB);
      if (ga && gb && ab) {
        const aa = arvore(chaveA);
        const cruza = ab.intersectsGeometry(ga, IDENTIDADE) || dentro(ga, ab) || (!!aa && dentro(gb, aa));
        if (cruza) {
          // O ponto da interferência sai da sobreposição das caixas, do lado
          // de lá (conflitos.ts): aqui só a confirmação.
          achados.push(i, 0, NaN, NaN, NaN);
        } else if (modo === "folga") {
          const r = ab.closestPointToGeometry(ga, IDENTIDADE, t1, t2, 0, folga);
          if (r && t1.distance <= folga) {
            const c = t1.point.clone().add(t2.point).multiplyScalar(0.5);
            achados.push(i, t1.distance, c.x, c.y, c.z);
          }
        }
      }
      if (i % 200 === 199) self.postMessage({ tipo: "progresso", valor: (i + 1) / total } satisfies RespostaTeste);
    }
    const saida = new Float64Array(achados);
    self.postMessage({ tipo: "pronto", achados: saida } satisfies RespostaTeste, [saida.buffer]);
  } catch (erro) {
    self.postMessage({
      tipo: "erro",
      mensagem: erro instanceof Error ? erro.message : String(erro),
    } satisfies RespostaTeste);
  }
};
