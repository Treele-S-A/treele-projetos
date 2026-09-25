import { useState, type FormEvent } from "react";
import { ErroApi } from "../api";
import { Aviso, SIMBOLO } from "../componentes";
import { useSessao } from "../sessao";

export default function Entrar() {
  const { entrar } = useSessao();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function aoEnviar(e: FormEvent) {
    e.preventDefault();
    setErro(null);
    setEnviando(true);
    try {
      await entrar(email.trim(), senha);
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex.message : "Não foi possível entrar.");
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
            {erro && <Aviso tom="erro">{erro}</Aviso>}

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

            <button className="botao" type="submit" disabled={enviando}>
              {enviando ? "Entrando…" : "Entrar"}
            </button>
          </form>
        </div>
        <p className="legenda">Sem acesso? Peça ao coordenador da obra.</p>
      </div>
    </div>
  );
}
