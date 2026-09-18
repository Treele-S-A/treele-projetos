import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  api,
  ErroApi,
  formatarData,
  formatarTamanho,
  type StatusRevisao,
  type TipoArquivo,
} from "./api";
import { Aviso, Carregando, Estado, Vazio } from "./componentes";

interface ArquivoNaArvore {
  id: number;
  nome: string;
  tamanho: number;
  enviado_em: string;
  documento_id: number;
  documento_codigo: string;
  documento_titulo: string | null;
  revisao: string;
  status: StatusRevisao;
}

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
  arquivos: ArquivoNaArvore[];
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

const RECUO = 22;

function Linha({
  nivel,
  aberto,
  marca,
  codigo,
  nome,
  tamanho,
  data,
  classe,
  aoAlternar,
}: {
  nivel: number;
  aberto: boolean;
  marca?: { letra: string; classe: string };
  codigo?: string;
  nome: ReactNode;
  tamanho: number;
  data: string | null;
  classe?: string;
  aoAlternar: () => void;
}) {
  return (
    <div
      className={`arvore-linha ${classe ?? ""}`}
      style={{ paddingLeft: 16 + nivel * RECUO }}
    >
      <button className="arvore-alvo" onClick={aoAlternar} aria-expanded={aberto}>
        <span className={`arvore-seta ${aberto ? "aberta" : ""}`}>&#9656;</span>
        {marca && <span className={`marca-no ${marca.classe}`}>{marca.letra}</span>}
        <span className="arvore-nome">
          {codigo && <span className="codigo-no">{codigo}</span>}
          {nome}
        </span>
      </button>
      <span className="arvore-meta">{tamanho ? formatarTamanho(tamanho) : "—"}</span>
      <span className="arvore-meta data">{formatarData(data, false)}</span>
    </div>
  );
}

export default function Arvore({
  obraId,
  podeVerHistorico,
}: {
  obraId: number;
  podeVerHistorico: boolean;
}) {
  const [dados, setDados] = useState<ArvoreDados | null>(null);
  const [abertos, setAbertos] = useState<Set<string>>(new Set());
  const [historico, setHistorico] = useState(false);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    setCarregando(true);
    const consulta = historico ? "?todas_revisoes=true" : "";
    api
      .get<ArvoreDados>(`/obras/${obraId}/arvore${consulta}`)
      .then(setDados)
      .catch((ex) =>
        setErro(
          ex instanceof ErroApi ? ex.message : "Não foi possível montar a árvore.",
        ),
      )
      .finally(() => setCarregando(false));
  }, [obraId, historico]);

  function alternar(chave: string) {
    setAbertos((atual) => {
      const novo = new Set(atual);
      if (novo.has(chave)) novo.delete(chave);
      else novo.add(chave);
      return novo;
    });
  }

  function expandirTudo() {
    if (!dados) return;
    const todas = new Set<string>();
    for (const d of dados.disciplinas) {
      todas.add(d.chave);
      for (const f of d.fases) {
        todas.add(f.chave);
        for (const tp of f.tipos) todas.add(tp.chave);
      }
    }
    setAbertos(todas);
  }

  async function baixar(arquivo: ArquivoNaArvore) {
    try {
      const r = await api.get<{ url: string; aviso: string | null }>(
        `/arquivos/${arquivo.id}/download`,
      );
      if (r.aviso && !window.confirm(`${r.aviso}\n\nBaixar mesmo assim?`)) return;
      window.location.href = r.url;
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex.message : "Não foi possível baixar.");
    }
  }

  if (carregando && !dados) return <Carregando texto="Montando a árvore" />;
  if (erro && !dados) return <Aviso tom="erro">{erro}</Aviso>;
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
          {podeVerHistorico && (
            <label className="linha" style={{ gap: 6, fontSize: 12 }}>
              <input
                type="checkbox"
                checked={historico}
                onChange={(e) => setHistorico(e.target.checked)}
              />
              <span>Incluir revisões anteriores</span>
            </label>
          )}
          <button className="botao secundario pequeno" onClick={expandirTudo}>
            Expandir tudo
          </button>
          <button
            className="botao secundario pequeno"
            onClick={() => setAbertos(new Set())}
          >
            Recolher
          </button>
        </div>
      </div>

      {erro && (
        <div style={{ padding: "12px 16px 0" }}>
          <Aviso tom="erro">{erro}</Aviso>
        </div>
      )}

      {dados.disciplinas.map((d) => {
        const dAberta = abertos.has(d.chave);
        return (
          <div key={d.chave}>
            <Linha
              nivel={0}
              classe="nivel-disciplina"
              aberto={dAberta}
              marca={{ letra: "D", classe: "marca-disciplina" }}
              codigo={d.codigo}
              nome={d.nome}
              tamanho={d.tamanho}
              data={d.atualizado_em}
              aoAlternar={() => alternar(d.chave)}
            />

            {dAberta &&
              d.fases.map((f) => {
                const fAberta = abertos.has(f.chave);
                return (
                  <div key={f.chave}>
                    <Linha
                      nivel={1}
                      aberto={fAberta}
                      marca={{ letra: "F", classe: "marca-fase" }}
                      codigo={f.codigo}
                      nome={f.nome}
                      tamanho={f.tamanho}
                      data={f.atualizado_em}
                      aoAlternar={() => alternar(f.chave)}
                    />

                    {fAberta &&
                      f.tipos.map((tp) => {
                        const tAberto = abertos.has(tp.chave);
                        return (
                          <div key={tp.chave}>
                            <Linha
                              nivel={2}
                              aberto={tAberto}
                              nome={
                                <>
                                  <span className="tipo" style={{ marginRight: 8 }}>
                                    {tp.codigo}
                                  </span>
                                  <span
                                    className="silencioso"
                                    style={{ fontSize: 12, fontWeight: 400 }}
                                  >
                                    {tp.arquivos.length} arquivo
                                    {tp.arquivos.length === 1 ? "" : "s"}
                                  </span>
                                </>
                              }
                              tamanho={tp.tamanho}
                              data={tp.atualizado_em}
                              aoAlternar={() => alternar(tp.chave)}
                            />

                            {tAberto &&
                              tp.arquivos.map((arq) => (
                                <div
                                  key={arq.id}
                                  className="arvore-linha arquivo"
                                  style={{ paddingLeft: 16 + 3 * RECUO }}
                                >
                                  <span
                                    className="arvore-alvo"
                                    style={{ cursor: "default" }}
                                  >
                                    <span className="arvore-seta" />
                                    <Link
                                      className="arvore-nome"
                                      to={`/documentos/${arq.documento_id}`}
                                      title={
                                        arq.documento_titulo ?? arq.documento_codigo
                                      }
                                      style={{ color: "var(--azul)" }}
                                    >
                                      {arq.nome}
                                    </Link>
                                    {arq.status !== "liberado_para_obra" && (
                                      <Estado status={arq.status} />
                                    )}
                                  </span>
                                  <span className="arvore-meta">
                                    {formatarTamanho(arq.tamanho)}
                                  </span>
                                  <button
                                    className="botao secundario pequeno"
                                    onClick={() => baixar(arq)}
                                  >
                                    Baixar
                                  </button>
                                </div>
                              ))}
                          </div>
                        );
                      })}
                  </div>
                );
              })}
          </div>
        );
      })}
    </>
  );
}
