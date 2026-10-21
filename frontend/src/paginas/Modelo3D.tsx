/** Visualizador 3D de IFC (TREELE, 21/10/2026). Abre um ou vários modelos de
 *  uma vez (/modelos?arquivos=12,34): cada disciplina é um modelo, e dá para
 *  ligar e desligar cada uma, clicar num elemento para ver as propriedades,
 *  isolar, esconder e cortar.
 *
 *  Na primeira abertura de um IFC, a tela converte o arquivo para o formato
 *  leve de visualização e, se a pessoa for da equipe, guarda o resultado: as
 *  aberturas seguintes, de qualquer pessoa, levam segundos. */

import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ErroApi, type StatusRevisao } from "../api";
import { Estado } from "../componentes";
import { converter, criarMotor, type Motor, type Propriedades, type Valor } from "../modelo3d/motor";

interface ModeloSaida {
  arquivo_id: number;
  nome: string;
  obra_id: number;
  obra: string;
  documento: string;
  documento_id: number;
  titulo: string | null;
  disciplina: string;
  revisao: string;
  status_revisao: string;
  aviso: string | null;
  tamanho_ifc: number | null;
  modelo_url: string | null;
  tamanho_modelo: number | null;
  ifc_url: string | null;
  envio: { url: string; metodo: string; headers: Record<string, string> } | null;
}

type Etapa = "buscando" | "baixando" | "convertendo" | "carregando" | "pronto" | "erro";

interface ItemModelo {
  id: number;
  info: ModeloSaida | null;
  etapa: Etapa;
  progresso: number;
  visivel: boolean;
  erro: string | null;
  guardado: "nao" | "guardando" | "guardado" | "falhou";
}

const ROTULO_ETAPA: Record<Etapa, string> = {
  buscando: "Preparando…",
  baixando: "Baixando",
  convertendo: "Convertendo o IFC (só na primeira vez)",
  carregando: "Montando o modelo…",
  pronto: "",
  erro: "",
};

function mb(bytes: number | null | undefined): string {
  if (!bytes) return "";
  return bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1).replace(".", ",")} MB` : `${Math.ceil(bytes / 1024)} KB`;
}

/** Baixa com andamento. O tamanho vem do servidor (o storage nem sempre manda). */
async function baixar(url: string, tamanho: number | null, aoProgredir: (p: number) => void): Promise<Uint8Array> {
  const r = await fetch(url);
  if (!r.ok || !r.body) throw new Error(`Falha ao baixar (${r.status}).`);
  const total = tamanho || Number(r.headers.get("content-length")) || 0;
  const leitor = r.body.getReader();
  const pedacos: Uint8Array[] = [];
  let recebido = 0;
  for (;;) {
    const { value, done } = await leitor.read();
    if (done) break;
    pedacos.push(value);
    recebido += value.byteLength;
    if (total) aoProgredir(Math.min(1, recebido / total));
  }
  const tudo = new Uint8Array(recebido);
  let pos = 0;
  for (const p of pedacos) {
    tudo.set(p, pos);
    pos += p.byteLength;
  }
  return tudo;
}

function Linha({ nome, valor }: { nome: string; valor: Valor }) {
  return (
    <tr>
      <th>{nome}</th>
      <td>{typeof valor === "boolean" ? (valor ? "Sim" : "Não") : String(valor)}</td>
    </tr>
  );
}

export default function Modelo3D() {
  const [parametros, setParametros] = useSearchParams();
  const ids = (parametros.get("arquivos") ?? "")
    .split(",")
    .map(Number)
    .filter((n) => Number.isInteger(n) && n > 0);
  const chaveIds = ids.join(",");

  const palco = useRef<HTMLDivElement>(null);
  const motor = useRef<Motor | null>(null);
  const abertos = useRef<Set<number>>(new Set());
  const [modelos, setModelos] = useState<ItemModelo[]>([]);
  const [selecao, setSelecao] = useState<Propriedades | null>(null);
  const [corte, setCorte] = useState(false);
  const [falhaMotor, setFalhaMotor] = useState<string | null>(null);
  const [pronto, setPronto] = useState(false);

  function atualizar(id: number, mudanca: Partial<ItemModelo>) {
    setModelos((lista) => lista.map((m) => (m.id === id ? { ...m, ...mudanca } : m)));
  }

  // O motor nasce uma vez com a tela e morre com ela.
  useEffect(() => {
    let vivo = true;
    if (!palco.current) return;
    criarMotor(palco.current, (p) => vivo && setSelecao(p))
      .then((m) => {
        if (!vivo) return m.descartar();
        motor.current = m;
        setPronto(true);
      })
      .catch((e) => setFalhaMotor(e instanceof Error ? e.message : String(e)));
    return () => {
      vivo = false;
      motor.current?.descartar();
      motor.current = null;
      abertos.current.clear();
    };
  }, []);

  // Abre, um por vez, os modelos pedidos que ainda não estão na cena.
  useEffect(() => {
    if (!pronto) return;
    const novos = ids.filter((id) => !abertos.current.has(id));
    if (!novos.length) return;
    novos.forEach((id) => abertos.current.add(id));
    setModelos((lista) => [
      ...lista,
      ...novos.map<ItemModelo>((id) => ({
        id, info: null, etapa: "buscando", progresso: 0, visivel: true, erro: null, guardado: "nao",
      })),
    ]);
    (async () => {
      for (const id of novos) {
        await abrir(id);
        if (id === novos[0]) void motor.current?.enquadrar();
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pronto, chaveIds]);

  async function abrir(id: number) {
    try {
      const info = await api.get<ModeloSaida>(`/arquivos/${id}/modelo`);
      atualizar(id, { info, etapa: "baixando", progresso: 0 });
      let frag: Uint8Array;
      if (info.modelo_url) {
        frag = await baixar(info.modelo_url, info.tamanho_modelo, (p) => atualizar(id, { progresso: p }));
      } else {
        const ifc = await baixar(info.ifc_url!, info.tamanho_ifc, (p) => atualizar(id, { progresso: p }));
        atualizar(id, { etapa: "convertendo", progresso: 0 });
        frag = await converter(ifc, (p) => atualizar(id, { progresso: p }));
        if (info.envio) void guardar(id, info.envio, frag.slice());
      }
      atualizar(id, { etapa: "carregando" });
      await motor.current?.carregar(String(id), frag);
      atualizar(id, { etapa: "pronto" });
    } catch (e) {
      atualizar(id, {
        etapa: "erro",
        erro: e instanceof ErroApi || e instanceof Error ? e.message : "Não foi possível abrir o modelo.",
      });
    }
  }

  /** Guarda a conversão no servidor: as próximas aberturas pulam o IFC. */
  async function guardar(id: number, envio: NonNullable<ModeloSaida["envio"]>, frag: Uint8Array) {
    atualizar(id, { guardado: "guardando" });
    try {
      const r = await fetch(envio.url, { method: envio.metodo, headers: envio.headers, body: new Blob([frag as BlobPart]) });
      atualizar(id, { guardado: r.ok ? "guardado" : "falhou" });
    } catch {
      atualizar(id, { guardado: "falhou" });
    }
  }

  async function alternarVisivel(m: ItemModelo) {
    atualizar(m.id, { visivel: !m.visivel });
    await motor.current?.mostrarModelo(String(m.id), !m.visivel);
  }

  function remover(m: ItemModelo) {
    // Tirar da URL recarrega a tela sem ele: o motor recomeça limpo.
    const resto = ids.filter((id) => id !== m.id);
    if (!resto.length) return;
    setParametros({ arquivos: resto.join(",") });
    window.location.reload();
  }

  function alternarCorte() {
    const novo = !corte;
    setCorte(novo);
    motor.current?.corte(novo);
  }

  const modeloDaSelecao = selecao ? modelos.find((m) => String(m.id) === selecao.modelId) : null;
  const obraId = modelos.find((m) => m.info)?.info?.obra_id;

  if (!ids.length) {
    return <p className="silencioso">Nenhum modelo pedido. Abra um IFC pela página do documento.</p>;
  }

  return (
    <div className="visualizador">
      <aside className="visualizador-lado">
        <div className="cabecalho-visualizador">
          <span className="rotulo">Visualizador 3D</span>
          {obraId && (
            <Link className="silencioso" to={`/obras/${obraId}/acervo`} style={{ fontSize: 12.5 }}>
              ← Voltar ao acervo
            </Link>
          )}
        </div>

        <ul className="lista-modelos">
          {modelos.map((m) => (
            <li key={m.id} className={m.etapa === "erro" ? "com-erro" : undefined}>
              <label className="linha" style={{ gap: 8, alignItems: "flex-start" }}>
                <input
                  type="checkbox"
                  checked={m.visivel}
                  disabled={m.etapa !== "pronto"}
                  onChange={() => alternarVisivel(m)}
                  aria-label={`Mostrar ${m.info?.documento ?? "modelo"}`}
                />
                <span style={{ minWidth: 0 }}>
                  <span className="mono" style={{ fontSize: 12.5, fontWeight: 600 }}>
                    {m.info ? `${m.info.documento} R${m.info.revisao}` : `Arquivo ${m.id}`}
                  </span>
                  {m.info?.titulo && <span className="titulo-modelo">{m.info.titulo}</span>}
                  {m.info && (
                    <span className="linha" style={{ gap: 6, marginTop: 4 }}>
                      <Estado status={m.info.status_revisao as StatusRevisao} />
                      <span className="silencioso mono" style={{ fontSize: 11 }}>
                        {m.info.disciplina}
                      </span>
                    </span>
                  )}
                </span>
              </label>
              {m.etapa !== "pronto" && m.etapa !== "erro" && (
                <div className="andamento-modelo">
                  <span>
                    {ROTULO_ETAPA[m.etapa]}
                    {m.etapa === "baixando" && m.info && ` ${mb(m.info.modelo_url ? m.info.tamanho_modelo : m.info.tamanho_ifc)}`}
                  </span>
                  {(m.etapa === "baixando" || m.etapa === "convertendo") && (
                    <div className="progresso-lote">
                      <span style={{ width: `${Math.round(m.progresso * 100)}%` }} />
                    </div>
                  )}
                </div>
              )}
              {m.erro && <p className="erro-modelo">{m.erro}</p>}
              {m.info?.aviso && m.etapa === "pronto" && <p className="aviso-modelo">{m.info.aviso}</p>}
              {m.guardado === "guardando" && <p className="silencioso nota-modelo">Guardando a conversão…</p>}
              {m.guardado === "guardado" && (
                <p className="silencioso nota-modelo">Conversão guardada: da próxima vez abre na hora.</p>
              )}
              {m.guardado === "falhou" && (
                <p className="silencioso nota-modelo">Não deu para guardar a conversão; abre do IFC de novo.</p>
              )}
              {ids.length > 1 && (
                <button className="link-pequeno" onClick={() => remover(m)}>
                  Tirar da cena
                </button>
              )}
            </li>
          ))}
        </ul>

        <div className="ferramentas-modelo">
          <button className="botao secundario pequeno" onClick={() => motor.current?.enquadrar()}>
            Enquadrar
          </button>
          <button className="botao secundario pequeno" disabled={!selecao} onClick={() => motor.current?.isolarSelecao()}>
            Isolar seleção
          </button>
          <button
            className="botao secundario pequeno"
            disabled={!selecao}
            onClick={() => motor.current?.esconderSelecao()}
          >
            Esconder seleção
          </button>
          <button className="botao secundario pequeno" onClick={() => motor.current?.mostrarTudo()}>
            Mostrar tudo
          </button>
          <button className={`botao pequeno ${corte ? "" : "secundario"}`} onClick={alternarCorte}>
            {corte ? "Corte ligado" : "Corte"}
          </button>
          {corte && (
            <button className="botao secundario pequeno" onClick={() => motor.current?.limparCortes()}>
              Limpar cortes
            </button>
          )}
        </div>
        <p className="silencioso dica-modelo">
          Arraste para girar, botão direito para mover, roda para aproximar. Clique num elemento para
          ver as propriedades.
          {corte && " Com o corte ligado, dê um duplo clique numa face para cortar ali."}
        </p>
      </aside>

      <div className="visualizador-palco" ref={palco}>
        {falhaMotor && (
          <p className="erro-modelo" style={{ position: "absolute", inset: "auto 16px 16px" }}>
            O visualizador não abriu neste navegador: {falhaMotor}
          </p>
        )}
      </div>

      {selecao && (
        <aside className="visualizador-propriedades" aria-label="Propriedades do elemento">
          <div className="linha" style={{ alignItems: "flex-start" }}>
            <div style={{ minWidth: 0 }}>
              <strong>{selecao.nome ?? "Elemento sem nome"}</strong>
              <div className="silencioso mono" style={{ fontSize: 11.5 }}>
                {selecao.categoria}
                {modeloDaSelecao?.info && ` · ${modeloDaSelecao.info.documento} R${modeloDaSelecao.info.revisao}`}
              </div>
            </div>
            <div className="espaco" />
            <button className="assistente-fechar" onClick={() => setSelecao(null)} aria-label="Fechar">
              ×
            </button>
          </div>
          <table className="tabela-propriedades">
            <tbody>
              {selecao.guid && <Linha nome="GlobalId" valor={selecao.guid} />}
              {selecao.atributos
                .filter(([n]) => n !== "Name" && n !== "GlobalId")
                .map(([n, v]) => (
                  <Linha key={n} nome={n} valor={v} />
                ))}
            </tbody>
          </table>
          {selecao.grupos.map((g, i) => (
            <details key={i} open={i < 2}>
              <summary>{g.titulo}</summary>
              <table className="tabela-propriedades">
                <tbody>
                  {g.linhas.map(([n, v], j) => (
                    <Linha key={j} nome={n} valor={v} />
                  ))}
                </tbody>
              </table>
            </details>
          ))}
        </aside>
      )}
    </div>
  );
}
