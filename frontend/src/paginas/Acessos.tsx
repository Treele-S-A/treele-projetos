/** Controle de acessos (TREELE, 10/11/2026): cada vez que alguém entra no
 *  sistema, inclusive quem volta com a sessão de 30 dias ainda aberta. Dos
 *  coordenadores: o administrador vê todo mundo; o coordenador, a equipe das
 *  obras dele (ver api/acessos.py). */

import { useEffect, useState } from "react";
import { api, ErroApi, formatarData } from "../api";
import { Aviso, Carregando, Vazio } from "../componentes";

interface Pessoa {
  id: number;
  nome: string;
  email: string;
  ativo: boolean;
}

interface Dados {
  pessoas: { usuario: Pessoa; ultimo: string | null; no_periodo: number }[];
  itens: { id: number; usuario: Pessoa; quando: string; tipo: string; dispositivo: string | null }[];
  total: number;
  pagina: number;
  por_pagina: number;
}

const TIPO: Record<string, string> = {
  login_senha: "Login com e-mail e senha",
  login_microsoft: "Login com Microsoft",
  retorno: "Voltou com a sessão aberta",
};

const PERIODOS: [string, string][] = [
  ["1", "Hoje e ontem"],
  ["7", "Últimos 7 dias"],
  ["30", "Últimos 30 dias"],
  ["90", "Últimos 90 dias"],
  ["3650", "Todo o período"],
];

export default function Acessos() {
  const [dados, setDados] = useState<Dados | null>(null);
  const [pessoa, setPessoa] = useState("");
  const [dias, setDias] = useState("30");
  const [pagina, setPagina] = useState(1);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    const p = new URLSearchParams({ dias, pagina: String(pagina), por_pagina: "50" });
    if (pessoa) p.set("usuario_id", pessoa);
    setCarregando(true);
    setErro(null);
    let vivo = true;
    api
      .get<Dados>(`/acessos?${p}`)
      .then((d) => vivo && setDados(d))
      .catch((ex) => vivo && setErro(ex instanceof ErroApi ? ex.message : "Não foi possível carregar os acessos."))
      .finally(() => vivo && setCarregando(false));
    return () => {
      vivo = false;
    };
  }, [pessoa, dias, pagina]);

  const totalPaginas = dados ? Math.max(1, Math.ceil(dados.total / dados.por_pagina)) : 1;
  const nomePeriodo = PERIODOS.find(([v]) => v === dias)?.[1].toLowerCase() ?? "";
  const escolher = (id: string) => {
    setPessoa(id);
    setPagina(1);
  };

  return (
    <>
      <div className="cabecalho-area">
        <div>
          <span className="rotulo">Configurações</span>
          <h1>Controle de acessos</h1>
        </div>
      </div>

      {erro && <Aviso tom="erro">{erro}</Aviso>}

      <Aviso tom="info">
        Cada vez que alguém entra no sistema fica registrado: pelo login, com senha ou Microsoft, e também quando a
        pessoa volta com a sessão ainda aberta (o "Manter conectado por 30 dias"). A volta conta uma vez a cada 30
        minutos.
      </Aviso>

      <div className="folha">
        <div className="folha-corpo filtros">
          <label className="campo" style={{ flex: "1 1 260px" }}>
            <span className="rotulo">Pessoa</span>
            <select value={pessoa} onChange={(e) => escolher(e.target.value)}>
              <option value="">Todas</option>
              {(dados?.pessoas ?? [])
                .map((p) => p.usuario)
                .sort((a, b) => a.nome.localeCompare(b.nome))
                .map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.nome} · {u.email}
                  </option>
                ))}
            </select>
          </label>
          <label className="campo">
            <span className="rotulo">Período</span>
            <select
              value={dias}
              onChange={(e) => {
                setDias(e.target.value);
                setPagina(1);
              }}
            >
              {PERIODOS.map(([v, r]) => (
                <option key={v} value={v}>
                  {r}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {carregando && !dados ? (
        <Carregando texto="Buscando os acessos" />
      ) : dados ? (
        <>
          {!pessoa && (
            <div className="folha">
              <div className="folha-titulo">
                <strong>Último acesso de cada pessoa</strong>
                <span className="silencioso" style={{ fontSize: 12 }}>
                  Clique em uma pessoa para ver só os acessos dela
                </span>
              </div>
              <div className="tabela-rolagem">
                <table className="tabela">
                  <thead>
                    <tr>
                      <th>Pessoa</th>
                      <th>E-mail</th>
                      <th>Último acesso</th>
                      <th style={{ textAlign: "right" }}>Acessos ({nomePeriodo})</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dados.pessoas.map((p) => (
                      <tr key={p.usuario.id} className="linha-clicavel" onClick={() => escolher(String(p.usuario.id))}>
                        <td>
                          {p.usuario.nome}
                          {!p.usuario.ativo && <span className="silencioso"> · inativo</span>}
                        </td>
                        <td className="mono silencioso" style={{ fontSize: 12 }}>
                          {p.usuario.email}
                        </td>
                        <td className="mono" style={{ fontSize: 12, whiteSpace: "nowrap" }}>
                          {p.ultimo ? formatarData(p.ultimo) : <span className="silencioso">Nunca entrou</span>}
                        </td>
                        <td className="mono" style={{ textAlign: "right" }}>
                          {p.no_periodo}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div className="folha">
            <div className="folha-titulo">
              <strong>
                {pessoa
                  ? `Acessos de ${dados.pessoas.find((p) => String(p.usuario.id) === pessoa)?.usuario.nome ?? ""}`
                  : "Todos os acessos"}
              </strong>
              {pessoa && (
                <button className="botao secundario pequeno" onClick={() => escolher("")}>
                  Ver todas as pessoas
                </button>
              )}
            </div>
            {dados.itens.length === 0 ? (
              <Vazio titulo="Nenhum acesso neste período" />
            ) : (
              <>
                <div className="tabela-rolagem">
                  <table className="tabela">
                    <thead>
                      <tr>
                        <th>Quando</th>
                        {!pessoa && <th>Pessoa</th>}
                        <th>Como entrou</th>
                        <th>Dispositivo</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dados.itens.map((i) => (
                        <tr key={i.id}>
                          <td className="mono" style={{ fontSize: 12, whiteSpace: "nowrap" }}>
                            {formatarData(i.quando)}
                          </td>
                          {!pessoa && <td>{i.usuario.nome}</td>}
                          <td>{TIPO[i.tipo] ?? i.tipo}</td>
                          <td className="silencioso" style={{ fontSize: 12.5 }}>
                            {i.dispositivo ?? "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="paginacao">
                  <span>
                    {dados.total} acesso{dados.total === 1 ? "" : "s"}
                    {totalPaginas > 1 && ` · página ${dados.pagina} de ${totalPaginas}`}
                  </span>
                  {totalPaginas > 1 && (
                    <div className="linha">
                      <button className="botao secundario pequeno" disabled={pagina <= 1} onClick={() => setPagina((p) => p - 1)}>
                        Anterior
                      </button>
                      <button
                        className="botao secundario pequeno"
                        disabled={pagina >= totalPaginas}
                        onClick={() => setPagina((p) => p + 1)}
                      >
                        Próxima
                      </button>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </>
      ) : null}
    </>
  );
}
