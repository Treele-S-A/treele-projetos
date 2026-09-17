import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import {
  api,
  ErroApi,
  formatarData,
  formatarTamanho,
  type Arquivo,
  type DocumentoDetalhe,
  type Revisao,
  type Verificacao,
} from "../api";
import { Aviso, CampoCarimbo, Carregando, Estado, Selo } from "../componentes";
import { useSessao } from "../sessao";

export default function Documento() {
  const { documentoId } = useParams();
  const { obras } = useSessao();

  const [doc, setDoc] = useState<DocumentoDetalhe | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [editandoTitulo, setEditandoTitulo] = useState(false);
  const [rascunhoTitulo, setRascunhoTitulo] = useState("");
  const [salvandoTitulo, setSalvandoTitulo] = useState(false);

  const obra = obras.find((o) => o.id === doc?.obra_id);
  const podePublicar = obra?.permissoes.includes("publicar") ?? false;
  const podeCancelar = obra?.permissoes.includes("cancelar") ?? false;
  // O título não vem no nome do arquivo (decisão da TREELE, 17/09/2026), então
  // é aqui que ele é preenchido — por quem tem permissão de enviar.
  const podeEditarTitulo = obra?.permissoes.includes("enviar") ?? false;

  const carregar = useCallback(async () => {
    setCarregando(true);
    try {
      setDoc(await api.get<DocumentoDetalhe>(`/documentos/${documentoId}`));
      setErro(null);
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex : new ErroApi(0, "Não foi possível abrir o documento."));
    } finally {
      setCarregando(false);
    }
  }, [documentoId]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  async function salvarTitulo(e: FormEvent) {
    e.preventDefault();
    setSalvandoTitulo(true);
    setErro(null);
    try {
      await api.patch(`/documentos/${documentoId}`, { titulo: rascunhoTitulo.trim() });
      await carregar();
      setEditandoTitulo(false);
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex : new ErroApi(0, "Não foi possível salvar."));
    } finally {
      setSalvandoTitulo(false);
    }
  }

  async function baixar(arquivo: Arquivo) {
    setErro(null);
    try {
      const r = await api.get<{ url: string; aviso: string | null }>(
        `/arquivos/${arquivo.id}/download`,
      );
      if (r.aviso) {
        const seguir = window.confirm(`${r.aviso}\n\nBaixar mesmo assim?`);
        if (!seguir) return;
        setAviso(r.aviso);
      }
      window.location.href = r.url;
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex : new ErroApi(0, "Não foi possível baixar."));
    }
  }

  if (carregando) return <Carregando texto="Abrindo documento" />;
  if (!doc) {
    return (
      <Aviso tom="erro" titulo={erro?.message ?? "Documento não encontrado."} itens={erro?.erros} />
    );
  }

  const atual = doc.revisoes.find((r) => r.status !== "cancelado") ?? doc.revisoes[0] ?? null;

  return (
    <>
      <div className="cabecalho-area">
        <div>
          <span className="rotulo">
            {obra ? (
              <Link to={`/obras/${obra.id}/acervo`} style={{ textDecoration: "underline" }}>
                {obra.codigo} · {obra.nome}
              </Link>
            ) : (
              "Documento"
            )}
          </span>
          <h1 className="mono" style={{ letterSpacing: "-0.02em" }}>
            {doc.codigo}
          </h1>
          {editandoTitulo ? (
            <form onSubmit={salvarTitulo} className="linha" style={{ marginTop: 6 }}>
              <input
                className="entrada"
                style={{ marginTop: 0, width: 340, maxWidth: "100%" }}
                value={rascunhoTitulo}
                onChange={(e) => setRascunhoTitulo(e.target.value)}
                placeholder="Ex.: Planta de Forma — Pav. Tipo"
                maxLength={300}
                autoFocus
              />
              <button className="botao pequeno" disabled={salvandoTitulo}>
                {salvandoTitulo ? "Salvando…" : "Salvar"}
              </button>
              <button
                type="button"
                className="botao secundario pequeno"
                onClick={() => setEditandoTitulo(false)}
              >
                Cancelar
              </button>
            </form>
          ) : (
            <div className="linha" style={{ marginTop: 4 }}>
              {doc.titulo ? (
                <span className="silencioso">{doc.titulo}</span>
              ) : (
                podeEditarTitulo && <span className="rotulo">Sem título</span>
              )}
              {podeEditarTitulo && (
                <button
                  className="botao secundario pequeno"
                  onClick={() => {
                    setRascunhoTitulo(doc.titulo ?? "");
                    setEditandoTitulo(true);
                  }}
                >
                  {doc.titulo ? "Editar título" : "Adicionar título"}
                </button>
              )}
            </div>
          )}
        </div>
        {atual && <Selo status={atual.status} />}
      </div>

      {erro && <Aviso tom="erro" titulo={erro.message} itens={erro.erros} />}
      {aviso && <Aviso tom="atencao">{aviso}</Aviso>}

      <div className="folha">
        <div className="carimbo" style={{ borderTop: "none" }}>
          <CampoCarimbo
            rotulo="Disciplina"
            valor={`${doc.disciplina.codigo} · ${doc.disciplina.nome}`}
          />
          <CampoCarimbo rotulo="Fase" valor={`${doc.fase.codigo} · ${doc.fase.nome}`} />
          <CampoCarimbo
            rotulo="Revisão atual"
            valor={atual ? `R${atual.numero}` : "—"}
          />
          <CampoCarimbo rotulo="Revisões" valor={doc.total_revisoes} />
          <CampoCarimbo
            rotulo="Liberada em"
            valor={formatarData(atual?.publicada_em ?? null)}
          />
        </div>
      </div>

      <div className="folha">
        <div className="folha-titulo">
          <strong>Histórico de revisões</strong>
          <span className="silencioso" style={{ fontSize: 12 }}>
            Mais recente no topo
          </span>
        </div>
        {doc.revisoes.map((r) => (
          <LinhaRevisao
            key={r.id}
            revisao={r}
            podePublicar={podePublicar}
            podeCancelar={podeCancelar}
            aoMudar={carregar}
            aoBaixar={baixar}
          />
        ))}
      </div>
    </>
  );
}

function LinhaRevisao({
  revisao,
  podePublicar,
  podeCancelar,
  aoMudar,
  aoBaixar,
}: {
  revisao: Revisao;
  podePublicar: boolean;
  podeCancelar: boolean;
  aoMudar: () => Promise<void>;
  aoBaixar: (a: Arquivo) => void;
}) {
  const [verificacao, setVerificacao] = useState<Verificacao | null>(null);
  const [descricao, setDescricao] = useState(revisao.descricao ?? "");
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<ErroApi | null>(null);

  const emRevisao = revisao.status === "em_revisao";

  useEffect(() => {
    if (!emRevisao) return;
    api
      .get<Verificacao>(`/revisoes/${revisao.id}/verificar`)
      .then(setVerificacao)
      .catch(() => setVerificacao(null));
  }, [revisao.id, emRevisao]);

  async function publicar() {
    setOcupado(true);
    setErro(null);
    try {
      await api.post(`/revisoes/${revisao.id}/publicar`, { descricao: descricao.trim() || null });
      await aoMudar();
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex : new ErroApi(0, "Não foi possível liberar."));
    } finally {
      setOcupado(false);
    }
  }

  async function cancelar() {
    if (!window.confirm(`Cancelar a revisão R${revisao.numero}? Ela deixa de valer.`)) return;
    setOcupado(true);
    try {
      await api.post(`/revisoes/${revisao.id}/cancelar`);
      await aoMudar();
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex : new ErroApi(0, "Não foi possível cancelar."));
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className={`revisao ${revisao.status === "obsoleto" ? "obsoleta" : ""}`}>
      <div className="revisao-topo">
        <div>
          <span className="rotulo">Revisão</span>
          <div className="numero-rev">R{revisao.numero}</div>
        </div>

        <div style={{ flex: 1, minWidth: 220 }}>
          <Estado status={revisao.status} />
          <div className="silencioso" style={{ fontSize: 12, marginTop: 6 }}>
            Enviada em {formatarData(revisao.criada_em)}
            {revisao.criada_por && ` por ${revisao.criada_por.nome}`}
            {revisao.publicada_em &&
              ` · Liberada em ${formatarData(revisao.publicada_em)}${
                revisao.publicada_por ? ` por ${revisao.publicada_por.nome}` : ""
              }`}
          </div>

          {revisao.descricao_ia && (
            <div style={{ marginTop: 10 }}>
              <span className="rotulo">O que mudou (gerado automaticamente)</span>
              <div style={{ marginTop: 3 }}>{revisao.descricao_ia}</div>
            </div>
          )}

          {revisao.descricao && !emRevisao && (
            <div style={{ marginTop: 10 }}>
              <span className="rotulo">Descrição</span>
              <div style={{ marginTop: 3 }}>{revisao.descricao}</div>
            </div>
          )}
        </div>
      </div>

      {erro && (
        <div style={{ marginTop: 12 }}>
          <Aviso tom="erro" titulo={erro.message} itens={erro.erros} />
        </div>
      )}

      {revisao.arquivos.length > 0 && (
        <div className="arquivos">
          {revisao.arquivos.map((a) => (
            <div className="arquivo" key={a.id}>
              <div className="linha" style={{ gap: 8, minWidth: 0 }}>
                <span className="tipo">{a.tipo.toUpperCase()}</span>
                <span className="nome">{a.nome_original}</span>
                {a.status !== "disponivel" && (
                  <span className="estado estado-em_revisao">
                    {a.status === "pendente" ? "Envio incompleto" : "Falhou"}
                  </span>
                )}
              </div>
              <div className="linha">
                <span className="silencioso mono" style={{ fontSize: 11 }}>
                  {formatarTamanho(a.tamanho)}
                </span>
                <button
                  className="botao secundario pequeno"
                  disabled={a.status !== "disponivel"}
                  onClick={() => aoBaixar(a)}
                >
                  Baixar
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {emRevisao && (
        <div style={{ marginTop: 14 }}>
          {verificacao && verificacao.impedimentos.length > 0 && (
            <Aviso
              tom="atencao"
              titulo="Ainda não dá para liberar esta revisão"
              itens={verificacao.impedimentos}
            />
          )}

          {podePublicar ? (
            <>
              <label className="campo">
                <span className="rotulo">O que mudou nesta revisão</span>
                <textarea
                  value={descricao}
                  onChange={(e) => setDescricao(e.target.value)}
                  placeholder="Ex.: Ajuste de armadura da viga V12 e revisão das cotas do eixo 4."
                />
              </label>
              <div className="linha" style={{ marginTop: 10 }}>
                <button
                  className="botao"
                  disabled={ocupado || !verificacao?.pode_publicar}
                  onClick={publicar}
                >
                  {ocupado ? "Liberando…" : "Liberar para obra"}
                </button>
                {podeCancelar && (
                  <button className="botao perigo pequeno" disabled={ocupado} onClick={cancelar}>
                    Cancelar revisão
                  </button>
                )}
              </div>
            </>
          ) : (
            <p className="silencioso" style={{ fontSize: 12, margin: 0 }}>
              Esta revisão aguarda liberação do coordenador da obra.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
