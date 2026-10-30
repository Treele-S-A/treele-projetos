import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, ErroApi } from "../api";
import { Aviso, SIMBOLO } from "../componentes";
import { useSessao } from "../sessao";

export default function Entrar() {
  const { entrar } = useSessao();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [manter, setManter] = useState(false);
  const [erro, setErro] = useState<string | null>(() => {
    return new URLSearchParams(window.location.hash.slice(1)).get("entra_erro");
  });
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    if (new URLSearchParams(window.location.hash.slice(1)).has("entra_erro")) {
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
    }
  }, []);

  async function aoEnviar(e: FormEvent) {
    e.preventDefault();
    setErro(null);
    setEnviando(true);
    try {
      await entrar(email.trim(), senha, manter);
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex.message : "Não foi possível entrar.");
      setEnviando(false);
    }
  }

  async function aoMicrosoft() {
    setErro(null);
    setEnviando(true);
    try {
      const { configurado } = await api.get<{ configurado: boolean }>("/auth/microsoft/status");
      if (!configurado) throw new Error("Login Microsoft ainda não configurado neste sistema.");
      window.location.assign(`${api.base}/auth/microsoft/start`);
    } catch (ex) {
      setErro(ex instanceof Error ? ex.message : "Não foi possível iniciar o login Microsoft.");
      setEnviando(false);
    }
  }

  return (
    <div className="tela-entrar">
      <div>
        <div className="cartao-entrar">
          <div className="topo">
            <img src={SIMBOLO} alt="" />
            <h1 className="marca-nome">Projetos</h1>
            <div className="marca-sub">Treèle Construtora</div>
          </div>

          <form onSubmit={aoEnviar}>
            {erro && (
              <Aviso tom="erro">
                {erro.includes("Solicite seu acesso") ? (
                  <>
                    Acesso não permitido. <Link to="/solicitar-acesso">Solicite seu acesso</Link>.
                  </>
                ) : (
                  erro
                )}
              </Aviso>
            )}

            <label className="campo">
              <span className="rotulo">E-mail</span>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="username"
                required
                autoFocus
              />
            </label>

            <label className="campo">
              <span className="rotulo">Senha</span>
              <input
                type="password"
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
                autoComplete="current-password"
                required
              />
            </label>

            <label className="manter-conectado">
              <input
                type="checkbox"
                checked={manter}
                onChange={(e) => setManter(e.target.checked)}
              />
              <span>
                Manter conectado por 30 dias
                <small>Só em computador ou celular seu. Sem marcar, vale 12 horas.</small>
              </span>
            </label>

            <button className="botao" type="submit" disabled={enviando}>
              {enviando ? "Entrando…" : "Entrar"}
            </button>
          </form>
          <div className="entrar-microsoft">
            <span>ou</span>
            <button
              className="botao-entra"
              type="button"
              disabled={enviando}
              onClick={aoMicrosoft}
            >
              <span className="marca-microsoft" aria-hidden="true"><i /><i /><i /><i /></span>
              Entrar com Microsoft Entra ID
            </button>
          </div>
        </div>
        {/* Projetista e comercial de fora (TREELE, 30/10/2026): pedem o
            acesso antes de tentar entrar. */}
        <div className="solicitar-acesso-entrar">
          <span>Usuário fora do domínio @treele? Solicite seu acesso</span>
          <Link className="botao secundario pequeno" to="/solicitar-acesso">
            Solicitar acesso
          </Link>
        </div>
      </div>
    </div>
  );
}
