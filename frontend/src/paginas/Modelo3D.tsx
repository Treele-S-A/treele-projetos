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
import { api, ErroApi, formatarData, type StatusRevisao, type Usuario } from "../api";
import { Estado } from "../componentes";
import Marcacao, { type Gerador } from "../modelo3d/Marcacao";
import {
  converter,
  criarMotor,
  type EstadoCena,
  type Motor,
  type Propriedades,
  type Valor,
} from "../modelo3d/motor";
import { useSessao } from "../sessao";

interface ModeloSaida {
  arquivo_id: number;
  nome: string;
  obra_id: number;
  obra: string;
  documento: string;
  documento_id: number;
  titulo: string | null;
  disciplina: string;
  revisao_id: number;
  revisao: string;
  status_revisao: string;
  aviso: string | null;
  tamanho_ifc: number | null;
  modelo_url: string | null;
  tamanho_modelo: number | null;
  ifc_url: string | null;
  envio: { url: string; metodo: string; headers: Record<string, string> } | null;
}

interface VistaOut extends EstadoCena {
  id: number;
  obra_id: number;
  titulo: string;
  arquivos: number[];
  ocultos: number[];
  modelos: { arquivo_id: number; documento: string; documento_id: number; revisao: string; disciplina: string }[];
  imagem_url: string | null;
  marcacoes_url: string | null;
  criada_por: Usuario | null;
  criada_em: string;
}

/** A vista sendo criada: a foto da tela e a cena no momento do clique. */
interface RascunhoVista {
  foto: Blob;
  cena: EstadoCena;
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
  // Vista guardada (?vista=ID): os modelos vêm dela, e a cena volta como era.
  const vistaId = Number(parametros.get("vista")) || null;
  const [vista, setVista] = useState<VistaOut | null>(null);
  const [falhaVista, setFalhaVista] = useState<string | null>(null);
  const idsDaUrl = (parametros.get("arquivos") ?? "")
    .split(",")
    .map(Number)
    .filter((n) => Number.isInteger(n) && n > 0);
  const ids = vistaId ? (vista?.arquivos ?? []) : idsDaUrl;
  const chaveIds = ids.join(",");
  const { obras } = useSessao();
  const [rascunho, setRascunho] = useState<RascunhoVista | null>(null);
  const [vistas, setVistas] = useState<VistaOut[]>([]);
  // Menu do botão direito (esconder, isolar), na posição do clique.
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null);
  const [verMarcacoes, setVerMarcacoes] = useState(true);
  const [temMarcacoes, setTemMarcacoes] = useState(false);

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
    criarMotor(
      palco.current,
      (p) => vivo && setSelecao(p),
      (posicao) => vivo && setMenu(posicao),
    )
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

  useEffect(() => {
    if (!vistaId) return;
    api
      .get<VistaOut>(`/vistas/${vistaId}`)
      .then(setVista)
      .catch((e) => setFalhaVista(e instanceof ErroApi ? e.message : "Não foi possível abrir a vista."));
  }, [vistaId]);

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
        if (id === novos[0] && !vista) void motor.current?.enquadrar();
      }
      // Vista guardada: desliga o que estava desligado e volta câmera, cortes
      // e seleção.
      if (vista && motor.current) {
        for (const id of vista.ocultos) {
          atualizar(id, { visivel: false });
          await motor.current.mostrarModelo(String(id), false);
        }
        await motor.current.aplicar(vista);
        // As marcações voltam para a cena: no ângulo da vista, idênticas à
        // imagem anexada; mexendo a câmera, deformam.
        if (vista.marcacoes_url) {
          try {
            await motor.current.mostrarMarcacoes(vista.marcacoes_url, vista.camera);
            setTemMarcacoes(true);
          } catch {
            setTemMarcacoes(false);
          }
        }
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

  /** Tudo de volta: elementos escondidos, cortes e disciplinas desligadas. */
  async function mostrarTudo() {
    setMenu(null);
    for (const m of modelos) {
      if (!m.visivel && m.etapa === "pronto") {
        atualizar(m.id, { visivel: true });
        await motor.current?.mostrarModelo(String(m.id), true);
      }
    }
    await motor.current?.mostrarTudo();
  }

  useEffect(() => {
    if (!menu) return;
    const fechar = (e: Event) => {
      if (e instanceof KeyboardEvent && e.key !== "Escape") return;
      setMenu(null);
    };
    window.addEventListener("keydown", fechar);
    window.addEventListener("pointerdown", fechar);
    return () => {
      window.removeEventListener("keydown", fechar);
      window.removeEventListener("pointerdown", fechar);
    };
  }, [menu]);

  function alternarCorte() {
    const novo = !corte;
    setCorte(novo);
    motor.current?.corte(novo);
  }

  const modeloDaSelecao = selecao ? modelos.find((m) => String(m.id) === selecao.modelId) : null;
  const obraId = vista?.obra_id ?? modelos.find((m) => m.info)?.info?.obra_id;
  const obra = obras.find((o) => o.id === obraId);
  const todosProntos = modelos.length > 0 && modelos.every((m) => m.etapa === "pronto" || m.etapa === "erro");

  const carregarVistas = () => {
    if (!obraId) return;
    api
      .get<VistaOut[]>(`/obras/${obraId}/vistas`)
      .then(setVistas)
      .catch(() => setVistas([]));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(carregarVistas, [obraId]);

  async function novaVista() {
    if (!motor.current) return;
    const cena = await motor.current.estado();
    const foto = await motor.current.fotografar(cena.camera);
    setRascunho({ foto, cena });
  }

  if (vistaId && falhaVista) {
    return <p className="erro-modelo">{falhaVista}</p>;
  }
  if (!ids.length && !vistaId) {
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
          <button
            className="botao pequeno"
            disabled={!todosProntos || !obraId}
            onClick={novaVista}
            title="Fotografa a tela para marcar e guardar, ou pedir correção"
          >
            Nova vista
          </button>
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
          <button className="botao secundario pequeno" onClick={mostrarTudo}>
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
          Botão esquerdo arrasta para mover; aperte a roda e arraste para girar; gire a roda para aproximar.
          Clique num elemento para ver as propriedades, ou use o botão direito para esconder ou isolar.
          {corte && " Com o corte ligado, dê um duplo clique numa face para cortar ali."}
        </p>

        {vista && (
          <div className="vista-aberta">
            <span className="rotulo">Vista aberta</span>
            <strong>{vista.titulo}</strong>
            <span className="silencioso" style={{ fontSize: 12 }}>
              {vista.criada_por?.nome} · {formatarData(vista.criada_em)}
            </span>
            {temMarcacoes && (
              <label className="opcao-aviso" style={{ margin: "4px 0 0" }}>
                <input
                  type="checkbox"
                  checked={verMarcacoes}
                  onChange={(e) => {
                    setVerMarcacoes(e.target.checked);
                    motor.current?.verMarcacoes(e.target.checked);
                  }}
                />
                Mostrar as marcações
              </label>
            )}
            {temMarcacoes && (
              <span className="silencioso" style={{ fontSize: 11.5 }}>
                Idênticas à imagem no ângulo da vista; mexendo a câmera, elas deformam.
              </span>
            )}
            <button
              className="link-pequeno"
              style={{ alignSelf: "flex-start" }}
              onClick={async () => {
                await motor.current?.aplicar(vista);
              }}
            >
              Voltar ao ângulo da vista
            </button>
          </div>
        )}

        {vistas.length > 0 && (
          <div>
            <span className="rotulo">Vistas da obra</span>
            <ul className="lista-vistas">
              {vistas.slice(0, 30).map((v) => (
                <li key={v.id} className={v.id === vista?.id ? "atual" : undefined}>
                  <a href={`/modelos?vista=${v.id}`} title={v.modelos.map((m) => m.documento).join(", ")}>
                    {v.imagem_url && <img src={v.imagem_url} alt="" loading="lazy" />}
                    <span>
                      <strong>{v.titulo}</strong>
                      <span className="silencioso">
                        {v.criada_por?.nome} · {formatarData(v.criada_em, false)}
                      </span>
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}
      </aside>

      <div className="visualizador-palco" ref={palco} onContextMenu={(e) => e.preventDefault()}>
        {menu && (
          <div
            className="menu-modelo"
            style={{ left: menu.x, top: menu.y }}
            role="menu"
            onPointerDown={(e) => e.stopPropagation()}
          >
            <strong>{selecao?.nome ?? "Elemento"}</strong>
            <button
              role="menuitem"
              onClick={async () => {
                setMenu(null);
                await motor.current?.esconderSelecao();
              }}
            >
              Esconder
            </button>
            <button
              role="menuitem"
              onClick={async () => {
                setMenu(null);
                await motor.current?.isolarSelecao();
              }}
            >
              Isolar
            </button>
            <button role="menuitem" onClick={mostrarTudo}>
              Mostrar tudo
            </button>
          </div>
        )}
        {falhaMotor && (
          <p className="erro-modelo" style={{ position: "absolute", inset: "auto 16px 16px" }}>
            O visualizador não abriu neste navegador: {falhaMotor}
          </p>
        )}
      </div>

      {rascunho && obraId && (
        <PainelVista
          rascunho={rascunho}
          obraId={obraId}
          modelos={modelos}
          documentoSugerido={modeloDaSelecao?.info?.documento_id ?? null}
          podePedir={obra?.permissoes.includes("solicitar_revisao") ?? false}
          podeMarcar={obra?.permissoes.includes("autorizar_revisao") ?? false}
          podeReprovar={obra?.permissoes.includes("publicar") ?? false}
          aoFechar={(criou) => {
            setRascunho(null);
            if (criou) carregarVistas();
          }}
        />
      )}

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

/* ------------------------------------------------------- vista e correção */

interface Membro {
  usuario_id: number;
  papel: string;
  usuario: Usuario;
}

type Caminho = "solicitar" | "reprovar";

/** O que acontece com cada documento da cena se ele for marcado: pedido de
 *  revisão (liberado), reprovação (em análise, só o coordenador) ou nada,
 *  com o motivo. */
function caminhoDe(
  d: ModeloSaida,
  podePedir: boolean,
  podeReprovar: boolean,
): { caminho: Caminho | null; motivo: string } {
  if (d.status_revisao === "liberado_para_obra") {
    return podePedir
      ? { caminho: "solicitar", motivo: "pedir revisão" }
      : { caminho: null, motivo: "seu papel não pede revisão" };
  }
  if (d.status_revisao === "em_revisao") {
    return podeReprovar
      ? { caminho: "reprovar", motivo: `reprovar a R${d.revisao} em análise` }
      : { caminho: null, motivo: "em análise: só o coordenador reprova" };
  }
  return { caminho: null, motivo: `R${d.revisao} não aceita correção (nem liberada, nem em análise)` };
}

interface Resultado {
  documento: ModeloSaida;
  caminho: Caminho;
  erro: string | null;
}

/** Marcar a foto, dar um título e guardar a vista — e, se for o caso, pedir a
 *  correção de uma ou mais disciplinas da cena com a vista anexada. Cada
 *  documento segue o próprio estado: liberado vira solicitação de revisão
 *  (com os projetistas marcados); em análise vira reprovação, com o motivo. */
function PainelVista({
  rascunho,
  obraId,
  modelos,
  documentoSugerido,
  podePedir,
  podeMarcar,
  podeReprovar,
  aoFechar,
}: {
  rascunho: RascunhoVista;
  obraId: number;
  modelos: ItemModelo[];
  documentoSugerido: number | null;
  podePedir: boolean;
  podeMarcar: boolean;
  podeReprovar: boolean;
  aoFechar: (criou: boolean) => void;
}) {
  const gerador = useRef<Gerador>({ foto: async () => rascunho.foto, marcacoes: async () => null });
  const [titulo, setTitulo] = useState("");
  const podeCorrigir = podePedir || podeReprovar;
  const [pedir, setPedir] = useState(podeCorrigir);
  const documentos = modelos
    .filter((m) => m.info && m.etapa === "pronto")
    .map((m) => m.info!)
    .filter((d, i, todos) => todos.findIndex((x) => x.documento_id === d.documento_id) === i);
  // Começa marcado o documento do elemento selecionado; com uma disciplina
  // só na cena, ela.
  const [escolhidos, setEscolhidos] = useState<Set<number>>(() => {
    const inicial = documentoSugerido ?? (documentos.length === 1 ? documentos[0].documento_id : null);
    const d = documentos.find((x) => x.documento_id === inicial);
    return d && caminhoDe(d, podePedir, podeReprovar).caminho ? new Set([d.documento_id]) : new Set();
  });
  const [descricao, setDescricao] = useState("");
  const [projetistas, setProjetistas] = useState<Membro[]>([]);
  const [marcados, setMarcados] = useState<Set<number>>(new Set());
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [feito, setFeito] = useState<{ resultados: Resultado[] } | null>(null);

  useEffect(() => {
    if (!podeMarcar) return;
    api
      .get<Membro[]>(`/obras/${obraId}/membros`)
      .then((ms) => setProjetistas(ms.filter((m) => m.papel === "projetista" && m.usuario.ativo)))
      .catch(() => setProjetistas([]));
  }, [obraId, podeMarcar]);

  const selecionados = pedir
    ? documentos
        .filter((d) => escolhidos.has(d.documento_id))
        .map((d) => ({ documento: d, caminho: caminhoDe(d, podePedir, podeReprovar).caminho! }))
        .filter((x) => x.caminho)
    : [];
  const temSolicitacao = selecionados.some((x) => x.caminho === "solicitar");
  const temReprovacao = selecionados.some((x) => x.caminho === "reprovar");

  async function concluir() {
    if (!titulo.trim()) return setErro("Dê um título à vista (ex.: Pilar P12 invade a porta da sala).");
    if (pedir && !selecionados.length) return setErro("Marque ao menos uma disciplina para corrigir.");
    if (selecionados.length && descricao.trim().length < 10)
      return setErro(temReprovacao && !temSolicitacao ? "Escreva o motivo da reprovação." : "Descreva o que deve mudar.");
    setEnviando(true);
    setErro(null);
    try {
      const png = await gerador.current.foto();
      const desenhos = await gerador.current.marcacoes();
      type Envio = { url: string; metodo: string; headers: Record<string, string> };
      const criada = await api.post<{ vista: VistaOut; envio_imagem: Envio; envio_marcacoes: Envio | null }>(
        `/obras/${obraId}/vistas`,
        {
          titulo: titulo.trim(),
          arquivos: modelos.map((m) => m.id),
          ocultos: modelos.filter((m) => !m.visivel).map((m) => m.id),
          com_marcacoes: !!desenhos,
          ...rascunho.cena,
        },
      );
      if (desenhos && criada.envio_marcacoes) {
        const r = await fetch(criada.envio_marcacoes.url, {
          method: criada.envio_marcacoes.metodo,
          headers: criada.envio_marcacoes.headers,
          body: desenhos,
        });
        if (!r.ok) throw new Error("As marcações não subiram. Tente de novo.");
      }
      const envio = await fetch(criada.envio_imagem.url, {
        method: criada.envio_imagem.metodo,
        headers: criada.envio_imagem.headers,
        body: png,
      });
      if (!envio.ok) throw new Error("A imagem da vista não subiu. Tente de novo.");
      await api.post(`/vistas/${criada.vista.id}/imagem`);
      // Um pedido por disciplina; a falha de uma não segura as outras.
      const resultados: Resultado[] = [];
      for (const { documento, caminho } of selecionados) {
        try {
          if (caminho === "solicitar") {
            await api.post(`/documentos/${documento.documento_id}/solicitacoes`, {
              descricao: descricao.trim(),
              vista_id: criada.vista.id,
              mencionados: [...marcados],
            });
          } else {
            await api.post(`/revisoes/${documento.revisao_id}/reprovar`, {
              observacao: descricao.trim(),
              vista_id: criada.vista.id,
            });
          }
          resultados.push({ documento, caminho, erro: null });
        } catch (e) {
          resultados.push({
            documento,
            caminho,
            erro: e instanceof ErroApi || e instanceof Error ? e.message : "Não deu certo.",
          });
        }
      }
      setFeito({ resultados });
    } catch (e) {
      setErro(e instanceof ErroApi || e instanceof Error ? e.message : "Não foi possível guardar a vista.");
    } finally {
      setEnviando(false);
    }
  }

  if (feito) {
    const certos = feito.resultados.filter((r) => !r.erro);
    return (
      <div className="painel-vista-fundo">
        <div className="painel-vista" role="dialog" aria-label="Vista guardada">
          <strong>
            {feito.resultados.length ? `Vista guardada · ${certos.length} de ${feito.resultados.length} correções feitas` : "Vista guardada"}
          </strong>
          {feito.resultados.length === 0 ? (
            <p className="silencioso" style={{ fontSize: 13 }}>
              Ela aparece na lista de vistas da obra, para qualquer pessoa da equipe reabrir.
            </p>
          ) : (
            <ul className="resultado-correcoes">
              {feito.resultados.map((r) => (
                <li key={r.documento.documento_id} className={r.erro ? "com-erro" : undefined}>
                  <span className="mono">{r.documento.documento}</span>{" "}
                  {r.erro
                    ? `— não deu certo: ${r.erro}`
                    : r.caminho === "reprovar"
                      ? `— R${r.documento.revisao} reprovada; quem enviou foi avisado.`
                      : podeMarcar
                        ? "— revisão autorizada; o projetista da última revisão e os marcados foram avisados."
                        : "— pedido enviado para o coordenador autorizar."}{" "}
                  <Link to={`/documentos/${r.documento.documento_id}`}>abrir</Link>
                </li>
              ))}
            </ul>
          )}
          {feito.resultados.length > 0 && (
            <p className="silencioso" style={{ fontSize: 12.5 }}>
              A imagem marcada vai junto de cada uma, com o link para abrir esta vista no 3D.
            </p>
          )}
          <button className="botao secundario pequeno" onClick={() => aoFechar(true)}>
            Voltar ao modelo
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="painel-vista-fundo">
      <div className="painel-vista" role="dialog" aria-label="Nova vista">
        <div className="linha">
          <strong>Nova vista</strong>
          <div className="espaco" />
          <button
            className="assistente-fechar"
            onClick={() => aoFechar(false)}
            aria-label="Fechar"
            disabled={enviando}
          >
            ×
          </button>
        </div>
        <Marcacao imagem={rascunho.foto} aoMudar={(g) => (gerador.current = g)} />
        <label className="campo" style={{ display: "block", marginTop: 10 }}>
          <span className="rotulo">Título da vista</span>
          <input
            value={titulo}
            maxLength={200}
            onChange={(e) => setTitulo(e.target.value)}
            placeholder="Ex.: Pilar P12 invade a porta da sala"
            disabled={enviando}
          />
        </label>

        {podeCorrigir && (
          <label className="opcao-aviso" style={{ marginTop: 8 }}>
            <input
              type="checkbox"
              checked={pedir}
              onChange={(e) => setPedir(e.target.checked)}
              disabled={enviando}
            />
            Pedir correção com esta vista
            <span className="silencioso">— a imagem marcada vai junto</span>
          </label>
        )}

        {pedir && (
          <div className="pedido-vista">
            <span className="rotulo">Disciplinas a corrigir</span>
            <ul className="disciplinas-correcao">
              {documentos.map((d) => {
                const { caminho, motivo } = caminhoDe(d, podePedir, podeReprovar);
                return (
                  <li key={d.documento_id} className={caminho ? undefined : "sem-caminho"}>
                    <label className="linha" style={{ gap: 8, alignItems: "flex-start" }}>
                      <input
                        type="checkbox"
                        checked={escolhidos.has(d.documento_id)}
                        disabled={enviando || !caminho}
                        onChange={(e) => {
                          const novo = new Set(escolhidos);
                          if (e.target.checked) novo.add(d.documento_id);
                          else novo.delete(d.documento_id);
                          setEscolhidos(novo);
                        }}
                      />
                      <span>
                        <span className="mono" style={{ fontWeight: 600 }}>
                          {d.disciplina} · {d.documento} R{d.revisao}
                        </span>
                        {d.titulo && <span className="silencioso"> · {d.titulo}</span>}
                        <span className={`caminho-correcao ${caminho ?? "nenhum"}`}>{motivo}</span>
                      </span>
                    </label>
                  </li>
                );
              })}
            </ul>
            {temReprovacao && (
              <p className="nota-reprovacao">
                As marcadas em análise são <strong>reprovadas</strong> com esta vista e o texto abaixo: quem enviou
                recebe o aviso e o e-mail, e a correção vem numa revisão nova.
              </p>
            )}
            <label className="campo" style={{ display: "block", marginTop: 8 }}>
              <span className="rotulo">
                {temReprovacao && !temSolicitacao ? "Motivo da reprovação" : "O que deve mudar"}
              </span>
              <textarea
                value={descricao}
                onChange={(e) => setDescricao(e.target.value)}
                rows={3}
                maxLength={4000}
                disabled={enviando}
                placeholder="Ex.: A tubulação de esgoto atravessa a viga V12 no 3º pavimento. Desviar a tubulação ou prever furo na viga."
              />
            </label>
            {temSolicitacao && podeMarcar && projetistas.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <span className="rotulo">Marcar projetistas (nos pedidos de revisão)</span>
                <div className="linha" style={{ gap: 12, flexWrap: "wrap", marginTop: 4 }}>
                  {projetistas.map((p) => (
                    <label key={p.usuario_id} className="opcao-aviso" style={{ margin: 0 }}>
                      <input
                        type="checkbox"
                        checked={marcados.has(p.usuario_id)}
                        disabled={enviando}
                        onChange={(e) => {
                          const novo = new Set(marcados);
                          if (e.target.checked) novo.add(p.usuario_id);
                          else novo.delete(p.usuario_id);
                          setMarcados(novo);
                        }}
                      />
                      {p.usuario.nome}
                    </label>
                  ))}
                </div>
                <p className="silencioso" style={{ fontSize: 12, margin: "4px 0 0" }}>
                  O projetista que subiu a última revisão é avisado sempre; os marcados também recebem o aviso
                  e o e-mail.
                </p>
              </div>
            )}
          </div>
        )}

        {erro && <p className="erro-modelo">{erro}</p>}
        <div className="linha" style={{ gap: 8, marginTop: 12 }}>
          <button className="botao" disabled={enviando} onClick={concluir}>
            {enviando
              ? "Guardando…"
              : selecionados.length === 0
                ? "Guardar vista"
                : selecionados.length === 1
                  ? selecionados[0].caminho === "reprovar"
                    ? "Guardar e reprovar"
                    : "Guardar e pedir correção"
                  : `Guardar e corrigir ${selecionados.length} disciplinas`}
          </button>
          <button className="botao secundario pequeno" disabled={enviando} onClick={() => aoFechar(false)}>
            Cancelar
          </button>
        </div>
      </div>
    </div>
  );
}
