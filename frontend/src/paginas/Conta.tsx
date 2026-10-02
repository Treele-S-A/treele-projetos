import { useState, type FormEvent } from "react";
import { api, ErroApi } from "../api";
import { Aviso } from "../componentes";
import { useSessao } from "../sessao";

export default function Conta() {
  const { usuario } = useSessao();
  const [atual, setAtual] = useState("");
  const [nova, setNova] = useState("");
  const [repetida, setRepetida] = useState("");
  const [erro, setErro] = useState<ErroApi | string | null>(null);
  const [ok, setOk] = useState(false);
  const [salvando, setSalvando] = useState(false);

  async function trocar(e: FormEvent) {
    e.preventDefault();
    setErro(null);
    setOk(false);
    // Conferido aqui porque a API só recebe a nova uma vez: um erro de
    // digitação viraria uma senha que nem a própria pessoa sabe.
    if (nova !== repetida) {
      setErro("A nova senha e a repetição não são iguais.");
      return;
    }
    if (nova === atual) {
      setErro("A nova senha precisa ser diferente da atual.");
      return;
    }
    setSalvando(true);
    try {
      await api.post("/auth/senha", { senha_atual: atual, senha_nova: nova });
      setOk(true);
      setAtual("");
      setNova("");
      setRepetida("");
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex : "Não foi possível trocar a senha.");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <div className="cabecalho-area">
        <div>
          <span className="rotulo">{usuario?.email}</span>
          <h1>Minha conta</h1>
        </div>
      </div>

      <div className="folha">
        <div className="folha-titulo">
          <strong>Trocar senha</strong>
        </div>
        <form className="folha-corpo" onSubmit={trocar}>
          {typeof erro === "string" && <Aviso tom="erro">{erro}</Aviso>}
          {erro instanceof ErroApi && (
            <Aviso tom="erro" titulo={erro.message} itens={erro.erros} />
          )}
          {ok && <Aviso tom="ok">Senha trocada. Use a nova no próximo acesso.</Aviso>}

          <div className="filtros">
            <label className="campo">
              <span className="rotulo">Senha atual</span>
              <input
                type="password"
                value={atual}
                onChange={(e) => setAtual(e.target.value)}
                autoComplete="current-password"
                required
              />
            </label>
            <label className="campo">
              <span className="rotulo">Nova senha</span>
              <input
                type="password"
                value={nova}
                onChange={(e) => setNova(e.target.value)}
                autoComplete="new-password"
                minLength={8}
                maxLength={128}
                required
              />
            </label>
            <label className="campo">
              <span className="rotulo">Repita a nova senha</span>
              <input
                type="password"
                value={repetida}
                onChange={(e) => setRepetida(e.target.value)}
                autoComplete="new-password"
                minLength={8}
                maxLength={128}
                required
              />
            </label>
          </div>

          <p className="silencioso" style={{ margin: "10px 0 0", fontSize: 13 }}>
            Pelo menos 8 caracteres.
          </p>

          <div style={{ marginTop: 14 }}>
            <button className="botao" disabled={salvando}>
              {salvando ? "Trocando…" : "Trocar senha"}
            </button>
          </div>
        </form>
      </div>

      {usuario?.admin && <TesteEmail />}
    </>
  );
}

/** Confere a configuração do e-mail mandando um para o próprio administrador —
 *  sem gerar aviso falso para a equipe. */
function TesteEmail() {
  const [resultado, setResultado] = useState<{
    enviado: boolean;
    para: string;
    remetente: string;
    erro: string | null;
  } | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function testar() {
    setErro(null);
    setResultado(null);
    setEnviando(true);
    try {
      setResultado(await api.post("/notificacoes/email-teste"));
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex.message : "Não foi possível testar o e-mail.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="folha">
      <div className="folha-titulo">
        <strong>E-mail das notificações</strong>
      </div>
      <div className="folha-corpo">
        {erro && <Aviso tom="erro">{erro}</Aviso>}
        {resultado?.enviado && (
          <Aviso tom="ok">
            Enviado de {resultado.remetente} para {resultado.para}. Se não chegar em alguns
            minutos, olhe o spam: é sinal de que falta registro no DNS.
          </Aviso>
        )}
        {resultado && !resultado.enviado && (
          <Aviso tom="erro" titulo="O e-mail não saiu.">
            <div style={{ marginTop: 4 }}>{resultado.erro}</div>
          </Aviso>
        )}
        <p className="silencioso" style={{ margin: "0 0 12px", fontSize: 13 }}>
          Manda um e-mail de teste para você, com a configuração atual do servidor.
        </p>
        <button className="botao secundario" onClick={testar} disabled={enviando}>
          {enviando ? "Enviando…" : "Enviar e-mail de teste"}
        </button>
      </div>
    </div>
  );
}
