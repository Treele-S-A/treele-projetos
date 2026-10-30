import { useEffect, useState, type FormEvent } from "react";
import { api, ErroApi, gravarToken, type Usuario } from "../api";
import { Aviso } from "../componentes";
import { useSessao } from "../sessao";
import { useTema } from "../tema";

export default function Conta() {
  const { usuario, recarregarUsuario } = useSessao();
  const [tema, mudarTema] = useTema();
  const [nome, setNome] = useState(usuario?.nome ?? "");
  const [email, setEmail] = useState(usuario?.email ?? "");
  const [senhaEmail, setSenhaEmail] = useState("");
  const [erroPerfil, setErroPerfil] = useState<string | null>(null);
  const [perfilSalvo, setPerfilSalvo] = useState(false);
  const [salvandoPerfil, setSalvandoPerfil] = useState(false);
  const [atual, setAtual] = useState("");
  const [nova, setNova] = useState("");
  const [repetida, setRepetida] = useState("");
  const [erro, setErro] = useState<ErroApi | string | null>(null);
  const [ok, setOk] = useState(false);
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    setNome(usuario?.nome ?? "");
    setEmail(usuario?.email ?? "");
  }, [usuario?.nome, usuario?.email]);

  async function salvarPerfil(e: FormEvent) {
    e.preventDefault();
    setErroPerfil(null);
    setPerfilSalvo(false);
    setSalvandoPerfil(true);
    try {
      await api.patch<Usuario>("/auth/perfil", {
        nome: nome.trim(), email: email.trim(), senha_atual: senhaEmail || null,
      });
      await recarregarUsuario();
      setSenhaEmail("");
      setPerfilSalvo(true);
    } catch (ex) {
      setErroPerfil(ex instanceof ErroApi ? ex.message : "Não foi possível salvar o perfil.");
    } finally {
      setSalvandoPerfil(false);
    }
  }

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
      // A troca derruba todas as sessões; esta segue com a nova que volta.
      const r = await api.post<{ token: string }>("/auth/senha", {
        senha_atual: atual,
        senha_nova: nova,
      });
      gravarToken(r.token);
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
        <div className="folha-titulo"><strong>Dados da conta</strong></div>
        <form className="folha-corpo conta-formulario" onSubmit={salvarPerfil}>
          {erroPerfil && <Aviso tom="erro">{erroPerfil}</Aviso>}
          {perfilSalvo && <Aviso tom="ok">Dados atualizados.</Aviso>}
          <div className="filtros">
            <label className="campo"><span className="rotulo">Nome</span>
              <input value={nome} onChange={(e) => setNome(e.target.value)} minLength={2} maxLength={160} autoComplete="name" required />
            </label>
            <label className="campo"><span className="rotulo">E-mail de acesso</span>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required />
            </label>
          </div>
          {email.trim().toLowerCase() !== usuario?.email && <>
            <label className="campo conta-senha-email"><span className="rotulo">Senha atual para confirmar a troca de e-mail</span>
              <input type="password" value={senhaEmail} onChange={(e) => setSenhaEmail(e.target.value)} autoComplete="current-password" required />
            </label>
            <p className="silencioso conta-ajuda">Se você entra com Microsoft, peça à TI para atualizar o e-mail no Entra ID. Alterá-lo apenas aqui interromperia o acesso à conta atual.</p>
          </>}
          <button className="botao" disabled={salvandoPerfil || (nome.trim() === usuario?.nome && email.trim().toLowerCase() === usuario?.email)}>
            {salvandoPerfil ? "Salvando…" : "Salvar dados"}
          </button>
        </form>
      </div>

      <div className="folha">
        <div className="folha-titulo"><strong>Aparência</strong></div>
        <div className="folha-corpo">
          <p className="silencioso conta-ajuda">Escolha o tema deste navegador.</p>
          <div className="conta-temas" role="group" aria-label="Tema do sistema">
            <button type="button" className={tema === "claro" ? "ativo" : ""} aria-pressed={tema === "claro"} onClick={() => mudarTema("claro")}>☀ Tema claro</button>
            <button type="button" className={tema === "escuro" ? "ativo" : ""} aria-pressed={tema === "escuro"} onClick={() => mudarTema("escuro")}>☾ Tema escuro</button>
          </div>
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
          {ok && <Aviso tom="ok">
              Senha trocada. Os outros computadores e celulares em que você estava conectado
              precisam entrar de novo.
            </Aviso>}

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
