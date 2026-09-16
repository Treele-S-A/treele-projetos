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
  const [admin, setAdmin] = useState(false);
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
      await api.post("/usuarios", { nome: nome.trim(), email: email.trim(), senha, admin });
      setOk(`${nome.trim()} já pode entrar. Passe a senha por um canal seguro.`);
      setNome("");
      setEmail("");
      setSenha("");
      setAdmin(false);
      await carregar();
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex : null);
    } finally {
      setSalvando(false);
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

          <label className="linha" style={{ gap: 8, marginTop: 12 }}>
            <input
              type="checkbox"
              checked={admin}
              onChange={(e) => setAdmin(e.target.checked)}
            />
            <span>Administrador — cria obras, usuários e catálogos</span>
          </label>

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
                    <td className="silencioso">{u.admin ? "Administrador" : "Usuário"}</td>
                    <td>
                      <span className={`estado estado-${u.ativo ? "liberado_para_obra" : "cancelado"}`}>
                        {u.ativo ? "Ativo" : "Inativo"}
                      </span>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <button className="botao secundario pequeno" onClick={() => alternar(u)}>
                        {u.ativo ? "Desativar" : "Reativar"}
                      </button>
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
