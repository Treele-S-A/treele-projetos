/** BCF no visualizador 3D (TREELE, 22/10/2026): o formato aberto de
 *  apontamentos de BIM. Importa o .bcfzip que veio de outro programa (Revit,
 *  Solibri, Trimble Connect, BIMcollab) — cada tópico vai para a câmera e as
 *  peças dele, e vira vista ou pedido de correção aqui — e exporta as vistas
 *  da obra para o projetista abrir no programa dele. Os conflitos se exportam
 *  pelo painel de conflitos. */

import { useEffect, useRef, useState } from "react";
import { formatarData } from "../api";
import type { EstadoCena, Motor, TopicoBcf, TopicoImportado } from "./motor";
import type { PedidoVistaConflito } from "./PainelConflitos";

export interface VistaParaBcf extends EstadoCena {
  id: number;
  titulo: string;
  imagem_url: string | null;
  modelos: { disciplina: string }[];
  criada_por: { nome: string } | null;
}

/** Baixa o arquivo gerado no navegador. */
export function baixarArquivo(blob: Blob, nome: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nome;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export function hojeArquivo() {
  return new Date().toISOString().slice(0, 10);
}

export default function PainelBCF({
  motor,
  obraCodigo,
  vistas,
  aoNovaVista,
}: {
  motor: Motor;
  obraCodigo: string;
  vistas: VistaParaBcf[];
  aoNovaVista: (pedido: PedidoVistaConflito) => void;
}) {
  const [topicos, setTopicos] = useState<TopicoImportado[] | null>(null);
  const [arquivo, setArquivo] = useState<string | null>(null);
  const [ativo, setAtivo] = useState<string | null>(null);
  const [andamento, setAndamento] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const entrada = useRef<HTMLInputElement>(null);

  // As fotos importadas são URLs locais: soltas quando o painel fecha.
  useEffect(
    () => () => {
      for (const t of topicos ?? []) if (t.foto) URL.revokeObjectURL(t.foto);
    },
    [topicos],
  );

  async function importar(f: File) {
    setErro(null);
    setAndamento("Lendo o arquivo BCF…");
    try {
      const lidos = await motor.bcfImportar(new Uint8Array(await f.arrayBuffer()));
      setTopicos(lidos);
      setArquivo(f.name);
      if (!lidos.length) setErro("O arquivo não trouxe nenhum tópico.");
    } catch (e) {
      setErro(`Não deu para ler o arquivo: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setAndamento(null);
    }
  }

  async function exportarVistas() {
    setErro(null);
    try {
      const lista: TopicoBcf[] = vistas.map((v) => ({
        titulo: v.titulo,
        descricao: `Vista do sistema de projetos da Treèle${v.criada_por ? `, por ${v.criada_por.nome}` : ""}.`,
        tipo: "Issue",
        situacao: "Open",
        rotulos: [...new Set(v.modelos.map((m) => m.disciplina))],
        comentarios: [],
        guids: Object.values(v.selecao ?? {}).flat(),
        posicionar: async () => motor.aplicar(v),
        // A foto da vista é a marcada, que vale mais que uma nova.
        foto: undefined,
      }));
      for (const [i, v] of vistas.entries()) {
        if (!v.imagem_url) continue;
        try {
          const r = await fetch(v.imagem_url);
          if (r.ok) lista[i].foto = await r.blob();
        } catch {
          // Sem a imagem guardada, fotografa a tela.
        }
      }
      const blob = await motor.bcfExportar(lista, (feitos, total) =>
        setAndamento(`Montando o BCF: ${feitos} de ${total} vistas…`),
      );
      baixarArquivo(blob, `${obraCodigo}-vistas-${hojeArquivo()}.bcfzip`);
    } catch (e) {
      setErro(`Não deu para exportar: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      motor.limparCortes();
      setAndamento(null);
    }
  }

  async function ir(t: TopicoImportado) {
    setAtivo(t.guid);
    if (t.viewpoint) await motor.bcfIr(t.viewpoint);
  }

  function pedirVista(t: TopicoImportado) {
    const comentarios = t.comentarios
      .filter((c) => c.texto)
      .map((c) => `${c.autor || "?"}: ${c.texto}`)
      .join("\n");
    aoNovaVista({
      titulo: t.titulo.slice(0, 200),
      descricao: [t.descricao, comentarios && `Comentários do BCF:\n${comentarios}`].filter(Boolean).join("\n\n"),
      documentoId: null,
    });
  }

  return (
    <div className="painel-bcf">
      <span className="rotulo">BCF — troca com outros programas</span>
      <p className="silencioso" style={{ fontSize: 11.5, margin: 0 }}>
        O formato aberto de apontamentos de BIM: Revit (BCF Manager), Solibri, Trimble Connect e BIMcollab leem.
      </p>
      <div className="linha" style={{ gap: 6, flexWrap: "wrap" }}>
        <button className="botao pequeno" disabled={!!andamento} onClick={() => entrada.current?.click()}>
          Importar arquivo BCF
        </button>
        <button
          className="botao secundario pequeno"
          disabled={!!andamento || vistas.length === 0}
          onClick={exportarVistas}
          title={vistas.length ? `As ${vistas.length} vistas da obra` : "A obra ainda não tem vistas"}
        >
          Exportar as vistas
        </button>
        <input
          ref={entrada}
          type="file"
          accept=".bcfzip,.bcf,.zip"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (f) void importar(f);
          }}
        />
      </div>
      {andamento && <p className="silencioso" style={{ fontSize: 12, margin: 0 }}>{andamento}</p>}
      {erro && <p className="erro-modelo">{erro}</p>}

      {topicos && topicos.length > 0 && (
        <>
          <p style={{ fontSize: 12.5, margin: "4px 0 0" }}>
            <strong>{topicos.length} tópicos</strong> <span className="silencioso">· {arquivo}</span>
          </p>
          <ol className="lista-bcf">
            {topicos.map((t) => (
              <li key={t.guid} className={t.guid === ativo ? "atual" : undefined}>
                <button className="item-bcf" onClick={() => ir(t)} disabled={!t.viewpoint}>
                  {t.foto && <img src={t.foto} alt="" loading="lazy" />}
                  <span style={{ minWidth: 0 }}>
                    <strong>{t.titulo || "Sem título"}</strong>
                    <span className="silencioso">
                      {[t.tipo, t.situacao].filter(Boolean).join(" · ")}
                      {t.autor && ` · ${t.autor}`}
                      {t.data && !Number.isNaN(Date.parse(t.data)) && ` · ${formatarData(t.data, false)}`}
                    </span>
                  </span>
                </button>
                {t.guid === ativo && (
                  <div className="acoes-conflito">
                    {t.descricao && <p style={{ fontSize: 12.5, margin: 0, whiteSpace: "pre-wrap" }}>{t.descricao}</p>}
                    {t.comentarios.length > 0 && (
                      <ul className="comentarios-bcf">
                        {t.comentarios.map((c, i) => (
                          <li key={i}>
                            <b>{c.autor || "?"}</b>: {c.texto}
                          </li>
                        ))}
                      </ul>
                    )}
                    {!t.viewpoint && (
                      <p className="silencioso" style={{ fontSize: 12, margin: 0 }}>
                        Este tópico não trouxe ponto de vista.
                      </p>
                    )}
                    {t.viewpoint && t.guids.length > 0 && (
                      <p className="silencioso" style={{ fontSize: 11.5, margin: 0 }}>
                        {t.guids.length} peça(s) em destaque — aparecem se o modelo delas estiver aberto na cena.
                      </p>
                    )}
                    <div className="linha" style={{ gap: 6 }}>
                      <button className="botao pequeno" onClick={() => pedirVista(t)}>
                        Nova vista
                      </button>
                    </div>
                  </div>
                )}
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}
