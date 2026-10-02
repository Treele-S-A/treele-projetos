import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  api,
  ErroApi,
  formatarData,
  type Arquivo,
  type DocumentoDetalhe,
} from "../api";
import { Aviso, Carregando, Estado, Vazio } from "../componentes";
import { HistoricoRevisoes, baixarArquivo } from "../Revisoes";
import { MarcaSolicitada } from "../Solicitacoes";
import { useSessao } from "../sessao";

interface PastaDados {
  obra_codigo: string;
  obra_nome: string;
  disciplina: { codigo: string; nome: string };
  fase: { codigo: string; nome: string };
  total: number;
  documentos: DocumentoDetalhe[];
}

export default function Pasta() {
  const { obraId, disciplina, fase } = useParams();
  const { obras } = useSessao();
  const obra = obras.find((o) => o.id === Number(obraId));

  const [dados, setDados] = useState<PastaDados | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  // Guarda os abertos, não os recolhidos: a pasta chega toda recolhida, como
  // um índice de pranchas, e a pessoa abre só o documento que procura.
  const [abertos, setAbertos] = useState<Set<number>>(new Set());

  const podePublicar = obra?.permissoes.includes("publicar") ?? false;
  const podeCancelar = obra?.permissoes.includes("cancelar") ?? false;

  const carregar = useCallback(async () => {
    setCarregando(true);
    try {
      setDados(
        await api.get<PastaDados>(
          `/obras/${obraId}/pastas/${disciplina}/${fase}`,
        ),
      );
      setErro(null);
    } catch (ex) {
      setErro(
        ex instanceof ErroApi ? ex.message : "Não foi possível abrir a pasta.",
      );
    } finally {
      setCarregando(false);
    }
  }, [obraId, disciplina, fase]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  function baixar(arquivo: Arquivo) {
    setErro(null);
    baixarArquivo(arquivo, setErro, setAviso);
  }

  function alternar(id: number) {
    setAbertos((atual) => {
      const novo = new Set(atual);
      if (novo.has(id)) novo.delete(id);
      else novo.add(id);
      return novo;
    });
  }

  if (carregando) return <Carregando texto="Abrindo a pasta" />;
  if (erro && !dados) return <Aviso tom="erro">{erro}</Aviso>;
  if (!dados) return null;

  const totalRevisoes = dados.documentos.reduce(
    (soma, d) => soma + d.revisoes.length,
    0,
  );

  return (
    <>
      <div className="cabecalho-area">
        <div>
          <span className="rotulo">
            <Link
              to={`/obras/${obraId}/acervo`}
              style={{ textDecoration: "underline" }}
            >
              {dados.obra_codigo} · {dados.obra_nome}
            </Link>
            {"  /  "}
            {dados.disciplina.codigo} {dados.disciplina.nome}
          </span>
          <h1>{dados.fase.nome}</h1>
          <div className="silencioso" style={{ marginTop: 2 }}>
            {dados.total} documento{dados.total === 1 ? "" : "s"} ·{" "}
            {totalRevisoes} revis{totalRevisoes === 1 ? "ão" : "ões"}
          </div>
        </div>
        <div className="linha">
          {dados.documentos.length > 1 && (
            <>
              <button
                className="botao secundario pequeno"
                onClick={() => setAbertos(new Set(dados.documentos.map((d) => d.id)))}
              >
                Expandir tudo
              </button>
              <button
                className="botao secundario pequeno"
                onClick={() => setAbertos(new Set())}
              >
                Recolher
              </button>
            </>
          )}
          <Link className="botao secundario" to={`/obras/${obraId}/acervo`}>
            Voltar ao acervo
          </Link>
        </div>
      </div>

      {erro && <Aviso tom="erro">{erro}</Aviso>}
      {aviso && <Aviso tom="atencao">{aviso}</Aviso>}

      {dados.documentos.length === 0 ? (
        <div className="folha">
          <Vazio titulo="Pasta vazia">
            Nenhum documento de {dados.disciplina.nome} nesta fase ainda.
          </Vazio>
        </div>
      ) : (
        dados.documentos.map((doc) => {
          const recolhido = !abertos.has(doc.id);
          const atual = doc.revisao_atual;
          return (
            <div className="folha" key={doc.id}>
              <div className="folha-titulo">
                <button
                  className="arvore-alvo"
                  style={{ width: "auto", flex: 1, minWidth: 0 }}
                  onClick={() => alternar(doc.id)}
                  aria-expanded={!recolhido}
                >
                  <span className={`arvore-seta ${recolhido ? "" : "aberta"}`}>
                    &#9656;
                  </span>
                  {/* Título em destaque, código como rótulo: quem navega
                      procura a prancha pelo nome, não pelo número. */}
                  <span className="doc-na-pasta">
                    <span className="codigo">{doc.codigo}</span>
                    <span className={doc.titulo ? "titulo" : "titulo sem"}>
                      {doc.titulo ?? "Sem título"}
                    </span>
                  </span>
                </button>

                <div className="linha">
                  {atual && (
                    <>
                      <span className="mono" style={{ fontSize: 13 }}>
                        R{atual.numero}
                      </span>
                      <Estado status={atual.status} />
                      <MarcaSolicitada quantidade={doc.solicitacoes_abertas} />
                    </>
                  )}
                  <span className="silencioso mono" style={{ fontSize: 11 }}>
                    {doc.total_revisoes} rev · {formatarData(atual?.publicada_em ?? null, false)}
                  </span>
                  <Link className="botao secundario pequeno" to={`/documentos/${doc.id}`}>
                    Abrir
                  </Link>
                </div>
              </div>

              {!recolhido && (
                <HistoricoRevisoes
                  revisoes={doc.revisoes}
                  podePublicar={podePublicar}
                  podeCancelar={podeCancelar}
                  aoMudar={carregar}
                  aoBaixar={baixar}
                />
              )}
            </div>
          );
        })
      )}
    </>
  );
}
