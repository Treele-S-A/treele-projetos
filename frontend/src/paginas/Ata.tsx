import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ErroApi, type Ata as AtaDados } from "../api";
import { Aviso, Carregando } from "../componentes";

/** Como cada disciplina entra no título: "Análise crítica de projeto
 *  arquitetônico" (o modelo ENG-FL-001 é o da arquitetura). */
const ADJETIVO: Record<string, string> = {
  ARQ: "arquitetônico",
  EST: "estrutural",
  FUN: "de fundação",
  CON: "de contenção",
  HID: "hidrossanitário",
  DRE: "de drenagem",
  ELE: "elétrico",
  INC: "de incêndio",
  GAS: "de gás",
  CLI: "de climatização",
  TEL: "de telecomunicações",
  PAI: "paisagístico",
  IMP: "de impermeabilização",
  ESQ: "de esquadrias",
  TOP: "topográfico",
  CTL: "de conforto térmico e lumínico",
  LUM: "luminotécnico",
  SPD: "de SPDA",
  INT: "de interiores",
};

function dataCurta(iso: string | null) {
  return iso ? new Date(iso).toLocaleDateString("pt-BR") : "-";
}

function Marca({ marcada }: { marcada: boolean }) {
  return <span className="marca-ata">{marcada ? "☒" : "☐"}</span>;
}

/** A ata de análise crítica no modelo da Treèle (ENG-FL-001, TREELE,
 *  29/10/2026): para ler na tela e imprimir ou salvar em PDF. O que muda
 *  depois dela (a reprovação, a correção recebida) entra na "Solicitação de
 *  alterações". */
export default function Ata() {
  const { ataId } = useParams();
  const [ata, setAta] = useState<AtaDados | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    api
      .get<AtaDados>(`/atas/${ataId}`)
      .then((a) => {
        if (!vivo) return;
        setAta(a);
        document.title = `${a.codigo} · Projetos`;
      })
      .catch((ex) => vivo && setErro(ex instanceof ErroApi ? ex.message : "Não foi possível abrir a ata."));
    return () => {
      vivo = false;
    };
  }, [ataId]);

  if (erro) return <Aviso tom="erro">{erro}</Aviso>;
  if (!ata) return <Carregando texto="Abrindo a ata" />;

  const adjetivo = ADJETIVO[ata.disciplina] ?? `de ${ata.disciplina_nome.toLowerCase()}`;
  const grupos: { titulo: string; itens: AtaDados["itens"] }[] = [];
  for (const i of ata.itens) {
    if (grupos[grupos.length - 1]?.titulo !== i.grupo) grupos.push({ titulo: i.grupo, itens: [] });
    grupos[grupos.length - 1].itens.push(i);
  }
  const varias = ata.situacao.length > 1;
  const solicitacoes = ata.situacao.filter((s) => s.motivo);
  const vazias = Math.max(0, 4 - solicitacoes.length);

  return (
    <>
      <div className="cabecalho-area nao-imprimir">
        <div>
          <Link to="/atas" className="link-pequeno">
            ← Atas de análise crítica
          </Link>
          <div className="silencioso mono" style={{ fontSize: 12, marginTop: 4 }}>
            {ata.codigo} · {ata.resultado === "conforme" ? "conforme" : `não conforme (${ata.nao_conformes})`}
          </div>
        </div>
        <button className="botao" onClick={() => window.print()}>
          Imprimir ou salvar PDF
        </button>
      </div>

      <article className="eng-fl">
        {/* thead/tfoot: o navegador repete o cabeçalho e o rodapé em cada página impressa. */}
        <table className="eng-fl-pagina">
          <thead>
            <tr>
              <td>
                <header className="eng-fl-cabecalho">
                  <img src="/logo-treele-construtora.png" alt="treèle construtora" />
                  <h1>Análise crítica de projeto {adjetivo}</h1>
                  <div className="eng-fl-controle">
                    <strong>ENG-FL-001</strong>
                    <strong>DATA:</strong>
                    <span>{dataCurta(ata.criada_em)}</span>
                  </div>
                </header>
              </td>
            </tr>
          </thead>
          <tfoot>
            <tr>
              <td>
                <div className="eng-fl-rodape-espaco" />
              </td>
            </tr>
          </tfoot>
          <tbody>
            <tr>
              <td>
                <table className="eng-fl-corpo">
                  <tbody>
                    <tr>
                      <th className="eng-fl-faixa">Projeto {adjetivo}</th>
                    </tr>
                    <tr>
                      <td className="eng-fl-projeto">
                        <p>
                          <strong>Projeto {adjetivo}</strong> do empreendimento {ata.obra_nome}
                          {ata.obra_endereco ? `, localizado na ${ata.obra_endereco}` : " (endereço não cadastrado)"}.
                        </p>
                        <p className="eng-fl-documentos">
                          {ata.revisoes.length === 1 ? "Documento analisado: " : "Documentos analisados: "}
                          {ata.revisoes.map((r, k) => (
                            <span key={r.id}>
                              {k > 0 && "; "}
                              {r.documento} R{r.revisao}
                              {r.titulo ? ` – ${r.titulo}` : ""}
                            </span>
                          ))}
                          .
                        </p>
                      </td>
                    </tr>

                    <tr>
                      <th className="eng-fl-faixa espacada">Itens analisados</th>
                    </tr>
                    <tr>
                      <td className="eng-fl-itens">
                        <table>
                          <thead>
                            <tr>
                              <th>SIM</th>
                              <th>NÃO</th>
                              <th>N/A</th>
                              <th />
                            </tr>
                          </thead>
                          {grupos.map((g) => (
                            <tbody key={g.titulo}>
                              <tr className="eng-fl-grupo">
                                <td colSpan={4}>{g.titulo}</td>
                              </tr>
                              {g.itens.map((i) => (
                                <tr key={i.id}>
                                  <td>
                                    <Marca marcada={i.resposta === "S"} />
                                  </td>
                                  <td>
                                    <Marca marcada={i.resposta === "N"} />
                                  </td>
                                  <td>
                                    <Marca marcada={i.resposta === "NA"} />
                                  </td>
                                  <td className="eng-fl-texto">
                                    {i.item} {i.texto}
                                    {i.comentario && <em className="eng-fl-comentario">Comentário: {i.comentario}</em>}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          ))}
                        </table>
                        {ata.observacoes && (
                          <p className="eng-fl-observacoes">
                            <strong>Observações:</strong> {ata.observacoes}
                          </p>
                        )}
                      </td>
                    </tr>

                    <tr>
                      <th className="eng-fl-faixa espacada">Solicitação de alterações</th>
                    </tr>
                    <tr>
                      <td className="eng-fl-solicitacoes">
                        <table>
                          <thead>
                            <tr>
                              <th>REVISÃO</th>
                              <th>DATA DA SOLICITAÇÃO</th>
                              <th>SOLICITANTE</th>
                              <th>ALTERAÇÃO SOLICITADA</th>
                              <th>DATA DO RECEBIMENTO</th>
                            </tr>
                          </thead>
                          <tbody>
                            {solicitacoes.map((s) => (
                              <tr key={s.id}>
                                <td>
                                  {varias && <span className="eng-fl-doc">{s.documento}</span>}R{s.revisao}
                                </td>
                                <td>{dataCurta(s.reprovada_em)}</td>
                                <td>{s.reprovada_por ?? "-"}</td>
                                <td className="eng-fl-alteracao">{s.motivo}</td>
                                <td>{dataCurta(s.recebida_em)}</td>
                              </tr>
                            ))}
                            {Array.from({ length: vazias }, (_, k) => (
                              <tr key={`vazia-${k}`} className="eng-fl-vazia">
                                <td />
                                <td />
                                <td />
                                <td />
                                <td />
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </td>
                    </tr>

                    <tr>
                      <th className="eng-fl-faixa esquerda">Analisado por:</th>
                    </tr>
                    <tr>
                      <td className="eng-fl-assinatura">{ata.analisado_por}</td>
                    </tr>
                  </tbody>
                </table>
              </td>
            </tr>
          </tbody>
        </table>
        <div className="eng-fl-barra" aria-hidden="true" />
      </article>
    </>
  );
}
