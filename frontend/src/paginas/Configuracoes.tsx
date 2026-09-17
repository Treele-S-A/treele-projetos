import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import {
  api,
  ErroApi,
  ROTULO_PAPEL,
  type Membro,
  type Padrao,
  type PapelObra,
  type Usuario,
} from "../api";
import { Aviso, Carregando } from "../componentes";
import { useSessao } from "../sessao";

const PAPEIS: PapelObra[] = ["coordenador", "projetista", "obra", "cliente"];

const O_QUE_O_PAPEL_FAZ: Record<PapelObra, string> = {
  coordenador: "Envia, libera para obra, cancela e gerencia a equipe.",
  projetista: "Envia arquivos e vê tudo, mas não libera para obra.",
  obra: "Baixa o que está liberado e consulta o histórico.",
  cliente: "Baixa somente o que está liberado para obra.",
};

const TIPOS_TOKEN: Array<[string, string]> = [
  ["obra", "Obra — confere com a obra de destino"],
  ["disciplina", "Disciplina — precisa estar cadastrada"],
  ["fase", "Fase — precisa estar cadastrada"],
  ["codigo", "Código livre — número da prancha"],
  ["numero", "Número — só dígitos"],
  ["revisao", "Revisão"],
  ["texto", "Texto — vira o título do documento"],
];
const EXTENSOES = ["dwg", "rvt", "pdf", "ifc"];

export default function Configuracoes() {
  const { obraId } = useParams();
  const { obras, recarregarObras } = useSessao();
  const obra = obras.find((o) => o.id === Number(obraId));

  if (!obra) return <Carregando />;

  return (
    <>
      <div className="cabecalho-area">
        <div>
          <span className="rotulo">
            {obra.codigo} · {obra.nome}
          </span>
          <h1>Configurações da obra</h1>
        </div>
      </div>

      <Equipe obraId={obra.id} />
      <Nomenclatura obraId={obra.id} />
      <Companheiros
        obraId={obra.id}
        regra={obra.regra_companheiro}
        aoSalvar={recarregarObras}
      />
    </>
  );
}

/* --------------------------------------------------------------------- equipe */

function Equipe({ obraId }: { obraId: number }) {
  const [membros, setMembros] = useState<Membro[]>([]);
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [novoUsuario, setNovoUsuario] = useState("");
  const [novoPapel, setNovoPapel] = useState<PapelObra>("projetista");
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [carregando, setCarregando] = useState(true);

  const carregar = useCallback(async () => {
    const [m, u] = await Promise.all([
      api.get<Membro[]>(`/obras/${obraId}/membros`),
      api.get<Usuario[]>("/usuarios"),
    ]);
    setMembros(m);
    setUsuarios(u);
    setCarregando(false);
  }, [obraId]);

  useEffect(() => {
    carregar().catch(() => setCarregando(false));
  }, [carregar]);

  const disponiveis = useMemo(
    () => usuarios.filter((u) => !membros.some((m) => m.usuario_id === u.id)),
    [usuarios, membros],
  );

  async function adicionar() {
    if (!novoUsuario) return;
    setErro(null);
    try {
      await api.post(`/obras/${obraId}/membros`, {
        usuario_id: Number(novoUsuario),
        papel: novoPapel,
      });
      setNovoUsuario("");
      await carregar();
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex : null);
    }
  }

  async function remover(membro: Membro) {
    if (!window.confirm(`Remover ${membro.usuario.nome} desta obra?`)) return;
    setErro(null);
    try {
      await api.delete(`/obras/${obraId}/membros/${membro.id}`);
      await carregar();
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex : null);
    }
  }

  return (
    <div className="folha">
      <div className="folha-titulo">
        <strong>Equipe</strong>
        <span className="silencioso" style={{ fontSize: 12 }}>
          Quem pode ver, enviar e liberar
        </span>
      </div>

      <div className="folha-corpo">
        {erro && <Aviso tom="erro" titulo={erro.message} itens={erro.erros} />}

        <div className="filtros">
          <label className="campo">
            <span className="rotulo">Pessoa</span>
            <select value={novoUsuario} onChange={(e) => setNovoUsuario(e.target.value)}>
              <option value="">Selecione</option>
              {disponiveis.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.nome} · {u.email}
                </option>
              ))}
            </select>
          </label>
          <label className="campo">
            <span className="rotulo">Papel</span>
            <select value={novoPapel} onChange={(e) => setNovoPapel(e.target.value as PapelObra)}>
              {PAPEIS.map((p) => (
                <option key={p} value={p}>
                  {ROTULO_PAPEL[p]}
                </option>
              ))}
            </select>
          </label>
          <div>
            <button className="botao" style={{ marginTop: 21 }} onClick={adicionar}>
              Adicionar à equipe
            </button>
          </div>
        </div>

        <p className="silencioso" style={{ fontSize: 12, marginBottom: 0 }}>
          {O_QUE_O_PAPEL_FAZ[novoPapel]}
        </p>
      </div>

      {carregando ? (
        <Carregando />
      ) : (
        <div className="tabela-rolagem">
          <table className="tabela">
            <thead>
              <tr>
                <th>Nome</th>
                <th>E-mail</th>
                <th>Papel</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {membros.map((m) => (
                <tr key={m.id}>
                  <td>{m.usuario.nome}</td>
                  <td className="silencioso mono" style={{ fontSize: 12 }}>
                    {m.usuario.email}
                  </td>
                  <td>{ROTULO_PAPEL[m.papel]}</td>
                  <td style={{ textAlign: "right" }}>
                    <button className="botao secundario pequeno" onClick={() => remover(m)}>
                      Remover
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* --------------------------------------------------------------- nomenclatura */

function Nomenclatura({ obraId }: { obraId: number }) {
  const [padrao, setPadrao] = useState<Padrao | null>(null);
  const [template, setTemplate] = useState("");
  const [tokens, setTokens] = useState<Record<string, Record<string, unknown>>>({});
  const [extensoes, setExtensoes] = useState<string[]>([]);
  const [exemplo, setExemplo] = useState("");
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [ok, setOk] = useState(false);
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    api.get<Padrao>(`/obras/${obraId}/padrao`).then((p) => {
      setPadrao(p);
      setTemplate(p.template);
      setTokens(p.tokens);
      setExtensoes(p.extensoes);
      setExemplo(p.exemplo ?? "");
    });
  }, [obraId]);

  const nomesNoTemplate = useMemo(
    () => Array.from(template.matchAll(/\{(\w+)\}/g)).map((m) => m[1]),
    [template],
  );

  function ajustar(nome: string, chave: string, valor: unknown) {
    setTokens((t) => ({ ...t, [nome]: { ...(t[nome] ?? {}), [chave]: valor } }));
  }

  async function salvar() {
    setErro(null);
    setOk(false);
    setSalvando(true);
    const limpos: Record<string, Record<string, unknown>> = {};
    for (const nome of nomesNoTemplate) limpos[nome] = tokens[nome] ?? { tipo: "texto" };

    try {
      const p = await api.put<Padrao>(`/obras/${obraId}/padrao`, {
        nome: padrao?.nome ?? "Padrão da obra",
        template,
        tokens: limpos,
        extensoes,
        exemplo: exemplo || null,
      });
      setPadrao(p);
      setTokens(p.tokens);
      setOk(true);
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex : null);
    } finally {
      setSalvando(false);
    }
  }

  if (!padrao) return null;

  return (
    <div className="folha">
      <div className="folha-titulo">
        <strong>Padrão de nomenclatura</strong>
        <span className="silencioso" style={{ fontSize: 12 }}>
          {padrao.obra_id === null ? "Usando o padrão global" : "Específico desta obra"}
        </span>
      </div>

      <div className="folha-corpo">
        {erro && <Aviso tom="erro" titulo={erro.message} itens={erro.erros} />}
        {ok && <Aviso tom="ok">Padrão salvo. Vale para os próximos envios.</Aviso>}

        <label className="campo">
          <span className="rotulo">Template</span>
          <input
            className="mono"
            value={template}
            onChange={(e) => setTemplate(e.target.value)}
            spellCheck={false}
          />
        </label>
        <p className="silencioso" style={{ fontSize: 12, marginTop: 6 }}>
          Escreva os campos entre chaves e o resto como separador literal. O sistema exige um
          campo de revisão, um de disciplina e um de fase — é o que permite classificar o arquivo
          sem ninguém digitar nada.
        </p>

        <div style={{ marginTop: 14 }}>
          <span className="rotulo">Campos</span>
          <div className="tabela-rolagem" style={{ marginTop: 6 }}>
            <table className="tabela">
              <thead>
                <tr>
                  <th>Campo</th>
                  <th>Tipo</th>
                  <th>Dígitos</th>
                  <th>Formato da revisão</th>
                </tr>
              </thead>
              <tbody>
                {nomesNoTemplate.map((nome) => {
                  const spec = tokens[nome] ?? { tipo: "texto" };
                  const tipo = String(spec.tipo ?? "texto");
                  return (
                    <tr key={nome}>
                      <td className="mono">{`{${nome}}`}</td>
                      <td>
                        <select
                          className="entrada"
                          style={{ marginTop: 0 }}
                          value={tipo}
                          onChange={(e) => ajustar(nome, "tipo", e.target.value)}
                        >
                          {TIPOS_TOKEN.map(([valor, descricao]) => (
                            <option key={valor} value={valor}>
                              {descricao}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        {tipo === "numero" || tipo === "revisao" ? (
                          <input
                            className="entrada"
                            style={{ marginTop: 0, width: 72 }}
                            type="number"
                            min={0}
                            max={6}
                            value={Number(spec.digitos ?? 0) || ""}
                            placeholder="livre"
                            onChange={(e) =>
                              ajustar(nome, "digitos", Number(e.target.value) || null)
                            }
                          />
                        ) : (
                          <span className="silencioso">—</span>
                        )}
                      </td>
                      <td>
                        {tipo === "revisao" ? (
                          <select
                            className="entrada"
                            style={{ marginTop: 0 }}
                            value={String(spec.formato ?? "numerico")}
                            onChange={(e) => ajustar(nome, "formato", e.target.value)}
                          >
                            <option value="numerico">Numérico (00, 01, 02)</option>
                            <option value="alfabetico">Alfabético (A, B, C)</option>
                          </select>
                        ) : (
                          <span className="silencioso">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        <div style={{ marginTop: 14 }}>
          <span className="rotulo">Formatos aceitos</span>
          <div className="linha" style={{ marginTop: 6 }}>
            {EXTENSOES.map((e) => (
              <label key={e} className="linha" style={{ gap: 6 }}>
                <input
                  type="checkbox"
                  checked={extensoes.includes(e)}
                  onChange={(ev) =>
                    setExtensoes((atual) =>
                      ev.target.checked ? [...atual, e] : atual.filter((x) => x !== e),
                    )
                  }
                />
                <span className="mono">.{e}</span>
              </label>
            ))}
          </div>
        </div>

        <label className="campo" style={{ marginTop: 14 }}>
          <span className="rotulo">Exemplo mostrado na tela de envio</span>
          <input
            className="mono"
            value={exemplo}
            onChange={(e) => setExemplo(e.target.value)}
            placeholder="TRL001-ARQ-PE-001-R00.pdf"
          />
        </label>

        <div style={{ marginTop: 14 }}>
          <button className="botao" onClick={salvar} disabled={salvando}>
            {salvando ? "Salvando…" : "Salvar padrão"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- companheiro */

function Companheiros({
  obraId,
  regra,
  aoSalvar,
}: {
  obraId: number;
  regra: Record<string, string[]>;
  aoSalvar: () => Promise<void>;
}) {
  const [dwgExigePdf, setDwgExigePdf] = useState((regra.dwg ?? []).includes("pdf"));
  const [rvtExigeIfc, setRvtExigeIfc] = useState((regra.rvt ?? []).includes("ifc"));
  const [ok, setOk] = useState(false);
  const [salvando, setSalvando] = useState(false);

  async function salvar() {
    setSalvando(true);
    setOk(false);
    const nova: Record<string, string[]> = {};
    if (dwgExigePdf) nova.dwg = ["pdf"];
    if (rvtExigeIfc) nova.rvt = ["ifc"];
    await api.patch(`/obras/${obraId}`, { regra_companheiro: nova });
    await aoSalvar();
    setOk(true);
    setSalvando(false);
  }

  return (
    <div className="folha">
      <div className="folha-titulo">
        <strong>Arquivo companheiro</strong>
      </div>
      <div className="folha-corpo">
        {ok && <Aviso tom="ok">Regra salva.</Aviso>}
        <p style={{ marginTop: 0 }} className="silencioso">
          Verificado na hora de liberar para obra. Garante que sempre exista um formato legível
          por quem está em campo — e um formato legível por máquina, que é o que vai permitir a
          descrição automática do que mudou entre revisões.
        </p>
        <label className="linha" style={{ gap: 8 }}>
          <input
            type="checkbox"
            checked={dwgExigePdf}
            onChange={(e) => setDwgExigePdf(e.target.checked)}
          />
          <span>Não liberar DWG sem o PDF plotado</span>
        </label>
        <label className="linha" style={{ gap: 8, marginTop: 8 }}>
          <input
            type="checkbox"
            checked={rvtExigeIfc}
            onChange={(e) => setRvtExigeIfc(e.target.checked)}
          />
          <span>Não liberar RVT sem o IFC exportado</span>
        </label>
        <div style={{ marginTop: 14 }}>
          <button className="botao" onClick={salvar} disabled={salvando}>
            {salvando ? "Salvando…" : "Salvar regra"}
          </button>
        </div>
      </div>
    </div>
  );
}
