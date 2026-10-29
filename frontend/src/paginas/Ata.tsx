import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ErroApi, formatarData, type Ata as AtaDados } from "../api";
import { Aviso, Carregando, SIMBOLO } from "../componentes";

const RESPOSTA: Record<string, string> = { S: "S", N: "N", NA: "N/A" };

/** A ata de análise crítica, em formato de documento: para ler na tela e
 *  imprimir ou salvar em PDF (TREELE, 29/10/2026). Não se edita. */
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

  const grupos: { titulo: string; itens: AtaDados["itens"] }[] = [];
  for (const i of ata.itens) {
    if (grupos[grupos.length - 1]?.titulo !== i.grupo) grupos.push({ titulo: i.grupo, itens: [] });
    grupos[grupos.length - 1].itens.push(i);
  }
  const conta = (r: string) => ata.itens.filter((i) => i.resposta === r).length;

  return (
    <>
      <div className="cabecalho-area nao-imprimir">
        <div>
          <Link to="/atas" className="link-pequeno">
            ← Atas de análise crítica
          </Link>
        </div>
        <button className="botao" onClick={() => window.print()}>
          Imprimir ou salvar PDF
        </button>
      </div>

      <article className="folha documento-ata">
        <header className="ata-cabecalho">
          <img src={SIMBOLO} alt="" className="ata-simbolo" />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="rotulo">Treèle Construtora · {ata.formulario}</div>
            <h1>Ata de análise crítica de projeto</h1>
            <div className="silencioso">{ata.titulo}</div>
          </div>
          <div className="ata-codigo">
            <span className="mono">{ata.codigo}</span>
            <span className={`resultado-ata ${ata.resultado}`}>
              {ata.resultado === "conforme" ? "Conforme" : "Não conforme"}
            </span>
          </div>
        </header>

        <dl className="ata-campos">
          <div>
            <dt>Empreendimento</dt>
            <dd>
              {ata.obra} · {ata.obra_nome}
            </dd>
          </div>
          <div>
            <dt>Disciplina</dt>
            <dd>
              {ata.disciplina} · {ata.disciplina_nome}
            </dd>
          </div>
          <div>
            <dt>Análise feita por</dt>
            <dd>{ata.criada_por ?? "—"}</dd>
          </div>
          <div>
            <dt>Data</dt>
            <dd>{formatarData(ata.criada_em)}</dd>
          </div>
          <div>
            <dt>Respostas</dt>
            <dd>
              {conta("S")} S · {conta("N")} N · {conta("NA")} N/A
            </dd>
          </div>
        </dl>

        <section>
          <h2>Revisões analisadas</h2>
          <table className="tabela tabela-ata">
            <thead>
              <tr>
                <th>Documento</th>
                <th>Título</th>
                <th>Revisão</th>
              </tr>
            </thead>
            <tbody>
              {ata.revisoes.map((r) => (
                <tr key={r.id}>
                  <td className="mono">{r.documento}</td>
                  <td>{r.titulo ?? "—"}</td>
                  <td className="mono">R{r.revisao}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section>
          <h2>Checklist</h2>
          <table className="tabela tabela-ata">
            <thead>
              <tr>
                <th style={{ width: 56 }}>Item</th>
                <th>Descrição</th>
                <th style={{ width: 52 }}>Resp.</th>
                <th>Comentário</th>
              </tr>
            </thead>
            {grupos.map((g) => (
              <tbody key={g.titulo}>
                <tr className="grupo-tabela-ata">
                  <td colSpan={4}>{g.titulo}</td>
                </tr>
                {g.itens.map((i) => (
                  <tr key={i.id} className={i.resposta === "N" ? "linha-nao" : undefined}>
                    <td className="mono">{i.item}</td>
                    <td style={{ whiteSpace: "pre-line" }}>
                      {i.texto}
                      {i.grupo.includes("Desempenho") && <span className="item-ata-disc">{i.disc}</span>}
                    </td>
                    <td className={`resposta-ata ${i.resposta}`}>{RESPOSTA[i.resposta] ?? i.resposta}</td>
                    <td>{i.comentario ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            ))}
          </table>
        </section>

        {ata.observacoes && (
          <section>
            <h2>Observações gerais</h2>
            <p style={{ whiteSpace: "pre-line" }}>{ata.observacoes}</p>
          </section>
        )}

        <footer className="ata-rodape silencioso">
          Legenda: S — sim · N — não · N/A — não aplicável. Registro gerado pelo Portal de Projetos na
          análise crítica que antecede a liberação para obra; arquivado por obra, pode ser descartado após 5
          anos (PRO-FL-005).
        </footer>
      </article>
    </>
  );
}
