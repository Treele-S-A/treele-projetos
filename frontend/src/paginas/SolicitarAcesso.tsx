/** Pedido de acesso de quem é de fora da Treèle (TREELE, 30/10/2026):
 *  projetista ou comercial externo, sem conta Microsoft @treele. Público —
 *  abre da tela de login. Os administradores recebem o pedido e decidem. */

import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, ErroApi } from "../api";
import { Aviso, SIMBOLO } from "../componentes";

interface Opcoes {
  obras: { id: number; codigo: string; nome: string }[];
  disciplinas: { codigo: string; nome: string }[];
}

export default function SolicitarAcesso() {
  const [opcoes, setOpcoes] = useState<Opcoes | null>(null);
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [empresa, setEmpresa] = useState("");
  const [funcao, setFuncao] = useState<"projetista" | "comercial" | "">("");
  const [obras, setObras] = useState<number[]>([]);
  const [disciplinas, setDisciplinas] = useState<string[]>([]);
  const [senha, setSenha] = useState("");
  const [confirma, setConfirma] = useState("");
  const [site, setSite] = useState(""); // armadilha para robô: escondido
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [enviado, setEnviado] = useState(false);

  useEffect(() => {
    api.get<Opcoes>("/acesso/opcoes").then(setOpcoes).catch(() => setOpcoes({ obras: [], disciplinas: [] }));
  }, []);

  const alterna = <T,>(lista: T[], v: T) => (lista.includes(v) ? lista.filter((x) => x !== v) : [...lista, v]);
  const dominioTreele = email.trim().toLowerCase().endsWith("@treele.com.br");
  const senhasDiferentes = confirma.length > 0 && senha !== confirma;
  const pronto =
    !!funcao && !dominioTreele && senha.length >= 8 && senha === confirma &&
    (funcao === "comercial" || (obras.length > 0 && disciplinas.length > 0));

  async function enviar(e: FormEvent) {
    e.preventDefault();
    if (!pronto) return;
    setErro(null);
    setEnviando(true);
    try {
      await api.post("/acesso/solicitacoes", {
        nome: nome.trim(),
        email: email.trim(),
        empresa: empresa.trim() || null,
        funcao,
        obras: funcao === "projetista" ? obras : [],
        disciplinas: funcao === "projetista" ? disciplinas : [],
        senha,
        site: site || null,
      });
      setEnviado(true);
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex : new ErroApi(0, "Não foi possível enviar a solicitação."));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="tela-entrar">
      <div>
        <div className="cartao-entrar cartao-solicitar">
          <div className="topo">
            <img src={SIMBOLO} alt="" />
            <h1 className="marca-nome">Solicitar acesso</h1>
            <div className="marca-sub">Projetos · Treèle Construtora</div>
          </div>

          {enviado ? (
            <div>
              <Aviso tom="ok" titulo="Solicitação enviada">
                Os administradores da Treèle vão analisar o seu pedido. Você recebe a resposta por e-mail em{" "}
                <strong>{email.trim()}</strong>. Se aprovado, entre com esse e-mail e a senha que você escolheu.
              </Aviso>
              <Link className="botao secundario" to="/">
                Voltar para a entrada
              </Link>
            </div>
          ) : (
            <form onSubmit={enviar}>
              {erro && <Aviso tom="erro" titulo={erro.message} itens={erro.erros} />}
              <label className="campo">
                <span className="rotulo">Nome completo</span>
                <input value={nome} onChange={(e) => setNome(e.target.value)} required minLength={3} maxLength={160} autoFocus />
              </label>
              <label className="campo">
                <span className="rotulo">E-mail</span>
                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required maxLength={190} />
              </label>
              {dominioTreele && (
                <Aviso tom="atencao">
                  E-mail @treele.com.br não precisa pedir acesso: volte e use "Entrar com Microsoft".
                </Aviso>
              )}
              <label className="campo">
                <span className="rotulo">Empresa (opcional)</span>
                <input value={empresa} onChange={(e) => setEmpresa(e.target.value)} maxLength={160} />
              </label>
              {/* Escondido de quem usa a tela: só robô preenche. */}
              <label className="campo-armadilha" aria-hidden="true">
                Site
                <input tabIndex={-1} autoComplete="off" value={site} onChange={(e) => setSite(e.target.value)} />
              </label>

              <fieldset className="perfis">
                <legend className="rotulo">Função</legend>
                <label className="perfil-opcao">
                  <input type="radio" name="funcao" checked={funcao === "projetista"} onChange={() => setFuncao("projetista")} required />
                  <span>
                    <strong>Projetista</strong>
                    <span className="silencioso">Envia e consulta os projetos das obras e disciplinas em que está envolvido.</span>
                  </span>
                </label>
                <label className="perfil-opcao">
                  <input type="radio" name="funcao" checked={funcao === "comercial"} onChange={() => setFuncao("comercial")} />
                  <span>
                    <strong>Comercial</strong>
                    <span className="silencioso">Consulta e baixa o material comercial liberado das obras.</span>
                  </span>
                </label>
              </fieldset>

              {funcao === "projetista" && opcoes && (
                <>
                  <fieldset className="perfis">
                    <legend className="rotulo">Obra(s) em que está envolvido</legend>
                    <div className="chips-escolha">
                      {opcoes.obras.map((o) => (
                        <button type="button" key={o.id} className={obras.includes(o.id) ? "marcado" : ""}
                          aria-pressed={obras.includes(o.id)} onClick={() => setObras(alterna(obras, o.id))}>
                          {o.nome}
                        </button>
                      ))}
                    </div>
                  </fieldset>
                  <fieldset className="perfis">
                    <legend className="rotulo">Disciplina(s)</legend>
                    <div className="chips-escolha">
                      {opcoes.disciplinas.map((d) => (
                        <button type="button" key={d.codigo} className={disciplinas.includes(d.codigo) ? "marcado" : ""}
                          aria-pressed={disciplinas.includes(d.codigo)} onClick={() => setDisciplinas(alterna(disciplinas, d.codigo))}
                          title={d.codigo}>
                          {d.nome}
                        </button>
                      ))}
                    </div>
                  </fieldset>
                </>
              )}

              <label className="campo">
                <span className="rotulo">Crie uma senha (mínimo 8 caracteres)</span>
                <input type="password" value={senha} onChange={(e) => setSenha(e.target.value)} minLength={8}
                  maxLength={128} autoComplete="new-password" required />
              </label>
              <label className="campo">
                <span className="rotulo">Repita a senha</span>
                <input type="password" value={confirma} onChange={(e) => setConfirma(e.target.value)}
                  autoComplete="new-password" required />
              </label>
              {senhasDiferentes && <span className="silencioso" style={{ color: "var(--obsoleto)", fontSize: 12.5 }}>As senhas não são iguais.</span>}

              <button className="botao" type="submit" disabled={!pronto || enviando}>
                {enviando ? "Enviando…" : "Solicitar Acesso"}
              </button>
              <Link className="link-pequeno" to="/" style={{ alignSelf: "center" }}>
                Voltar para a entrada
              </Link>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
