import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ErroApi, lerToken, type Ata as AtaDados } from "../api";
import { Aviso, Carregando } from "../componentes";

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
  const [gerando, setGerando] = useState(false);

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

  /** O PDF da ata (ENG-FL-001), gerado no servidor: o mesmo arquivo para
   *  todos. "Ver" abre a aba no clique, ainda vazia, para o navegador não
   *  bloquear como pop-up (ver visualizarArquivo). */
  async function pdf(modo: "ver" | "baixar") {
    if (!ata) return;
    const aba = modo === "ver" ? window.open("", "_blank") : null;
    if (aba) aba.document.title = `${ata.codigo}.pdf`;
    setGerando(true);
    setErro(null);
    try {
      const r = await fetch(`${api.base}/atas/${ata.id}/pdf`, {
        headers: { Authorization: `Bearer ${lerToken()}` },
      });
      if (!r.ok) throw new Error(String(r.status));
      const url = URL.createObjectURL(await r.blob());
      if (aba) {
        aba.location.href = url;
      } else {
        const link = document.createElement("a");
        link.href = url;
        link.download = `${ata.codigo}.pdf`;
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 60_000);
      }
    } catch {
      aba?.close();
      setErro("Não foi possível gerar o PDF da ata.");
    } finally {
      setGerando(false);
    }
  }

  if (erro && !ata) return <Aviso tom="erro">{erro}</Aviso>;
  if (!ata) return <Carregando texto="Abrindo a ata" />;

  const adjetivo = ata.adjetivo;
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
        <div className="linha" style={{ gap: 8 }}>
          <button className="botao" onClick={() => pdf("ver")} disabled={gerando}>
            {gerando ? "Gerando o PDF…" : "Ver PDF"}
          </button>
          <button className="botao secundario" onClick={() => pdf("baixar")} disabled={gerando}>
            Baixar PDF
          </button>
          <button className="botao secundario pequeno" onClick={() => window.print()}>
            Imprimir
          </button>
        </div>
      </div>
      {erro && (
        <div className="nao-imprimir">
          <Aviso tom="erro">{erro}</Aviso>
        </div>
      )}

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
