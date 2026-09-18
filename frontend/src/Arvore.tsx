import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  ErroApi,
  formatarData,
  formatarTamanho,
  type TipoArquivo,
} from "./api";
import { Aviso, Carregando, Vazio } from "./componentes";

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

export default function Arvore({ obraId }: { obraId: number }) {
  const [dados, setDados] = useState<ArvoreDados | null>(null);
  const [abertas, setAbertas] = useState<Set<string>>(new Set());
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    setCarregando(true);
    api
      .get<ArvoreDados>(`/obras/${obraId}/arvore`)
      .then((a) => {
        setDados(a);
        // Uma disciplina só: abre, porque não há o que escolher.
        if (a.disciplinas.length === 1) setAbertas(new Set([a.disciplinas[0].chave]));
      })
      .catch((ex) =>
        setErro(
          ex instanceof ErroApi ? ex.message : "Não foi possível montar a árvore.",
        ),
      )
      .finally(() => setCarregando(false));
  }, [obraId]);

  function alternar(chave: string) {
    setAbertas((atual) => {
      const novo = new Set(atual);
      if (novo.has(chave)) novo.delete(chave);
      else novo.add(chave);
      return novo;
    });
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
          <button
            className="botao secundario pequeno"
            onClick={() =>
              setAbertas(new Set(dados.disciplinas.map((d) => d.chave)))
            }
          >
            Expandir tudo
          </button>
          <button
            className="botao secundario pequeno"
            onClick={() => setAbertas(new Set())}
          >
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
                <span className={`arvore-seta ${aberta ? "aberta" : ""}`}>
                  &#9656;
                </span>
                <span className="marca-no marca-disciplina">D</span>
                <span className="arvore-nome">
                  <span className="codigo-no">{d.codigo}</span>
                  {d.nome}
                </span>
              </button>
              <span className="arvore-meta">{formatarTamanho(d.tamanho)}</span>
              <span className="arvore-meta data">
                {formatarData(d.atualizado_em, false)}
              </span>
            </div>

            {aberta &&
              d.fases.map((f) => (
                <Link
                  key={f.chave}
                  to={`/obras/${obraId}/pastas/${d.codigo}/${f.codigo}`}
                  className="arvore-linha linha-pasta"
                >
                  <span className="arvore-alvo">
                    <span className="arvore-seta" />
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
                  </span>
                  <span className="arvore-meta">{formatarTamanho(f.tamanho)}</span>
                  <span className="arvore-meta data">
                    {formatarData(f.atualizado_em, false)}
                  </span>
                </Link>
              ))}
          </div>
        );
      })}
    </>
  );
}
