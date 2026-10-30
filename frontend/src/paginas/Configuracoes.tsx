import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import {
  api,
  ErroApi,
  ROTULO_PAPEL,
  type Membro,
  type Obra,
  type Padrao,
  type PapelObra,
  type Usuario,
} from "../api";
import { Aviso, CapaObra, Carregando, LogoObra } from "../componentes";
import { prepararLogo } from "../imagem";
import { useSessao } from "../sessao";

const PAPEIS: PapelObra[] = ["coordenador", "projetista", "obra"];

const O_QUE_O_PAPEL_FAZ: Record<PapelObra, string> = {
  coordenador: "Envia, libera para obra, cancela e gerencia a equipe.",
  projetista: "Envia arquivos e vê tudo, mas não libera para obra.",
  obra: "Baixa o que está liberado e consulta o histórico.",
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
  const { obras, recarregarObras, usuario } = useSessao();
  const obra = obras.find((o) => o.id === Number(obraId));

  if (!obra) return <Carregando />;

  // Configurações são só do administrador (30/10/2026); o engenheiro
  // responsável que não é administrador só mexe na equipe.
  if (!usuario?.admin) {
    return (
      <>
        <div className="cabecalho-area">
          <div>
            <span className="rotulo">
              {obra.codigo} · {obra.nome}
            </span>
            <h1>Equipe da obra</h1>
          </div>
        </div>
        <Equipe obraId={obra.id} gerencia={false} />
      </>
    );
  }

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

      <Endereco obra={obra} aoSalvar={recarregarObras} />
      <Logo obra={obra} aoSalvar={recarregarObras} />
      <Identidade obra={obra} aoSalvar={recarregarObras} />
      <Responsavel obra={obra} aoSalvar={recarregarObras} />
      <Equipe obraId={obra.id} gerencia />
      <Nomenclatura obraId={obra.id} />
      <Companheiros
        obraId={obra.id}
        regra={obra.regra_companheiro}
        aoSalvar={recarregarObras}
      />
    </>
  );
}

/* ------------------------------------------------------------------ endereço */

/** Endereço do empreendimento (TREELE, 29/10/2026): vai na ata de análise
 *  crítica. Obrigatório na obra nova; as antigas preenchem aqui. */
function Endereco({ obra, aoSalvar }: { obra: Obra; aoSalvar: () => Promise<void> }) {
  const [texto, setTexto] = useState(obra.endereco ?? "");
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [ok, setOk] = useState(false);
  const [salvando, setSalvando] = useState(false);

  async function salvar(e: FormEvent) {
    e.preventDefault();
    setErro(null);
    setOk(false);
    setSalvando(true);
    try {
      await api.patch(`/obras/${obra.id}`, { endereco: texto.trim() });
      await aoSalvar();
      setOk(true);
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex : new ErroApi(0, "Não foi possível salvar o endereço."));
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div className="folha">
      <div className="folha-titulo">
        <strong>Endereço do empreendimento</strong>
        <span className="silencioso" style={{ fontSize: 12 }}>
          Vai na ata de análise crítica dos projetos
        </span>
      </div>
      <form className="folha-corpo" onSubmit={salvar}>
        {erro && <Aviso tom="erro" titulo={erro.message} itens={erro.erros} />}
        {ok && <Aviso tom="ok">Endereço salvo.</Aviso>}
        {!obra.endereco && !ok && (
          <Aviso tom="atencao">Esta obra ainda não tem endereço: as atas de análise crítica saem sem ele.</Aviso>
        )}
        <div className="filtros">
          <label className="campo" style={{ flex: "1 1 420px" }}>
            <span className="rotulo">Endereço</span>
            <input
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              placeholder="Rua João Mazzarotto, 526 – Capão Raso – Curitiba – PR"
              minLength={5}
              maxLength={300}
              required
            />
          </label>
          <div>
            <button className="botao" disabled={salvando || texto.trim() === (obra.endereco ?? "")}>
              {salvando ? "Salvando…" : "Salvar endereço"}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}

/* ---------------------------------------------------------------------- logo */

function Logo({ obra, aoSalvar }: { obra: Obra; aoSalvar: () => Promise<void> }) {
  const entrada = useRef<HTMLInputElement>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState<"enviando" | "removendo" | null>(null);

  async function enviar(arquivo: File | undefined) {
    if (!arquivo) return;
    setErro(null);
    setOk(null);
    setOcupado("enviando");
    try {
      const imagem = await prepararLogo(arquivo);
      await api.enviarImagem(`/obras/${obra.id}/logo`, imagem);
      await aoSalvar();
      setOk("Logo salvo.");
    } catch (ex) {
      setErro(ex instanceof Error ? ex.message : "Não foi possível enviar o logo.");
    } finally {
      setOcupado(null);
      // Sem limpar, escolher o mesmo arquivo de novo não dispara nada.
      if (entrada.current) entrada.current.value = "";
    }
  }

  async function remover() {
    setErro(null);
    setOk(null);
    setOcupado("removendo");
    try {
      await api.delete(`/obras/${obra.id}/logo`);
      await aoSalvar();
      setOk("Logo removido.");
    } catch (ex) {
      setErro(ex instanceof Error ? ex.message : "Não foi possível remover o logo.");
    } finally {
      setOcupado(null);
    }
  }

  return (
    <div className="folha">
      <div className="folha-titulo">
        <strong>Logo do empreendimento</strong>
        <span className="silencioso" style={{ fontSize: 12 }}>
          Aparece na lista de obras e no acervo
        </span>
      </div>
      <div className="folha-corpo">
        {erro && <Aviso tom="erro">{erro}</Aviso>}
        {ok && <Aviso tom="ok">{ok}</Aviso>}

        <div className="config-logo">
          <div className="palco-logo">
            <LogoObra
              obra={obra}
              alt={`Logo do ${obra.nome}`}
              reserva={<span className="silencioso">Sem logo</span>}
            />
          </div>
          <div>
            <p className="silencioso" style={{ marginTop: 0 }}>
              PNG, JPG ou WebP. Prefira a versão colorida e com fundo transparente — a
              versão branca some sobre o fundo claro. A imagem é reduzida e as margens
              vazias são cortadas antes de enviar.
            </p>
            <div className="linha">
              <button
                className="botao"
                onClick={() => entrada.current?.click()}
                disabled={ocupado !== null}
              >
                {ocupado === "enviando"
                  ? "Enviando…"
                  : obra.logo_url
                    ? "Trocar logo"
                    : "Enviar logo"}
              </button>
              {obra.logo_url && (
                <button
                  className="botao secundario"
                  onClick={remover}
                  disabled={ocupado !== null}
                >
                  {ocupado === "removendo" ? "Removendo…" : "Remover"}
                </button>
              )}
            </div>
            <input
              ref={entrada}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              hidden
              onChange={(e) => enviar(e.target.files?.[0])}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- identidade */

/** Pontos de partida tirados dos painéis da treèle; qualquer cor vale. */
const CORES_SUGERIDAS: Array<[string, string]> = [
  ["#2f4c52", "Petróleo treèle"],
  ["#7a4a28", "Terra (Serra Dourada)"],
  ["#3a5b62", "Verde-petróleo (Treviso)"],
  ["#0a3a4d", "Azul profundo (Creta)"],
  ["#12a3bd", "Azul-mar (Milos)"],
  ["#4f6b3a", "Oliva"],
  ["#6b3a4a", "Vinho"],
];

function Identidade({ obra, aoSalvar }: { obra: Obra; aoSalvar: () => Promise<void> }) {
  const [cor, setCor] = useState(obra.cor ?? "#2f4c52");
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [ok, setOk] = useState(false);
  const [salvando, setSalvando] = useState(false);

  async function salvar(valor: string) {
    setErro(null);
    setOk(false);
    setSalvando(true);
    try {
      await api.patch(`/obras/${obra.id}`, { cor: valor });
      await aoSalvar();
      setOk(true);
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex : null);
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div className="folha">
      <div className="folha-titulo">
        <strong>Cor da obra</strong>
        <span className="silencioso" style={{ fontSize: 12 }}>
          A cor da identidade do empreendimento — pinta o cartão e o cabeçalho
        </span>
      </div>
      <div className="folha-corpo">
        {erro && <Aviso tom="erro" titulo={erro.message} itens={erro.erros} />}
        {ok && <Aviso tom="ok">Cor salva.</Aviso>}

        <CapaObra obra={{ ...obra, cor }} className="capa-previa">
          <span className="capa-textos">
            <span className="codigo">Obra {obra.codigo}</span>
            <span className="nome-obra">{obra.nome}</span>
          </span>
        </CapaObra>

        <div className="amostras" role="group" aria-label="Cores sugeridas">
          {CORES_SUGERIDAS.map(([valor, nome]) => (
            <button
              key={valor}
              type="button"
              className={`amostra ${cor === valor ? "escolhida" : ""}`}
              style={{ background: valor }}
              title={nome}
              aria-label={nome}
              onClick={() => setCor(valor)}
            />
          ))}
          <label className="amostra-livre" title="Outra cor">
            <input type="color" value={cor} onChange={(e) => setCor(e.target.value)} />
            <span>Outra cor</span>
          </label>
        </div>

        <div className="linha" style={{ marginTop: 14 }}>
          <button className="botao" disabled={salvando} onClick={() => salvar(cor)}>
            {salvando ? "Salvando…" : "Salvar cor"}
          </button>
          {obra.cor && (
            <button className="botao secundario" disabled={salvando} onClick={() => salvar("")}>
              Voltar ao petróleo
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- responsável */

function Responsavel({
  obra,
  aoSalvar,
}: {
  obra: Obra;
  aoSalvar: () => Promise<void>;
}) {
  const [membros, setMembros] = useState<Membro[]>([]);
  const [escolhido, setEscolhido] = useState(String(obra.responsavel?.id ?? ""));
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [ok, setOk] = useState(false);
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    api
      .get<Membro[]>(`/obras/${obra.id}/membros`)
      .then(setMembros)
      .catch(() => setMembros([]));
  }, [obra.id]);

  async function salvar() {
    setErro(null);
    setOk(false);
    setSalvando(true);
    try {
      // 0 limpa o responsável; a API distingue isso de "não mexer".
      await api.patch(`/obras/${obra.id}`, {
        responsavel_id: escolhido ? Number(escolhido) : 0,
      });
      await aoSalvar();
      setOk(true);
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex : null);
    } finally {
      setSalvando(false);
    }
  }

  // Qualquer pessoa da equipe, em qualquer papel: o responsável costuma ser o
  // engenheiro da obra, não alguém da equipe de projetos. A API só exige que
  // seja da equipe — de fora, a pessoa não enxergaria a obra.
  const candidatos = membros;

  return (
    <div className="folha">
      <div className="folha-titulo">
        <strong>Engenheiro responsável</strong>
        <span className="silencioso" style={{ fontSize: 12 }}>
          Quem responde pela obra
        </span>
      </div>
      <div className="folha-corpo">
        {erro && <Aviso tom="erro" titulo={erro.message} itens={erro.erros} />}
        {ok && <Aviso tom="ok">Responsável salvo.</Aviso>}

        <p className="silencioso" style={{ marginTop: 0 }}>
          É diferente de coordenador, que é permissão: pode haver vários
          coordenadores, mas responsável é um só. Ele inclui e remove pessoas
          da equipe; as notificações seguem o papel dele na obra.
        </p>

        <div className="filtros">
          <label className="campo">
            <span className="rotulo">Responsável</span>
            <select value={escolhido} onChange={(e) => setEscolhido(e.target.value)}>
              <option value="">Ninguém definido</option>
              {candidatos.map((m) => (
                <option key={m.id} value={m.usuario_id}>
                  {m.usuario.nome} · {ROTULO_PAPEL[m.papel]}
                </option>
              ))}
            </select>
          </label>
          <div>
            <button
              className="botao"
              style={{ marginTop: 21 }}
              onClick={salvar}
              disabled={salvando}
            >
              {salvando ? "Salvando…" : "Salvar responsável"}
            </button>
          </div>
        </div>

        {candidatos.length === 0 && (
          <p className="silencioso" style={{ fontSize: 12, marginBottom: 0 }}>
            Inclua a pessoa na equipe abaixo, em qualquer papel, para poder
            marcá-la como responsável.
          </p>
        )}
      </div>
    </div>
  );
}

/* --------------------------------------------------------------------- equipe */

/** `gerencia` = coordenador ou administrador. Sem isso é o engenheiro
 *  responsável: inclui e remove pessoas, mas não nomeia nem remove
 *  coordenador, não troca papel e não tira a si mesmo — a API recusa tudo
 *  isso de qualquer forma. */
function Equipe({ obraId, gerencia }: { obraId: number; gerencia: boolean }) {
  const { usuario } = useSessao();
  const papeis = gerencia ? PAPEIS : PAPEIS.filter((p) => p !== "coordenador");
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
    // Comercial fica de fora: já vê todas as obras e não pode ter papel.
    () => usuarios.filter((u) => !u.comercial && !membros.some((m) => m.usuario_id === u.id)),
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
              {papeis.map((p) => (
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
        {!gerencia && (
          <p className="silencioso" style={{ fontSize: 12, marginBottom: 0 }}>
            Como engenheiro responsável, você inclui e remove pessoas já cadastradas.
            Nomear ou remover coordenador e trocar papel é com o coordenador da obra.
          </p>
        )}
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
                  <td>
                    {ROTULO_PAPEL[m.papel]}
                    {m.disciplinas && m.disciplinas.length > 0 && (
                      <span className="silencioso" style={{ fontSize: 11.5 }}> · só {m.disciplinas.join(", ")}</span>
                    )}
                  </td>
                  <td style={{ textAlign: "right" }}>
                    {/* Administrador é coordenador de todas as obras: não sai. */}
                    {!m.usuario.admin &&
                      (gerencia ||
                        (m.papel !== "coordenador" && m.usuario_id !== usuario?.id)) && (
                      <button className="botao secundario pequeno" onClick={() => remover(m)}>
                        Remover
                      </button>
                    )}
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
