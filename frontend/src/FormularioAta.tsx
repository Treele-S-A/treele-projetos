/** Ata de análise crítica (TREELE, 29/10/2026 — SIAC): o checklist PRO-FL-005
 *  da disciplina, num pop-up, antes de liberar para obra. Uma ata cobre as
 *  revisões da mesma disciplina liberadas juntas; cada item tem S, N ou N/A, e
 *  "N" pede comentário. Com algum "N" a ata fica registrada, mas as revisões
 *  não podem ser liberadas. */

import { useEffect, useMemo, useRef, useState } from "react";
import { api, ErroApi, type Ata, type GrupoAta } from "./api";
import { Aviso } from "./componentes";

type Resposta = "S" | "N" | "NA";
const OPCOES: [Resposta, string, string][] = [
  ["S", "S", "Sim, conforme"],
  ["N", "N", "Não conforme"],
  ["NA", "N/A", "Não se aplica"],
];

export default function FormularioAta({
  grupo,
  posicao,
  aoSalvar,
  aoFechar,
}: {
  grupo: GrupoAta;
  /** "1 de 3" quando a liberação em lote tem várias disciplinas. */
  posicao?: string;
  aoSalvar: (ata: Ata) => void;
  aoFechar: () => void;
}) {
  const itens = useMemo(() => grupo.formulario.grupos.flatMap((g) => g.itens), [grupo]);
  const [respostas, setRespostas] = useState<Record<string, Resposta>>({});
  const [comentarios, setComentarios] = useState<Record<string, string>>({});
  const [observacoes, setObservacoes] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [tentou, setTentou] = useState(false);
  const caixa = useRef<HTMLDivElement>(null);

  const respondidos = itens.filter((i) => respostas[i.id]).length;
  const naoConformes = itens.filter((i) => respostas[i.id] === "N");
  const semComentario = naoConformes.filter((i) => !comentarios[i.id]?.trim());
  const completo = respondidos === itens.length && semComentario.length === 0;

  useEffect(() => {
    caixa.current?.focus();
    const tecla = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !salvando) fechar();
    };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [salvando, respondidos]);

  function fechar() {
    if (respondidos > 0 && !window.confirm("Fechar sem salvar? As respostas deste checklist se perdem.")) return;
    aoFechar();
  }

  function marcarGrupo(ids: string[], r: Resposta) {
    setRespostas((atual) => {
      const novo = { ...atual };
      for (const id of ids) if (!novo[id]) novo[id] = r;
      return novo;
    });
  }

  // Todos como S de uma vez (TREELE, 29/10/2026): depois, só os N e N/A
  // mudam um a um. Desmarcar limpa as respostas S.
  const todosS = itens.length > 0 && itens.every((i) => respostas[i.id] === "S");
  function marcarTodosS(marcar: boolean) {
    if (marcar) {
      const outras = itens.filter((i) => respostas[i.id] && respostas[i.id] !== "S").length;
      if (outras && !window.confirm(`${outras} ite${outras === 1 ? "m já está" : "ns já estão"} como N ou N/A. Trocar tudo para S?`)) return;
      setRespostas(Object.fromEntries(itens.map((i) => [i.id, "S" as Resposta])));
    } else {
      setRespostas((atual) => Object.fromEntries(Object.entries(atual).filter(([, r]) => r !== "S")));
    }
  }

  async function salvar() {
    setTentou(true);
    if (!completo) {
      const primeiro = itens.find((i) => !respostas[i.id] || (respostas[i.id] === "N" && !comentarios[i.id]?.trim()));
      if (primeiro) document.getElementById(`item-ata-${primeiro.id}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
      return;
    }
    setSalvando(true);
    setErro(null);
    try {
      const ata = await api.post<Ata>("/atas", {
        revisao_ids: grupo.revisoes.map((r) => r.id),
        respostas: itens.map((i) => ({ id: i.id, resposta: respostas[i.id], comentario: comentarios[i.id]?.trim() || null })),
        observacoes: observacoes.trim() || null,
      });
      aoSalvar(ata);
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex : new ErroApi(0, "Não foi possível salvar a ata."));
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div className="fundo-modal" onMouseDown={(e) => e.target === e.currentTarget && fechar()}>
      <div
        className="modal-ata"
        role="dialog"
        aria-modal="true"
        aria-labelledby="titulo-ata"
        tabIndex={-1}
        ref={caixa}
      >
        <header className="modal-ata-topo">
          <div style={{ minWidth: 0 }}>
            <span className="rotulo">
              Análise crítica{posicao ? ` · ${posicao}` : ""} · {grupo.formulario.formulario}
            </span>
            <h2 id="titulo-ata" className="titulo-secao" style={{ margin: "2px 0 4px" }}>
              {grupo.disciplina_nome} <em>· {grupo.obra}</em>
            </h2>
            <div className="silencioso" style={{ fontSize: 12.5 }}>
              {grupo.revisoes.length === 1
                ? `${grupo.revisoes[0].documento} R${grupo.revisoes[0].revisao}`
                : `${grupo.revisoes.length} revisões: ${grupo.revisoes
                    .slice(0, 6)
                    .map((r) => `${r.documento} R${r.revisao}`)
                    .join(", ")}${grupo.revisoes.length > 6 ? "…" : ""}`}
            </div>
            <label className="opcao-aviso marcar-todos-ata">
              <input
                type="checkbox"
                checked={todosS}
                onChange={(e) => marcarTodosS(e.target.checked)}
                disabled={salvando}
              />
              Marcar todos como S
              <span className="silencioso">— depois, ajuste os que forem N ou N/A</span>
            </label>
          </div>
          <button className="botao secundario pequeno" onClick={fechar} disabled={salvando}>
            Fechar
          </button>
        </header>

        <div className="modal-ata-corpo">
          {grupo.formulario.blocos.length === 0 && (
            <p className="silencioso" style={{ fontSize: 12.5, marginTop: 0 }}>
              A planilha PRO-FL-005 não tem bloco próprio para {grupo.disciplina_nome.toLowerCase()}: valem os
              itens de representação gráfica.
            </p>
          )}
          {grupo.formulario.grupos.map((g) => {
            const ids = g.itens.map((i) => i.id);
            return (
              <section key={g.titulo} className="grupo-ata">
                <div className="grupo-ata-topo">
                  <h3>{g.titulo}</h3>
                  <span className="silencioso">
                    {ids.filter((id) => respostas[id]).length} de {ids.length}
                  </span>
                  <div className="espaco" />
                  <button className="link-pequeno" onClick={() => marcarGrupo(ids, "NA")} disabled={salvando}>
                    Restantes: N/A
                  </button>
                </div>
                <ol className="itens-ata">
                  {g.itens.map((i) => {
                    const r = respostas[i.id];
                    const falta = tentou && (!r || (r === "N" && !comentarios[i.id]?.trim()));
                    return (
                      <li key={i.id} id={`item-ata-${i.id}`} className={`item-ata ${falta ? "falta" : ""} ${r === "N" ? "nao" : ""}`}>
                        <span className="item-ata-numero mono">{i.item}</span>
                        <div className="item-ata-texto">
                          {i.texto}
                          {/* No desempenho, os itens vêm de várias disciplinas. */}
                          {g.titulo.includes("Desempenho") && <span className="item-ata-disc">{i.disc}</span>}
                        </div>
                        <div className="opcoes-ata" role="radiogroup" aria-label={`Item ${i.item}`}>
                          {OPCOES.map(([valor, rotulo, dica]) => (
                            <button
                              key={valor}
                              role="radio"
                              aria-checked={r === valor}
                              title={dica}
                              className={`opcao-ata ${valor} ${r === valor ? "marcada" : ""}`}
                              onClick={() => setRespostas((a) => ({ ...a, [i.id]: valor }))}
                              disabled={salvando}
                            >
                              {rotulo}
                            </button>
                          ))}
                        </div>
                        {(r === "N" || comentarios[i.id]) && (
                          <input
                            className="comentario-ata"
                            value={comentarios[i.id] ?? ""}
                            onChange={(e) => setComentarios((c) => ({ ...c, [i.id]: e.target.value }))}
                            placeholder={r === "N" ? "Obrigatório: o que não está conforme" : "Comentário"}
                            maxLength={2000}
                            disabled={salvando}
                          />
                        )}
                      </li>
                    );
                  })}
                </ol>
              </section>
            );
          })}

          <label className="campo" style={{ display: "block" }}>
            <span className="rotulo">Observações gerais (opcional)</span>
            <textarea
              value={observacoes}
              onChange={(e) => setObservacoes(e.target.value)}
              rows={3}
              maxLength={8000}
              disabled={salvando}
            />
          </label>
        </div>

        <footer className="modal-ata-rodape">
          {erro && <Aviso tom="erro" titulo={erro.message} itens={erro.erros} />}
          {tentou && !completo && (
            <Aviso
              tom="atencao"
              titulo={
                respondidos < itens.length
                  ? `Faltam ${itens.length - respondidos} ite${itens.length - respondidos === 1 ? "m" : "ns"} sem resposta.`
                  : `Ite${semComentario.length === 1 ? "m" : "ns"} marcado${semComentario.length === 1 ? "" : "s"} N sem comentário: ${semComentario.map((i) => i.item).join(", ")}.`
              }
            />
          )}
          {naoConformes.length > 0 && (
            <p className="silencioso" style={{ fontSize: 12.5, margin: 0 }}>
              <strong style={{ color: "var(--obsoleto)" }}>
                {naoConformes.length} não conforme{naoConformes.length === 1 ? "" : "s"}
              </strong>{" "}
              — a ata fica registrada, mas {grupo.revisoes.length === 1 ? "a revisão não poderá" : "as revisões não poderão"} ser
              liberada{grupo.revisoes.length === 1 ? "" : "s"}.
            </p>
          )}
          <div className="linha" style={{ gap: 10 }}>
            <span className="silencioso" style={{ fontSize: 12.5 }}>
              {respondidos} de {itens.length} respondidos
            </span>
            <div className="espaco" />
            <button className="botao" onClick={salvar} disabled={salvando}>
              {salvando ? "Salvando…" : "Salvar e gerar ata de análise crítica"}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
