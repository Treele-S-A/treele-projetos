import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  ErroApi,
  formatarData,
  formatarTamanho,
  type DocumentoDetalhe,
  type TipoArquivo,
} from "./api";
import { Aviso, Carregando, Estado, Vazio } from "./componentes";
import { MarcaSolicitada } from "./Solicitacoes";

interface NoBase {
  chave: string;
  codigo: string;
  nome: string;
  tamanho: number;
  total: number;
  atualizado_em: string | null;
}

interface NoTipo extends NoBase {
  tipo: TipoArquivo;
}

interface NoFase extends NoBase {
  tipos: NoTipo[];
}

interface NoDisciplina extends NoBase {
  fases: NoFase[];
}

interface ArvoreDados {
  obra_codigo: string;
  obra_nome: string;
  tamanho: number;
  total: number;
  atualizado_em: string | null;
  disciplinas: NoDisciplina[];
}

/** Conteúdo de uma pasta (disciplina + fase), carregado ao abrir. */
type Conteudo =
  | { estado: "carregando" }
  | { estado: "erro"; mensagem: string }
  | { estado: "pronto"; documentos: DocumentoDetalhe[] };

/**
 * O acervo em pastas: disciplina → fase → documentos. A fase abre ali mesmo,
 * e o documento leva direto à tela dele (06/10/2026 — antes, a fase abria uma
 * tela própria de pasta, um passo a mais até a prancha).
 *
 * `abrir` ("ARQ/PE") chega aberta: é o destino dos links antigos de pasta.
 */
export default function Arvore({ obraId, abrir }: { obraId: number; abrir?: string }) {
  const [dados, setDados] = useState<ArvoreDados | null>(null);
  const [abertas, setAbertas] = useState<Set<string>>(new Set());
  const [conteudos, setConteudos] = useState<Record<string, Conteudo>>({});
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  const carregarPasta = useCallback(
    (d: NoDisciplina, f: NoFase) => {
      setConteudos((c) => ({ ...c, [f.chave]: { estado: "carregando" } }));
      api
        .get<{ documentos: DocumentoDetalhe[] }>(
          `/obras/${obraId}/pastas/${d.codigo}/${f.codigo}`,
        )
        .then((p) =>
          setConteudos((c) => ({ ...c, [f.chave]: { estado: "pronto", documentos: p.documentos } })),
        )
        .catch((ex) =>
          setConteudos((c) => ({
            ...c,
            [f.chave]: {
              estado: "erro",
              mensagem: ex instanceof ErroApi ? ex.message : "Não foi possível abrir a pasta.",
            },
          })),
        );
    },
    [obraId],
  );

  useEffect(() => {
    setCarregando(true);
    setConteudos({});
    api
      .get<ArvoreDados>(`/obras/${obraId}/arvore`)
      .then((a) => {
        setDados(a);
        const iniciais = new Set<string>();
        // Uma disciplina só: abre, porque não há o que escolher.
        if (a.disciplinas.length === 1) iniciais.add(a.disciplinas[0].chave);
        if (abrir) {
          const [disc, fase] = abrir.split("/");
          const d = a.disciplinas.find((x) => x.codigo === disc);
          const f = d?.fases.find((x) => x.codigo === fase);
          if (d && f) {
            iniciais.add(d.chave);
            iniciais.add(f.chave);
            carregarPasta(d, f);
          }
        }
        setAbertas(iniciais);
      })
      .catch((ex) =>
        setErro(ex instanceof ErroApi ? ex.message : "Não foi possível montar a árvore."),
      )
      .finally(() => setCarregando(false));
  }, [obraId, abrir, carregarPasta]);

  function alternar(chave: string) {
    setAbertas((atual) => {
      const novo = new Set(atual);
      if (novo.has(chave)) novo.delete(chave);
      else novo.add(chave);
      return novo;
    });
  }

  function alternarPasta(d: NoDisciplina, f: NoFase) {
    // Busca na primeira abertura, e de novo se da vez anterior deu erro.
    if (!abertas.has(f.chave) && conteudos[f.chave]?.estado !== "pronto") carregarPasta(d, f);
    alternar(f.chave);
  }

  function expandirTudo() {
    if (!dados) return;
    const todas = new Set<string>();
    for (const d of dados.disciplinas) {
      todas.add(d.chave);
      for (const f of d.fases) {
        todas.add(f.chave);
        if (conteudos[f.chave]?.estado !== "pronto") carregarPasta(d, f);
      }
    }
    setAbertas(todas);
  }

  if (carregando) return <Carregando texto="Montando a árvore" />;
  if (erro) return <Aviso tom="erro">{erro}</Aviso>;
  if (!dados || dados.disciplinas.length === 0) {
    return (
      <Vazio titulo="Nada no acervo ainda">
        Envie o primeiro arquivo para a árvore aparecer.
      </Vazio>
    );
  }

  return (
    <>
      <div className="folha-titulo">
        <div className="linha" style={{ gap: 14 }}>
          <strong>
            {dados.total} arquivo{dados.total === 1 ? "" : "s"}
          </strong>
          <span className="silencioso mono" style={{ fontSize: 12 }}>
            {formatarTamanho(dados.tamanho)}
          </span>
        </div>
        <div className="linha">
          <button className="botao secundario pequeno" onClick={expandirTudo}>
            Expandir tudo
          </button>
          <button className="botao secundario pequeno" onClick={() => setAbertas(new Set())}>
            Recolher
          </button>
        </div>
      </div>

      {dados.disciplinas.map((d) => {
        const aberta = abertas.has(d.chave);
        return (
          <div key={d.chave}>
            <div className="arvore-linha nivel-disciplina">
              <button
                className="arvore-alvo"
                onClick={() => alternar(d.chave)}
                aria-expanded={aberta}
              >
                <span className={`arvore-seta ${aberta ? "aberta" : ""}`}>&#9656;</span>
                <span className="marca-no marca-disciplina">D</span>
                <span className="arvore-nome">
                  <span className="codigo-no">{d.codigo}</span>
                  {d.nome}
                </span>
              </button>
              <span className="arvore-meta">{formatarTamanho(d.tamanho)}</span>
              <span className="arvore-meta data">{formatarData(d.atualizado_em, false)}</span>
            </div>

            {aberta &&
              d.fases.map((f) => {
                const faseAberta = abertas.has(f.chave);
                return (
                  <div key={f.chave}>
                    <div className="arvore-linha nivel-fase">
                      <button
                        className="arvore-alvo"
                        onClick={() => alternarPasta(d, f)}
                        aria-expanded={faseAberta}
                      >
                        <span className={`arvore-seta ${faseAberta ? "aberta" : ""}`}>
                          &#9656;
                        </span>
                        <span className="marca-no marca-fase">F</span>
                        <span className="arvore-nome">
                          <span className="codigo-no">{f.codigo}</span>
                          {f.nome}
                        </span>
                        <span className="resumo-formatos">
                          {f.tipos.map((tp) => (
                            <span className="tipo" key={tp.chave}>
                              {tp.codigo} {tp.total}
                            </span>
                          ))}
                        </span>
                      </button>
                      <span className="arvore-meta">{formatarTamanho(f.tamanho)}</span>
                      <span className="arvore-meta data">
                        {formatarData(f.atualizado_em, false)}
                      </span>
                    </div>

                    {faseAberta && <ConteudoDaPasta conteudo={conteudos[f.chave]} />}
                  </div>
                );
              })}
          </div>
        );
      })}
    </>
  );
}

function ConteudoDaPasta({ conteudo }: { conteudo: Conteudo | undefined }) {
  if (!conteudo || conteudo.estado === "carregando") {
    return <div className="arvore-vazio nivel-documento">Abrindo a pasta…</div>;
  }
  if (conteudo.estado === "erro") {
    return <div className="arvore-vazio nivel-documento">{conteudo.mensagem}</div>;
  }
  if (conteudo.documentos.length === 0) {
    return <div className="arvore-vazio nivel-documento">Nenhum documento nesta pasta.</div>;
  }
  return (
    <>
      {conteudo.documentos.map((doc) => {
        const atual = doc.revisao_atual;
        return (
          <Link
            key={doc.id}
            to={`/documentos/${doc.id}`}
            className="arvore-linha nivel-documento"
            title="Abrir o documento"
          >
            {/* Título em destaque, código como rótulo: quem navega procura a
                prancha pelo nome, não pelo número. */}
            <span className="doc-na-pasta">
              <span className="codigo mono">{doc.codigo}</span>
              <span className={doc.titulo ? "titulo" : "titulo sem"}>
                {doc.titulo ?? "Sem título"}
              </span>
            </span>
            <span className="linha arvore-estado">
              {atual && (
                <>
                  <span className="mono" style={{ fontSize: 13 }}>
                    R{atual.numero}
                  </span>
                  <Estado status={atual.status} />
                </>
              )}
              <MarcaSolicitada
                quantidade={doc.solicitacoes_abertas}
                autorizadas={doc.solicitacoes_autorizadas}
              />
            </span>
            <span className="arvore-meta data">
              {doc.total_revisoes} rev · {formatarData(atual?.publicada_em ?? null, false)}
            </span>
          </Link>
        );
      })}
    </>
  );
}
