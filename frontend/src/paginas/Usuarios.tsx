import { Fragment, useCallback, useEffect, useState, type FormEvent } from "react";
import { api, ErroApi, type Usuario } from "../api";
import { Aviso, Carregando } from "../componentes";
import { useSessao } from "../sessao";

/** Os tipos de acesso (TREELE, 30/10/2026; backend services/acesso.py). */
type Tipo = "administrador" | "comercial" | "todas_obras" | "obra_especifica";

interface UsuarioComAcesso extends Usuario {
  todas_obras: boolean;
  tipo: Tipo;
  obras: { obra_id: number; codigo: string; papel: "coordenador" | "projetista" | "obra" }[];
}

const TIPOS: [Tipo, string, string][] = [
  ["obra_especifica", "Usuário de obra específica", "Só as obras escolhidas (papel \"obra\" ao entrar por aqui; o papel muda na equipe da obra)."],
  ["todas_obras", "Usuário de todas as obras", "Equipe de obra em todas as obras, inclusive nas criadas depois: vê e baixa o que está liberado."],
  ["comercial", "Comercial", "Vê todas as obras, mas só baixa o que é da disciplina COM e está liberado."],
  ["administrador", "Administrador", "Cria obras, usuários e catálogos; vê e faz tudo."],
];
const ROTULO_TIPO: Record<Tipo, string> = {
  obra_especifica: "Obra específica",
  todas_obras: "Todas as obras",
  comercial: "Comercial",
  administrador: "Administrador",
};

/** Escolha do tipo e, para obra específica, das obras. */
function EscolhaAcesso({
  tipo,
  obras,
  aoMudarTipo,
  aoMudarObras,
  nome,
}: {
  tipo: Tipo;
  obras: number[];
  aoMudarTipo: (t: Tipo) => void;
  aoMudarObras: (o: number[]) => void;
  nome: string;
}) {
  const { obras: todas } = useSessao();
  return (
    <>
      <fieldset className="perfis">
        <legend className="rotulo">Tipo de acesso</legend>
        {TIPOS.map(([valor, rotulo, descricao]) => (
          <label key={valor} className="perfil-opcao">
            <input type="radio" name={nome} checked={tipo === valor} onChange={() => aoMudarTipo(valor)} />
            <span>
              <strong>{rotulo}</strong>
              <span className="silencioso">{descricao}</span>
            </span>
          </label>
        ))}
      </fieldset>
      {tipo === "obra_especifica" && (
        <fieldset className="perfis">
          <legend className="rotulo">Obras</legend>
          <div className="chips-escolha">
            {todas.map((o) => (
              <button
                type="button"
                key={o.id}
                className={obras.includes(o.id) ? "marcado" : ""}
                aria-pressed={obras.includes(o.id)}
                onClick={() => aoMudarObras(obras.includes(o.id) ? obras.filter((x) => x !== o.id) : [...obras, o.id])}
                title={o.nome}
              >
                {o.codigo} · {o.nome}
              </button>
            ))}
          </div>
        </fieldset>
      )}
    </>
  );
}

export default function Usuarios() {
  const [usuarios, setUsuarios] = useState<UsuarioComAcesso[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [busca, setBusca] = useState("");

  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [tipo, setTipo] = useState<Tipo>("obra_especifica");
  const [obras, setObras] = useState<number[]>([]);
  const [salvando, setSalvando] = useState(false);
  const [editando, setEditando] = useState<{ id: number; tipo: Tipo; obras: number[] } | null>(null);

  const carregar = useCallback(async () => {
    setUsuarios(await api.get<UsuarioComAcesso[]>("/usuarios?incluir_inativos=true"));
    setCarregando(false);
  }, []);

  useEffect(() => {
    carregar().catch(() => setCarregando(false));
  }, [carregar]);

  async function criar(e: FormEvent) {
    e.preventDefault();
    setErro(null);
    setOk(null);
    setSalvando(true);
    try {
      await api.post("/usuarios", {
        nome: nome.trim(),
        email: email.trim(),
        senha: senha || null,
        tipo,
        obras: tipo === "obra_especifica" ? obras : [],
      });
      setOk(
        senha
          ? `${nome.trim()} já pode entrar. Passe a senha por um canal seguro e peça para trocá-la em Minha conta no primeiro acesso.`
          : `${nome.trim()} já pode entrar pelo botão "Entrar com Microsoft", com a conta corporativa.`,
      );
      setNome("");
      setEmail("");
      setSenha("");
      setTipo("obra_especifica");
      setObras([]);
      await carregar();
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex : null);
    } finally {
      setSalvando(false);
    }
  }

  async function salvarAcesso() {
    if (!editando) return;
    setErro(null);
    setOk(null);
    try {
      const u = await api.patch<UsuarioComAcesso>(`/usuarios/${editando.id}/acesso`, {
        tipo: editando.tipo,
        obras: editando.tipo === "obra_especifica" ? editando.obras : null,
      });
      setOk(`Acesso de ${u.nome}: ${ROTULO_TIPO[u.tipo]}.`);
      setEditando(null);
      await carregar();
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex : null);
    }
  }

  async function redefinir(u: Usuario) {
    const senha = window.prompt(`Nova senha para ${u.nome} (pelo menos 8 caracteres):`);
    if (senha === null) return;
    setErro(null);
    setOk(null);
    if (senha.length < 8) {
      setErro(new ErroApi(0, "A senha precisa ter ao menos 8 caracteres."));
      return;
    }
    try {
      await api.post(`/usuarios/${u.id}/senha`, { senha_nova: senha });
      setOk(
        `Senha de ${u.nome} redefinida. Passe a nova por um canal seguro e peça ` +
          "para trocá-la em Minha conta.",
      );
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex : null);
    }
  }

  async function alternar(u: Usuario) {
    setErro(null);
    try {
      await api.patch(`/usuarios/${u.id}/ativo?ativo=${!u.ativo}`);
      await carregar();
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex : null);
    }
  }

  const termo = busca.trim().toLowerCase();
  const visiveis = usuarios.filter(
    (u) => !termo || u.nome.toLowerCase().includes(termo) || u.email.toLowerCase().includes(termo),
  );

  return (
    <>
      <div className="cabecalho-area">
        <div>
          <span className="rotulo">Administração</span>
          <h1>Usuários</h1>
        </div>
      </div>

      <div className="folha">
        <div className="folha-titulo">
          <strong>Novo usuário</strong>
        </div>
        <form className="folha-corpo" onSubmit={criar}>
          {erro && !editando && <Aviso tom="erro" titulo={erro.message} itens={erro.erros} />}
          {ok && <Aviso tom="ok">{ok}</Aviso>}

          <div className="filtros">
            <label className="campo">
              <span className="rotulo">Nome</span>
              <input value={nome} onChange={(e) => setNome(e.target.value)} required />
            </label>
            <label className="campo">
              <span className="rotulo">E-mail</span>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </label>
            <label className="campo">
              <span className="rotulo">Senha inicial (opcional)</span>
              <input
                type="text"
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
                minLength={8}
                placeholder="Vazia: entra com a conta Microsoft"
              />
            </label>
          </div>

          <EscolhaAcesso tipo={tipo} obras={obras} aoMudarTipo={setTipo} aoMudarObras={setObras} nome="tipo-novo" />

          <div style={{ marginTop: 14 }}>
            <button className="botao" disabled={salvando}>
              {salvando ? "Criando…" : "Criar usuário"}
            </button>
          </div>
        </form>
      </div>

      <div className="folha">
        <div className="folha-corpo">
          <label className="campo" style={{ maxWidth: 360 }}>
            <span className="rotulo">Buscar</span>
            <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Nome ou e-mail" />
          </label>
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
                  <th>Tipo de acesso</th>
                  <th>Situação</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {visiveis.map((u) => (
                  <Fragment key={u.id}>
                    <tr>
                      <td>{u.nome}</td>
                      <td className="silencioso mono" style={{ fontSize: 12 }}>
                        {u.email}
                      </td>
                      <td>
                        <span className="silencioso">{ROTULO_TIPO[u.tipo]}</span>
                        {u.tipo === "obra_especifica" && (
                          <span className="chips-escopo" style={{ marginTop: 3 }}>
                            {u.obras.length === 0 ? (
                              <span className="silencioso" style={{ fontSize: 11.5 }}>nenhuma obra</span>
                            ) : (
                              u.obras.map((o) => (
                                <span key={o.obra_id} className="chip-escopo" title={`Papel: ${o.papel}`}>
                                  {o.codigo}
                                </span>
                              ))
                            )}
                          </span>
                        )}
                      </td>
                      <td>
                        <span className={`estado estado-${u.ativo ? "liberado_para_obra" : "cancelado"}`}>
                          {u.ativo ? "Ativo" : "Inativo"}
                        </span>
                      </td>
                      <td>
                        <div className="linha" style={{ gap: 8, justifyContent: "flex-end" }}>
                          <button
                            className="botao secundario pequeno"
                            onClick={() =>
                              setEditando(
                                editando?.id === u.id
                                  ? null
                                  : { id: u.id, tipo: u.tipo, obras: u.obras.map((o) => o.obra_id) },
                              )
                            }
                          >
                            Editar acesso
                          </button>
                          <button className="botao secundario pequeno" onClick={() => redefinir(u)}>
                            Redefinir senha
                          </button>
                          <button className="botao secundario pequeno" onClick={() => alternar(u)}>
                            {u.ativo ? "Desativar" : "Reativar"}
                          </button>
                        </div>
                      </td>
                    </tr>
                    {editando?.id === u.id && (
                      <tr className="linha-edicao-acesso">
                        <td colSpan={5}>
                          {erro && <Aviso tom="erro" titulo={erro.message} itens={erro.erros} />}
                          <EscolhaAcesso
                            tipo={editando.tipo}
                            obras={editando.obras}
                            aoMudarTipo={(t) => setEditando({ ...editando, tipo: t })}
                            aoMudarObras={(o) => setEditando({ ...editando, obras: o })}
                            nome={`tipo-${u.id}`}
                          />
                          <div className="linha" style={{ gap: 8, marginTop: 10 }}>
                            <button className="botao pequeno" onClick={salvarAcesso}>
                              Salvar acesso
                            </button>
                            <button className="botao secundario pequeno" onClick={() => setEditando(null)}>
                              Cancelar
                            </button>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
