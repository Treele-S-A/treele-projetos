import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  api,
  ErroApi,
  formatarData,
  type Arquivo,
  type DocumentoDetalhe,
} from "../api";
import { Aviso, CampoCarimbo, Carregando, Selo } from "../componentes";
import { HistoricoRevisoes, baixarArquivo } from "../Revisoes";
import { MarcaSolicitada, SolicitacoesDoDocumento } from "../Solicitacoes";
import { useSessao } from "../sessao";

export default function Documento() {
  const { documentoId } = useParams();
  const { obras } = useSessao();
  const navegar = useNavigate();

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
  const podeSolicitar = obra?.permissoes.includes("solicitar_revisao") ?? false;

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

  function baixar(arquivo: Arquivo) {
    setErro(null);
    baixarArquivo(arquivo, (m) => setErro(new ErroApi(0, m)), setAviso);
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
        <MarcaSolicitada quantidade={doc.solicitacoes_abertas} />
        {atual && (
          <Selo
            status={atual.status}
            numero={atual.numero}
            data={
              atual.status === "liberado_para_obra" && atual.publicada_em
                ? new Date(atual.publicada_em).toLocaleDateString("pt-BR")
                : null
            }
          />
        )}
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

      <SolicitacoesDoDocumento
        documentoId={doc.id}
        solicitacoes={doc.solicitacoes}
        podeSolicitar={podeSolicitar}
        temLiberada={doc.revisoes.some((r) => r.status === "liberado_para_obra")}
        aoMudar={carregar}
      />

      <div className="folha">
        <div className="folha-titulo">
          <strong>Histórico de revisões</strong>
          <span className="silencioso" style={{ fontSize: 12 }}>
            Mais recente no topo
          </span>
        </div>
        <HistoricoRevisoes
          revisoes={doc.revisoes}
          podePublicar={podePublicar}
          podeCancelar={podeCancelar}
          aoMudar={carregar}
          aoBaixar={baixar}
          aoExcluirDocumento={() => navegar(obra ? `/obras/${obra.id}/acervo` : "/obras")}
          solicitacoes={doc.solicitacoes}
        />
      </div>
    </>
  );
}
