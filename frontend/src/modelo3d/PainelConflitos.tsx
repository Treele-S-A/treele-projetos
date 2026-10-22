/** Conflitos entre disciplinas no visualizador 3D (TREELE, 22/10/2026,
 *  protótipo). A pessoa escolhe um conjunto — pronto ou montado por ela: quais
 *  disciplinas e categorias formam o grupo A e o grupo B, o tipo de teste e a
 *  tolerância — e o navegador testa os modelos abertos na cena.
 *
 *  Protótipo: os conjuntos montados ficam neste navegador, e o resultado,
 *  só na tela (não fica guardado nem tem status ainda). */

import { useEffect, useMemo, useRef, useState } from "react";
import {
  conjuntosProntos,
  nomeCategoria,
  type ConjuntoConflito,
  type Conflito,
  type Fase,
  type GrupoConflito,
} from "./conflitos";
import type { Motor } from "./motor";

export interface ModeloConflito {
  modelId: string;
  disciplina: string;
  documento: string;
  documentoId: number;
  revisao: string;
}

/** O que a tela leva para a nova vista de um conflito. */
export interface PedidoVistaConflito {
  titulo: string;
  descricao: string;
  documentoId: number | null;
}

const ROTULO_FASE: Record<Fase, string> = {
  elementos: "Separando os elementos dos grupos…",
  triagem: "Triando os pares que se tocam…",
  geometria: "Lendo a geometria dos pares…",
  teste: "Testando as malhas…",
  nomes: "Organizando os resultados…",
};

function chaveGuardados(obraId: number) {
  return `treele.conflitos.${obraId}`;
}

function lerGuardados(obraId: number): ConjuntoConflito[] {
  try {
    const bruto = localStorage.getItem(chaveGuardados(obraId));
    return bruto ? (JSON.parse(bruto) as ConjuntoConflito[]) : [];
  } catch {
    return [];
  }
}

function gravarGuardados(obraId: number, lista: ConjuntoConflito[]) {
  try {
    localStorage.setItem(chaveGuardados(obraId), JSON.stringify(lista));
  } catch {
    // Sem armazenamento (janela anônima): o conjunto vale só agora.
  }
}

function medidaTexto(m: number): string {
  if (m < 0.01) return `${Math.round(m * 1000)} mm`;
  return `${(m * 100).toFixed(m < 0.1 ? 1 : 0).replace(".", ",")} cm`;
}

function nomeCurto(nome: string | null): string {
  if (!nome) return "sem nome";
  // Revit: "Família:Tipo:123456" — o número do fim não diz nada a ninguém.
  return nome.replace(/:\d+$/, "");
}

export default function PainelConflitos({
  motor,
  obraId,
  modelos,
  aoNovaVista,
}: {
  motor: Motor;
  obraId: number;
  modelos: ModeloConflito[];
  aoNovaVista: (pedido: PedidoVistaConflito) => void;
}) {
  const disciplinas = useMemo(() => [...new Set(modelos.map((m) => m.disciplina))].sort(), [modelos]);
  const prontos = useMemo(() => conjuntosProntos(disciplinas), [disciplinas]);
  const [guardados, setGuardados] = useState<ConjuntoConflito[]>(() => lerGuardados(obraId));
  const todos = [...guardados, ...prontos];
  const [escolhido, setEscolhido] = useState<string>(() => todos[0]?.id ?? "");
  const conjunto = todos.find((c) => c.id === escolhido) ?? todos[0];
  const [editando, setEditando] = useState<ConjuntoConflito | null>(null);
  const [andamento, setAndamento] = useState<{ fase: Fase; valor: number } | null>(null);
  const [resultado, setResultado] = useState<{
    conjunto: ConjuntoConflito;
    conflitos: Conflito[];
    segundos: number;
  } | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ativo, setAtivo] = useState<number | null>(null);
  const [ignorados, setIgnorados] = useState<Set<number>>(new Set());
  const rodando = useRef(false);

  // Categorias de cada disciplina na cena, com a contagem.
  const [categorias, setCategorias] = useState<Record<string, Record<string, number>>>({});
  useEffect(() => {
    let vivo = true;
    (async () => {
      const porDisciplina: Record<string, Record<string, number>> = {};
      for (const m of modelos) {
        const contagem = await motor.categorias(m.modelId);
        const alvo = (porDisciplina[m.disciplina] ??= {});
        for (const [c, n] of Object.entries(contagem)) alvo[c] = (alvo[c] ?? 0) + n;
      }
      if (vivo) setCategorias(porDisciplina);
    })();
    return () => {
      vivo = false;
    };
  }, [motor, modelos]);

  const modeloDe = (modelId: string) => modelos.find((m) => m.modelId === modelId);

  async function rodar(c: ConjuntoConflito) {
    // Uma detecção por vez: duas ao mesmo tempo disputam o mesmo worker.
    if (rodando.current) return;
    rodando.current = true;
    setAndamento({ fase: "elementos", valor: 0 });
    setErro(null);
    setResultado(null);
    setAtivo(null);
    setIgnorados(new Set());
    await motor.focarConflito(null);
    const inicio = performance.now();
    try {
      const conflitos = await motor.detectarConflitos(
        modelos.map((m) => ({ modelId: m.modelId, disciplina: m.disciplina })),
        c,
        (fase, valor) => setAndamento({ fase, valor }),
      );
      setResultado({ conjunto: c, conflitos, segundos: (performance.now() - inicio) / 1000 });
    } catch (e) {
      setErro(e instanceof Error ? e.message : "A detecção falhou.");
    } finally {
      rodando.current = false;
      setAndamento(null);
    }
  }

  async function focar(c: Conflito) {
    setAtivo(c.id);
    await motor.focarConflito(c);
  }

  function guardar(c: ConjuntoConflito) {
    // Conjunto pronto editado vira um conjunto próprio.
    const proprio = c.id.startsWith("pronto-") ? { ...c, id: `c${Date.now()}` } : c;
    const lista = [proprio, ...guardados.filter((g) => g.id !== proprio.id)];
    setGuardados(lista);
    gravarGuardados(obraId, lista);
    setEscolhido(proprio.id);
    return proprio;
  }

  function apagar(c: ConjuntoConflito) {
    const lista = guardados.filter((g) => g.id !== c.id);
    setGuardados(lista);
    gravarGuardados(obraId, lista);
    setEscolhido(lista[0]?.id ?? prontos[0]?.id ?? "");
  }

  function pedirVista(c: Conflito) {
    const a = modeloDe(c.a.modelId);
    const b = modeloDe(c.b.modelId);
    const cA = nomeCategoria(c.a.categoria);
    const cB = nomeCategoria(c.b.categoria);
    const medida =
      c.tipo === "interferencia" ? `entra cerca de ${medidaTexto(c.medida)}` : `fica a ${medidaTexto(c.medida)}`;
    const nomeB = nomeCurto(c.b.nome);
    aoNovaVista({
      titulo: `Conflito: ${cA} × ${cB}${nomeB.length <= 16 ? ` ${nomeB}` : ""}${
        a && b ? ` (${a.disciplina} × ${b.disciplina})` : ""
      }`,
      descricao:
        `${cA} "${nomeCurto(c.a.nome)}"${a ? ` (${a.documento} R${a.revisao})` : ""} ${medida} ` +
        `${c.tipo === "interferencia" ? "em" : "de"} ${cB.toLowerCase()} "${nomeCurto(c.b.nome)}"` +
        `${b ? ` (${b.documento} R${b.revisao})` : ""}, na cota ${c.centro[1].toFixed(2).replace(".", ",")} m. ` +
        "Ajustar o traçado ou prever a passagem com o projetista de estrutura.",
      documentoId: a?.documentoId ?? null,
    });
  }

  const visiveis = resultado?.conflitos.filter((c) => !ignorados.has(c.id)) ?? [];

  return (
    <div className="painel-conflitos">
      <span className="rotulo">Conflitos entre disciplinas</span>
      {disciplinas.length < 1 ? (
        <p className="silencioso" style={{ fontSize: 12.5 }}>
          Abra os modelos das disciplinas na cena para testar.
        </p>
      ) : (
        <>
          <label className="campo" style={{ display: "block" }}>
            <select value={conjunto?.id ?? ""} onChange={(e) => setEscolhido(e.target.value)} disabled={!!andamento}>
              {guardados.length > 0 && (
                <optgroup label="Seus conjuntos">
                  {guardados.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.nome}
                    </option>
                  ))}
                </optgroup>
              )}
              <optgroup label="Prontos">
                {prontos.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.nome}
                  </option>
                ))}
              </optgroup>
            </select>
          </label>
          {conjunto && <ResumoConjunto conjunto={conjunto} />}
          <div className="linha" style={{ gap: 6, flexWrap: "wrap" }}>
            <button className="botao pequeno" disabled={!conjunto || !!andamento} onClick={() => conjunto && rodar(conjunto)}>
              Detectar
            </button>
            <button
              className="botao secundario pequeno"
              disabled={!conjunto || !!andamento}
              onClick={() => conjunto && setEditando(conjunto)}
            >
              Configurar…
            </button>
            <button
              className="botao secundario pequeno"
              disabled={!!andamento}
              onClick={() =>
                setEditando({
                  ...prontos[0],
                  id: `c${Date.now()}`,
                  nome: "Novo conjunto",
                })
              }
            >
              Novo
            </button>
            {conjunto && !conjunto.id.startsWith("pronto-") && (
              <button className="link-pequeno" disabled={!!andamento} onClick={() => apagar(conjunto)}>
                Apagar
              </button>
            )}
          </div>
        </>
      )}

      {andamento && (
        <div className="andamento-modelo">
          <span>{ROTULO_FASE[andamento.fase]}</span>
          <div className="progresso-lote">
            <span style={{ width: `${Math.round(andamento.valor * 100)}%` }} />
          </div>
        </div>
      )}
      {erro && <p className="erro-modelo">{erro}</p>}

      {resultado && (
        <div>
          <p style={{ margin: "4px 0", fontSize: 13 }}>
            <strong>
              {resultado.conflitos.length === 0
                ? "Nenhum conflito"
                : `${resultado.conflitos.length} conflito${resultado.conflitos.length > 1 ? "s" : ""}`}
            </strong>{" "}
            <span className="silencioso">
              · {resultado.conjunto.nome} · {resultado.segundos.toFixed(1).replace(".", ",")} s
              {ignorados.size > 0 && ` · ${ignorados.size} ignorado${ignorados.size > 1 ? "s" : ""}`}
            </span>
          </p>
          <ol className="lista-conflitos">
            {visiveis.slice(0, 300).map((c) => {
              const a = modeloDe(c.a.modelId);
              const b = modeloDe(c.b.modelId);
              return (
                <li key={c.id} className={c.id === ativo ? "atual" : undefined}>
                  <button className="conflito-item" onClick={() => focar(c)}>
                    <span className="conflito-numero">{c.id}</span>
                    <span style={{ minWidth: 0 }}>
                      <span className="conflito-lado">
                        <b>{nomeCategoria(c.a.categoria)}</b>
                        {c.a.localIds.length > 1 && ` (${c.a.localIds.length} peças)`} · {nomeCurto(c.a.nome)}
                      </span>
                      <span className="conflito-lado">
                        × <b>{nomeCategoria(c.b.categoria)}</b> · {nomeCurto(c.b.nome)}
                      </span>
                      <span className="silencioso conflito-meta">
                        {a?.disciplina} × {b?.disciplina} ·{" "}
                        {c.tipo === "interferencia" ? `entra ~${medidaTexto(c.medida)}` : `a ${medidaTexto(c.medida)}`} ·
                        cota {c.centro[1].toFixed(2).replace(".", ",")} m
                      </span>
                    </span>
                  </button>
                  {c.id === ativo && (
                    <div className="linha" style={{ gap: 6, margin: "4px 0 2px 30px" }}>
                      <button className="botao pequeno" onClick={() => pedirVista(c)}>
                        Nova vista
                      </button>
                      <button
                        className="botao secundario pequeno"
                        onClick={async () => {
                          setIgnorados(new Set([...ignorados, c.id]));
                          setAtivo(null);
                          await motor.focarConflito(null);
                        }}
                      >
                        Ignorar
                      </button>
                    </div>
                  )}
                </li>
              );
            })}
          </ol>
          {visiveis.length > 300 && (
            <p className="silencioso" style={{ fontSize: 12 }}>
              Mostrando 300 de {visiveis.length}. Afine o conjunto (menos categorias, mais tolerância).
            </p>
          )}
          {ignorados.size > 0 && (
            <button className="link-pequeno" onClick={() => setIgnorados(new Set())}>
              Mostrar os ignorados
            </button>
          )}
        </div>
      )}

      {editando && (
        <EditorConjunto
          inicial={editando}
          disciplinas={disciplinas}
          categorias={categorias}
          aoFechar={() => setEditando(null)}
          aoGuardar={(c, detectarJa) => {
            const salvo = guardar(c);
            setEditando(null);
            if (detectarJa) void rodar(salvo);
          }}
        />
      )}
    </div>
  );
}

function ResumoConjunto({ conjunto }: { conjunto: ConjuntoConflito }) {
  const grupo = (g: GrupoConflito) => {
    const discs = g.disciplinas.join(", ") || "nenhuma disciplina";
    if (g.categorias.length) return `${discs} (${g.categorias.map(nomeCategoria).join(", ")})`;
    const fora = [...new Set((g.excluir ?? []).map(nomeCategoria))];
    return `${discs} (tudo${fora.length ? `, menos ${fora.slice(0, 4).join(", ")}${fora.length > 4 ? "…" : ""}` : ""})`;
  };
  return (
    <p className="silencioso" style={{ fontSize: 12, margin: 0 }}>
      <b>A:</b> {grupo(conjunto.a)}
      <br />
      <b>B:</b> {grupo(conjunto.b)}
      <br />
      {conjunto.modo === "interferencia"
        ? `Interferência, tolerância ${medidaTexto(conjunto.tolerancia)}`
        : `Folga mínima de ${medidaTexto(conjunto.folga)}`}
      {conjunto.ignorarMesmoModelo && " · sem pares do mesmo modelo"}
    </p>
  );
}

/** A janela que monta o conjunto: grupo A, grupo B, tipo e tolerância. */
function EditorConjunto({
  inicial,
  disciplinas,
  categorias,
  aoFechar,
  aoGuardar,
}: {
  inicial: ConjuntoConflito;
  disciplinas: string[];
  categorias: Record<string, Record<string, number>>;
  aoFechar: () => void;
  aoGuardar: (c: ConjuntoConflito, detectarJa: boolean) => void;
}) {
  const [c, setC] = useState<ConjuntoConflito>(inicial);
  const [erro, setErro] = useState<string | null>(null);

  function concluir(detectarJa: boolean) {
    if (!c.nome.trim()) return setErro("Dê um nome ao conjunto.");
    if (!c.a.disciplinas.length || !c.b.disciplinas.length) return setErro("Escolha ao menos uma disciplina em cada grupo.");
    aoGuardar({ ...c, nome: c.nome.trim() }, detectarJa);
  }

  return (
    <div className="painel-vista-fundo">
      <div className="painel-vista" role="dialog" aria-label="Conjunto de conflitos">
        <div className="linha">
          <strong>Conjunto de conflitos</strong>
          <div className="espaco" />
          <button className="assistente-fechar" onClick={aoFechar} aria-label="Fechar">
            ×
          </button>
        </div>
        <label className="campo" style={{ display: "block", marginTop: 8 }}>
          <span className="rotulo">Nome</span>
          <input value={c.nome} maxLength={80} onChange={(e) => setC({ ...c, nome: e.target.value })} />
        </label>
        <div className="grupos-conflito">
          <EditorGrupo
            titulo="Grupo A"
            dica="O que costuma ser desviado (ex.: tubulações)."
            grupo={c.a}
            disciplinas={disciplinas}
            categorias={categorias}
            aoMudar={(a) => setC({ ...c, a })}
          />
          <EditorGrupo
            titulo="Grupo B"
            dica="Contra o que A é testado. Deixe as lajes de fora para não marcar os furos de laje."
            grupo={c.b}
            disciplinas={disciplinas}
            categorias={categorias}
            aoMudar={(b) => setC({ ...c, b })}
          />
        </div>
        <div className="linha" style={{ gap: 16, flexWrap: "wrap", marginTop: 10 }}>
          <label className="opcao-aviso" style={{ margin: 0 }}>
            <input
              type="radio"
              checked={c.modo === "interferencia"}
              onChange={() => setC({ ...c, modo: "interferencia" })}
            />
            Interferência — uma peça entra na outra mais que
            <input
              type="number"
              min={0}
              max={50}
              step={0.5}
              className="numero-conflito"
              value={Math.round(c.tolerancia * 1000) / 10}
              onChange={(e) => setC({ ...c, tolerancia: Math.max(0, Number(e.target.value) || 0) / 100 })}
            />
            cm
          </label>
          <label className="opcao-aviso" style={{ margin: 0 }}>
            <input type="radio" checked={c.modo === "folga"} onChange={() => setC({ ...c, modo: "folga" })} />
            Folga — ficam a menos de
            <input
              type="number"
              min={0.5}
              max={100}
              step={0.5}
              className="numero-conflito"
              value={Math.round(c.folga * 1000) / 10}
              onChange={(e) => setC({ ...c, folga: Math.max(0.005, (Number(e.target.value) || 0) / 100) })}
            />
            cm (inclui as interferências)
          </label>
        </div>
        <label className="opcao-aviso" style={{ marginTop: 8 }}>
          <input
            type="checkbox"
            checked={c.ignorarMesmoModelo}
            onChange={(e) => setC({ ...c, ignorarMesmoModelo: e.target.checked })}
          />
          Ignorar pares dentro do mesmo modelo
          <span className="silencioso">— tubo com a própria conexão sempre se toca</span>
        </label>
        {erro && <p className="erro-modelo">{erro}</p>}
        <div className="linha" style={{ gap: 8, marginTop: 12 }}>
          <button className="botao" onClick={() => concluir(true)}>
            Guardar e detectar
          </button>
          <button className="botao secundario pequeno" onClick={() => concluir(false)}>
            Só guardar
          </button>
          <button className="botao secundario pequeno" onClick={aoFechar}>
            Cancelar
          </button>
        </div>
        <p className="silencioso" style={{ fontSize: 12, margin: "8px 0 0" }}>
          O conjunto fica guardado neste navegador e vale para qualquer revisão dos modelos: ele escolhe por
          disciplina e categoria, não por arquivo.
        </p>
      </div>
    </div>
  );
}

function EditorGrupo({
  titulo,
  dica,
  grupo,
  disciplinas,
  categorias,
  aoMudar,
}: {
  titulo: string;
  dica: string;
  grupo: GrupoConflito;
  disciplinas: string[];
  categorias: Record<string, Record<string, number>>;
  aoMudar: (g: GrupoConflito) => void;
}) {
  // As categorias das disciplinas marcadas, com quantos elementos.
  const disponiveis: Record<string, number> = {};
  for (const d of grupo.disciplinas)
    for (const [cat, n] of Object.entries(categorias[d] ?? {})) disponiveis[cat] = (disponiveis[cat] ?? 0) + n;
  const lista = Object.entries(disponiveis).sort((x, y) => nomeCategoria(x[0]).localeCompare(nomeCategoria(y[0])));
  const todas = grupo.categorias.length === 0;
  const excluir = grupo.excluir ?? [];

  return (
    <fieldset className="grupo-conflito">
      <legend>{titulo}</legend>
      <p className="silencioso" style={{ fontSize: 12, margin: "0 0 6px" }}>
        {dica}
      </p>
      <span className="rotulo">Disciplinas</span>
      <div className="linha" style={{ gap: 10, flexWrap: "wrap", margin: "2px 0 8px" }}>
        {disciplinas.map((d) => (
          <label key={d} className="opcao-aviso" style={{ margin: 0 }}>
            <input
              type="checkbox"
              checked={grupo.disciplinas.includes(d)}
              onChange={(e) =>
                aoMudar({
                  ...grupo,
                  disciplinas: e.target.checked
                    ? [...grupo.disciplinas, d]
                    : grupo.disciplinas.filter((x) => x !== d),
                })
              }
            />
            <span className="mono">{d}</span>
          </label>
        ))}
      </div>
      <span className="rotulo">Categorias</span>
      <label className="opcao-aviso" style={{ margin: "2px 0 4px" }}>
        <input
          type="checkbox"
          checked={todas}
          onChange={(e) =>
            aoMudar({
              ...grupo,
              categorias: e.target.checked ? [] : lista.map(([cat]) => cat).filter((cat) => !excluir.includes(cat)),
            })
          }
        />
        Todas, menos as desmarcadas
      </label>
      <ul className="categorias-conflito">
        {lista.map(([cat, n]) => (
          <li key={cat}>
            <label className="opcao-aviso" style={{ margin: 0 }}>
              <input
                type="checkbox"
                checked={todas ? !excluir.includes(cat) : grupo.categorias.includes(cat)}
                onChange={(e) =>
                  aoMudar(
                    todas
                      ? {
                          ...grupo,
                          excluir: e.target.checked ? excluir.filter((x) => x !== cat) : [...excluir, cat],
                        }
                      : {
                          ...grupo,
                          categorias: e.target.checked
                            ? [...grupo.categorias, cat]
                            : grupo.categorias.filter((x) => x !== cat),
                        },
                  )
                }
              />
              {nomeCategoria(cat)}
              <span className="silencioso mono" style={{ fontSize: 11 }}>
                {" "}
                {cat} · {n}
              </span>
            </label>
          </li>
        ))}
        {grupo.categorias
          .filter((cat) => !(cat in disponiveis))
          .map((cat) => (
            <li key={cat} className="silencioso">
              <label className="opcao-aviso" style={{ margin: 0 }}>
                <input
                  type="checkbox"
                  checked
                  onChange={() => aoMudar({ ...grupo, categorias: grupo.categorias.filter((x) => x !== cat) })}
                />
                {nomeCategoria(cat)} <span className="mono" style={{ fontSize: 11 }}>(não está nos modelos abertos)</span>
              </label>
            </li>
          ))}
      </ul>
    </fieldset>
  );
}
