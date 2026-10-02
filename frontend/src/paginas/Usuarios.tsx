import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, ErroApi, type Usuario } from "../api";
import { Aviso, Carregando } from "../componentes";

export default function Usuarios() {
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [perfil, setPerfil] = useState<"usuario" | "admin" | "comercial">("usuario");
  const [salvando, setSalvando] = useState(false);

  const carregar = useCallback(async () => {
    setUsuarios(await api.get<Usuario[]>("/usuarios?incluir_inativos=true"));
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
        senha,
        admin: perfil === "admin",
        comercial: perfil === "comercial",
      });
      setOk(
        `${nome.trim()} já pode entrar. Passe a senha por um canal seguro e peça ` +
          "para trocá-la em Minha conta no primeiro acesso.",
      );
      setNome("");
      setEmail("");
      setSenha("");
      setPerfil("usuario");
      await carregar();
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex : null);
    } finally {
      setSalvando(false);
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
          {erro && <Aviso tom="erro" titulo={erro.message} itens={erro.erros} />}
          {ok && <Aviso tom="ok">{ok}</Aviso>}

          <div className="filtros">
            <label className="campo">
              <span className="rotulo">Nome</span>
              <input value={nome} onChange={(e) => setNome(e.target.value)} required />
            </label>
            <label className="campo">
              <span className="rotulo">E-mail</span>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </label>
            <label className="campo">
              <span className="rotulo">Senha inicial</span>
              <input
                type="text"
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
                minLength={8}
                required
              />
            </label>
          </div>

          <fieldset className="perfis">
            <legend className="rotulo">Perfil</legend>
            {(
              [
                ["usuario", "Usuário", "Acessa as obras em que for incluído na equipe, conforme o papel."],
                ["admin", "Administrador", "Cria obras, usuários e catálogos; vê e faz tudo."],
                ["comercial", "Comercial", "Vê todas as obras, mas só baixa o que é da disciplina COM e está liberado. Não envia, não exclui, não configura."],
              ] as const
            ).map(([valor, rotulo, descricao]) => (
              <label key={valor} className="perfil-opcao">
                <input
                  type="radio"
                  name="perfil"
                  checked={perfil === valor}
                  onChange={() => setPerfil(valor)}
                />
                <span>
                  <strong>{rotulo}</strong>
                  <span className="silencioso">{descricao}</span>
                </span>
              </label>
            ))}
          </fieldset>

          <div style={{ marginTop: 14 }}>
            <button className="botao" disabled={salvando}>
              {salvando ? "Criando…" : "Criar usuário"}
            </button>
          </div>
        </form>
      </div>

      <div className="folha">
        {carregando ? (
          <Carregando />
        ) : (
          <div className="tabela-rolagem">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Nome</th>
                  <th>E-mail</th>
                  <th>Perfil</th>
                  <th>Situação</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {usuarios.map((u) => (
                  <tr key={u.id}>
                    <td>{u.nome}</td>
                    <td className="silencioso mono" style={{ fontSize: 12 }}>
                      {u.email}
                    </td>
                    <td className="silencioso">
                      {u.admin ? "Administrador" : u.comercial ? "Comercial" : "Usuário"}
                    </td>
                    <td>
                      <span className={`estado estado-${u.ativo ? "liberado_para_obra" : "cancelado"}`}>
                        {u.ativo ? "Ativo" : "Inativo"}
                      </span>
                    </td>
                    <td>
                      <div className="linha" style={{ gap: 8, justifyContent: "flex-end" }}>
                        <button className="botao secundario pequeno" onClick={() => redefinir(u)}>
                          Redefinir senha
                        </button>
                        <button className="botao secundario pequeno" onClick={() => alternar(u)}>
                          {u.ativo ? "Desativar" : "Reativar"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
