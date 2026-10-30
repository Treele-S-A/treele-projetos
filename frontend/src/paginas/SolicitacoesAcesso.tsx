/** Solicitações de acesso de quem é de fora da Treèle (TREELE, 30/10/2026),
 *  para o administrador: os dados vêm preenchidos pela pessoa, a função pode
 *  ser ajustada (comercial, ou projetista com as obras e disciplinas), e aí
 *  aprovar ou reprovar. Aprovado, o projetista entra só no que foi aprovado. */

import { useEffect, useState } from "react";
import { api, ErroApi, formatarData } from "../api";
import { Aviso, Carregando, Vazio } from "../componentes";

interface Solicitacao {
  id: number;
  nome: string;
  email: string;
  empresa: string | null;
  funcao: "projetista" | "comercial";
  obras: { id: number; codigo: string; nome: string }[];
  disciplinas: string[];
  status: "pendente" | "aprovada" | "reprovada";
  motivo: string | null;
  criada_em: string;
  decidida_em: string | null;
  decidida_por: string | null;
}

interface Opcoes {
  obras: { id: number; codigo: string; nome: string }[];
  disciplinas: { codigo: string; nome: string }[];
}

type Filtro = "pendente" | "aprovada" | "reprovada" | "";

export default function SolicitacoesAcesso() {
  const [lista, setLista] = useState<Solicitacao[] | null>(null);
  const [opcoes, setOpcoes] = useState<Opcoes | null>(null);
  const [filtro, setFiltro] = useState<Filtro>("pendente");
  const [erro, setErro] = useState<string | null>(null);

  async function carregar() {
    try {
      const [l, o] = await Promise.all([
        api.get<Solicitacao[]>(`/acesso/solicitacoes${filtro ? `?situacao=${filtro}` : ""}`),
        api.get<Opcoes>("/acesso/opcoes"),
      ]);
      setLista(l);
      setOpcoes(o);
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex.message : "Não foi possível carregar as solicitações.");
    }
  }
  useEffect(() => {
    setLista(null);
    void carregar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtro]);

  return (
    <>
      <div className="cabecalho-area">
        <div>
          <span className="rotulo">Configurações</span>
          <h1>Solicitações de acesso</h1>
        </div>
      </div>
      <div className="folha">
        <div className="folha-corpo">
          <div className="seletor-visao" role="group" aria-label="Situação">
            {([["pendente", "Aguardando"], ["aprovada", "Aprovadas"], ["reprovada", "Reprovadas"], ["", "Todas"]] as const).map(
              ([v, r]) => (
                <button key={v} className={filtro === v ? "ativo" : ""} onClick={() => setFiltro(v)}>
                  {r}
                </button>
              ),
            )}
          </div>
        </div>
        {erro && <div className="folha-corpo"><Aviso tom="erro">{erro}</Aviso></div>}
        {lista === null && !erro && <Carregando texto="Buscando as solicitações" />}
        {lista && lista.length === 0 && (
          <Vazio titulo={filtro === "pendente" ? "Nenhuma solicitação aguardando" : "Nada aqui"}>
            Quem é de fora do domínio @treele pede acesso pela tela de entrada.
          </Vazio>
        )}
      </div>
      {lista && opcoes && lista.map((s) => <CartaoSolicitacao key={s.id} s={s} opcoes={opcoes} aoDecidir={carregar} />)}
    </>
  );
}

function CartaoSolicitacao({ s, opcoes, aoDecidir }: { s: Solicitacao; opcoes: Opcoes; aoDecidir: () => Promise<void> }) {
  const [funcao, setFuncao] = useState(s.funcao);
  const [obras, setObras] = useState(s.obras.map((o) => o.id));
  const [disciplinas, setDisciplinas] = useState(s.disciplinas);
  const [reprovando, setReprovando] = useState(false);
  const [motivo, setMotivo] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const pendente = s.status === "pendente";
  const alterna = <T,>(lista: T[], v: T) => (lista.includes(v) ? lista.filter((x) => x !== v) : [...lista, v]);
  const valido = funcao === "comercial" || (obras.length > 0 && disciplinas.length > 0);

  async function decidir(qual: "aprovar" | "reprovar") {
    setOcupado(true);
    setErro(null);
    try {
      if (qual === "aprovar") {
        await api.post(`/acesso/solicitacoes/${s.id}/aprovar`, { funcao, obras, disciplinas });
      } else {
        await api.post(`/acesso/solicitacoes/${s.id}/reprovar`, { motivo: motivo.trim() || null });
      }
      await aoDecidir();
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex : new ErroApi(0, "Não foi possível registrar a decisão."));
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="folha cartao-solicitacao-acesso">
      <div className="folha-titulo">
        <strong>{s.nome}</strong>
        <span className={`selo-fornecedor ${s.status === "aprovada" ? "qualificado" : s.status === "reprovada" ? "desqualificado" : "pendente"}`}>
          {s.status === "pendente" ? "Aguardando" : s.status === "aprovada" ? "Aprovada" : "Reprovada"}
        </span>
      </div>
      <div className="folha-corpo">
        {erro && <Aviso tom="erro" titulo={erro.message} itens={erro.erros} />}
        <dl className="dados-solicitacao">
          <div><dt>E-mail</dt><dd className="mono">{s.email}</dd></div>
          {s.empresa && <div><dt>Empresa</dt><dd>{s.empresa}</dd></div>}
          <div><dt>Pedido em</dt><dd>{formatarData(s.criada_em)}</dd></div>
          {!pendente && (
            <div><dt>Decidido</dt><dd>{s.decidida_em ? formatarData(s.decidida_em) : "—"}{s.decidida_por && ` por ${s.decidida_por}`}</dd></div>
          )}
        </dl>

        {pendente ? (
          <>
            <fieldset className="perfis">
              <legend className="rotulo">Função (pode ajustar)</legend>
              {(["projetista", "comercial"] as const).map((f) => (
                <label key={f} className="perfil-opcao">
                  <input type="radio" name={`funcao-${s.id}`} checked={funcao === f} onChange={() => setFuncao(f)} />
                  <span>
                    <strong>{f === "projetista" ? "Projetista" : "Comercial"}</strong>
                    <span className="silencioso">
                      {f === "projetista"
                        ? "Envia e consulta só nas obras e disciplinas marcadas abaixo."
                        : "Todas as obras, só o material comercial (COM) liberado."}
                    </span>
                  </span>
                </label>
              ))}
            </fieldset>
            {funcao === "projetista" && (
              <>
                <fieldset className="perfis">
                  <legend className="rotulo">Obras</legend>
                  <div className="chips-escolha">
                    {opcoes.obras.map((o) => (
                      <button type="button" key={o.id} className={obras.includes(o.id) ? "marcado" : ""}
                        aria-pressed={obras.includes(o.id)} onClick={() => setObras(alterna(obras, o.id))} title={o.nome}>
                        {o.codigo} · {o.nome}
                      </button>
                    ))}
                  </div>
                </fieldset>
                <fieldset className="perfis">
                  <legend className="rotulo">Disciplinas</legend>
                  <div className="chips-escolha">
                    {opcoes.disciplinas.map((d) => (
                      <button type="button" key={d.codigo} className={disciplinas.includes(d.codigo) ? "marcado" : ""}
                        aria-pressed={disciplinas.includes(d.codigo)} onClick={() => setDisciplinas(alterna(disciplinas, d.codigo))}
                        title={d.nome}>
                        {d.codigo}
                      </button>
                    ))}
                  </div>
                </fieldset>
              </>
            )}
            {reprovando ? (
              <div style={{ marginTop: 12 }}>
                <label className="campo" style={{ display: "block" }}>
                  <span className="rotulo">Motivo (opcional, vai no e-mail para a pessoa)</span>
                  <textarea value={motivo} onChange={(e) => setMotivo(e.target.value)} rows={2} maxLength={2000} autoFocus />
                </label>
                <div className="linha" style={{ gap: 8, marginTop: 8 }}>
                  <button className="botao perigo" disabled={ocupado} onClick={() => decidir("reprovar")}>
                    {ocupado ? "Reprovando…" : "Reprovar solicitação"}
                  </button>
                  <button className="botao secundario pequeno" onClick={() => setReprovando(false)} disabled={ocupado}>
                    Voltar
                  </button>
                </div>
              </div>
            ) : (
              <div className="linha" style={{ gap: 8, marginTop: 12 }}>
                <button className="botao" disabled={ocupado || !valido} onClick={() => decidir("aprovar")}
                  title={valido ? undefined : "Projetista: marque ao menos uma obra e uma disciplina"}>
                  {ocupado ? "Aprovando…" : "Aprovar"}
                </button>
                <button className="botao secundario" disabled={ocupado} onClick={() => setReprovando(true)}>
                  Reprovar
                </button>
              </div>
            )}
          </>
        ) : (
          <p style={{ margin: "8px 0 0" }}>
            <strong>{s.funcao === "projetista" ? "Projetista" : "Comercial"}</strong>
            {s.funcao === "projetista" && ` · ${s.obras.map((o) => o.codigo).join(", ")} · ${s.disciplinas.join(", ")}`}
            {s.motivo && <span className="silencioso"> · Motivo: {s.motivo}</span>}
          </p>
        )}
      </div>
    </div>
  );
}
