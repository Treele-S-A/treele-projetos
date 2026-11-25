/** Atas de mudança de projeto (TREELE, 25/11/2026), no módulo Qualidade.
 *
 *  Não são as atas de análise crítica: registram uma alteração técnica
 *  adotada. O coordenador sobe o PDF com qualquer nome, diz a disciplina, e o
 *  sistema dá o nome na ordem em que chegam (SER-HID-AMP01-R00). Cada ata
 *  aceita revisões e pode ser excluída. Ver backend/app/api/atas_mudanca.py. */

import { useEffect, useMemo, useState } from "react";
import { api, ErroApi, formatarData } from "../api";
import { Aviso, Carregando, Vazio } from "../componentes";

interface ObraAtas {
  id: number;
  codigo: string;
  nome: string;
  atas: number;
}

interface RevisaoAta {
  id: number;
  numero: number;
  codigo: string;
  nome_original: string;
  tamanho: number;
  enviada_em: string;
  enviada_por: string | null;
}

interface AtaMudanca {
  id: number;
  obra_id: number;
  disciplina: string;
  disciplina_nome: string;
  numero: number;
  codigo: string;
  assunto: string | null;
  criada_em: string;
  revisoes: RevisaoAta[];
}

interface Disciplina {
  id: number;
  codigo: string;
  nome: string;
  ordem: number;
  ativa: boolean;
}

type Envio = { envio_id: number; url: string; metodo: string; headers: Record<string, string> };

const dois = (n: number) => String(n).padStart(2, "0");

function mensagem(e: unknown, padrao: string) {
  return e instanceof ErroApi || e instanceof Error ? e.message : padrao;
}

/** Sobe um PDF: cria o envio, manda direto para o armazenamento e confirma. */
async function subir(obraId: number, arquivo: File, corpo: { disciplina_id?: number; ata_id?: number; assunto?: string }) {
  const envio = await api.post<Envio>(`/obras/${obraId}/atas-mudanca/envios`, {
    nome_arquivo: arquivo.name,
    tamanho: arquivo.size,
    ...corpo,
  });
  const r = await fetch(envio.url, { method: envio.metodo, headers: envio.headers, body: arquivo });
  if (!r.ok) throw new Error("O arquivo não subiu. Tente de novo.");
  return api.post<AtaMudanca>(`/atas-mudanca/envios/${envio.envio_id}/confirmar`);
}

/** Abre o PDF numa aba nova (a aba abre no clique, para o navegador não
 *  bloquear), ou baixa com o nome do sistema. */
function abrirPdf(rev: RevisaoAta, baixar: boolean, aoErro: (m: string) => void) {
  const aba = baixar ? null : window.open("", "_blank");
  if (!baixar && !aba) {
    aoErro("O navegador bloqueou a nova aba. Permita pop-ups deste site e tente de novo.");
    return;
  }
  if (aba) {
    aba.opener = null;
    aba.document.title = `${rev.codigo}.pdf`;
    aba.document.body.textContent = "Abrindo o PDF…";
  }
  api
    .get<{ url: string; nome: string }>(`/atas-mudanca/revisoes/${rev.id}/visualizar${baixar ? "?baixar=true" : ""}`)
    .then((r) => {
      if (aba) aba.location.href = r.url;
      else {
        const a = document.createElement("a");
        a.href = r.url;
        a.download = r.nome;
        a.click();
      }
    })
    .catch((e) => {
      aba?.close();
      aoErro(mensagem(e, "Não foi possível abrir a ata."));
    });
}

export default function AtasMudanca() {
  const [obras, setObras] = useState<ObraAtas[] | null>(null);
  const [disciplinas, setDisciplinas] = useState<Disciplina[]>([]);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<ObraAtas[]>("/atas-mudanca/obras")
      .then(setObras)
      .catch((e) => {
        setErro(mensagem(e, "Não foi possível carregar as obras."));
        setObras([]);
      });
    api
      .get<Disciplina[]>("/disciplinas")
      .then((d) => setDisciplinas(d.filter((x) => x.ativa).sort((a, b) => a.ordem - b.ordem || a.codigo.localeCompare(b.codigo))))
      .catch(() => setDisciplinas([]));
  }, []);

  return (
    <>
      <div className="cabecalho-area">
        <div>
          <span className="rotulo">Qualidade</span>
          <h1>Atas de mudança de projeto</h1>
        </div>
      </div>
      {erro && <Aviso tom="erro">{erro}</Aviso>}
      {obras === null ? (
        <Carregando texto="Buscando as obras" />
      ) : obras.length === 0 ? (
        <Vazio titulo="Nenhuma obra para mostrar">As atas de mudança ficam com os coordenadores de cada obra.</Vazio>
      ) : (
        obras.map((o) => (
          <ObraComAtas
            key={o.id}
            obra={o}
            disciplinas={disciplinas}
            abertaDeInicio={obras.length === 1}
            aoContar={(n) => setObras((l) => l?.map((x) => (x.id === o.id ? { ...x, atas: n } : x)) ?? l)}
          />
        ))
      )}
    </>
  );
}

function ObraComAtas({
  obra,
  disciplinas,
  abertaDeInicio,
  aoContar,
}: {
  obra: ObraAtas;
  disciplinas: Disciplina[];
  abertaDeInicio: boolean;
  aoContar: (n: number) => void;
}) {
  const [aberta, setAberta] = useState(abertaDeInicio);
  const [atas, setAtas] = useState<AtaMudanca[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  // Janela de envio: ata nova (sem ata) ou revisão de uma ata.
  const [enviando, setEnviando] = useState<{ ata: AtaMudanca | null } | null>(null);

  async function carregar() {
    try {
      const lista = await api.get<AtaMudanca[]>(`/obras/${obra.id}/atas-mudanca`);
      setAtas(lista);
      aoContar(lista.length);
    } catch (e) {
      setErro(mensagem(e, "Não foi possível carregar as atas."));
      setAtas([]);
    }
  }

  useEffect(() => {
    if ((aberta || enviando) && atas === null) void carregar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aberta, enviando]);

  const porDisciplina = useMemo(() => {
    const grupos: { codigo: string; nome: string; atas: AtaMudanca[] }[] = [];
    for (const a of atas ?? []) {
      const g = grupos.find((x) => x.codigo === a.disciplina);
      if (g) g.atas.push(a);
      else grupos.push({ codigo: a.disciplina, nome: a.disciplina_nome, atas: [a] });
    }
    return grupos;
  }, [atas]);

  async function excluirRevisao(a: AtaMudanca, r: RevisaoAta) {
    const unica = a.revisoes.length === 1;
    const texto = unica
      ? `Excluir ${r.codigo} de vez? É a única revisão: a ata ${a.codigo} sai da lista.`
      : `Excluir ${r.codigo} de vez?`;
    if (!window.confirm(`${texto}\n\nO PDF é apagado e não dá para desfazer.`)) return;
    try {
      await api.delete(`/atas-mudanca/revisoes/${r.id}`);
      await carregar();
    } catch (e) {
      setErro(mensagem(e, "Não foi possível excluir."));
    }
  }

  async function editarAssunto(a: AtaMudanca) {
    const novo = window.prompt(`Assunto de ${a.codigo}`, a.assunto ?? "");
    if (novo === null) return;
    try {
      await api.patch(`/atas-mudanca/${a.id}`, { assunto: novo.trim() || null });
      await carregar();
    } catch (e) {
      setErro(mensagem(e, "Não foi possível mudar o assunto."));
    }
  }

  async function excluirAta(a: AtaMudanca) {
    const n = a.revisoes.length;
    if (!window.confirm(`Excluir a ata ${a.codigo} inteira${n > 1 ? `, com as ${n} revisões` : ""}?\n\nOs PDFs são apagados e não dá para desfazer.`))
      return;
    try {
      await api.delete(`/atas-mudanca/${a.id}`);
      await carregar();
    } catch (e) {
      setErro(mensagem(e, "Não foi possível excluir."));
    }
  }

  return (
    <div className="folha obra-amp">
      <div className="folha-titulo">
        <button className="titulo-obra-amp" onClick={() => setAberta((x) => !x)} aria-expanded={aberta}>
          <span aria-hidden="true">{aberta ? "▾" : "▸"}</span>
          <strong>
            <span className="mono">{obra.codigo}</span> · {obra.nome}
          </strong>
          <span className="silencioso" style={{ fontSize: 12.5 }}>
            {obra.atas === 0 ? "nenhuma ata" : `${obra.atas} ata${obra.atas > 1 ? "s" : ""}`}
          </span>
        </button>
        <button className="botao pequeno" onClick={() => setEnviando({ ata: null })}>
          Enviar atas
        </button>
      </div>
      {aberta && (
        <div className="folha-corpo">
          {erro && <Aviso tom="erro">{erro}</Aviso>}
          {atas === null ? (
            <Carregando texto="Buscando as atas" />
          ) : atas.length === 0 ? (
            <p className="silencioso" style={{ margin: 0 }}>
              Nenhuma ata de mudança nesta obra ainda.
            </p>
          ) : (
            porDisciplina.map((g) => (
              <section key={g.codigo} className="disciplina-amp">
                <h3>
                  <span className="mono">{g.codigo}</span> · {g.nome}
                </h3>
                <div className="tabela-rolagem">
                  <table className="tabela">
                    <thead>
                      <tr>
                        <th>Ata</th>
                        <th>Assunto</th>
                        <th>Enviada</th>
                        <th style={{ textAlign: "right" }}>Ações</th>
                      </tr>
                    </thead>
                    <tbody>
                      {g.atas.map((a) => {
                        const atual = a.revisoes[a.revisoes.length - 1];
                        const anteriores = a.revisoes.slice(0, -1).reverse();
                        return (
                          <tr key={a.id}>
                            <td>
                              <button className="link-pequeno mono codigo-amp" onClick={() => abrirPdf(atual, false, setErro)} title="Abrir o PDF">
                                {atual.codigo}
                              </button>
                              {anteriores.length > 0 && (
                                <div className="revisoes-amp">
                                  {anteriores.map((r) => (
                                    <span key={r.id}>
                                      <button className="link-pequeno mono" onClick={() => abrirPdf(r, false, setErro)} title={`Abrir ${r.codigo}`}>
                                        R{dois(r.numero)}
                                      </button>
                                      <button
                                        className="link-pequeno perigo"
                                        onClick={() => excluirRevisao(a, r)}
                                        title={`Excluir ${r.codigo}`}
                                        aria-label={`Excluir ${r.codigo}`}
                                      >
                                        ×
                                      </button>
                                    </span>
                                  ))}
                                </div>
                              )}
                            </td>
                            <td>
                              {a.assunto ?? <span className="silencioso">—</span>}{" "}
                              <button className="link-pequeno" onClick={() => editarAssunto(a)} title="Editar o assunto">
                                editar
                              </button>
                              <div className="silencioso" style={{ fontSize: 11.5 }} title="Nome do arquivo enviado">
                                {atual.nome_original}
                              </div>
                            </td>
                            <td className="silencioso" style={{ fontSize: 12.5, whiteSpace: "nowrap" }}>
                              {formatarData(atual.enviada_em)}
                              {atual.enviada_por && <div>{atual.enviada_por}</div>}
                            </td>
                            <td>
                              <div className="linha acoes-amp">
                                <button className="botao secundario pequeno" onClick={() => abrirPdf(atual, true, setErro)}>
                                  Baixar
                                </button>
                                <button className="botao secundario pequeno" onClick={() => setEnviando({ ata: a })}>
                                  Nova revisão
                                </button>
                                {a.revisoes.length > 1 && (
                                  <button className="botao secundario pequeno" onClick={() => excluirRevisao(a, atual)}>
                                    Excluir R{dois(atual.numero)}
                                  </button>
                                )}
                                <button className="botao secundario pequeno perigo" onClick={() => excluirAta(a)}>
                                  Excluir ata
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </section>
            ))
          )}
        </div>
      )}
      {enviando && (
        <JanelaEnvio
          obra={obra}
          ata={enviando.ata}
          atas={atas}
          disciplinas={disciplinas}
          aoFechar={async (mudou) => {
            setEnviando(null);
            if (mudou) {
              setAberta(true);
              await carregar();
            }
          }}
        />
      )}
    </div>
  );
}

function JanelaEnvio({
  obra,
  ata,
  atas,
  disciplinas,
  aoFechar,
}: {
  obra: ObraAtas;
  /** Revisão desta ata; sem ela, atas novas. */
  ata: AtaMudanca | null;
  atas: AtaMudanca[] | null;
  disciplinas: Disciplina[];
  aoFechar: (mudou: boolean) => void;
}) {
  const [arquivos, setArquivos] = useState<File[]>([]);
  const [disciplinaId, setDisciplinaId] = useState<number | "">("");
  const [assunto, setAssunto] = useState("");
  const [andamento, setAndamento] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [feitos, setFeitos] = useState<string[]>([]);

  const disciplina = disciplinas.find((d) => d.id === disciplinaId);
  // O nome que cada arquivo vai ganhar, na ordem da lista (o servidor numera
  // de verdade ao confirmar; isto é a prévia).
  const nomes = useMemo(() => {
    if (ata) {
      const proxima = (ata.revisoes[ata.revisoes.length - 1]?.numero ?? -1) + 1;
      return arquivos.slice(0, 1).map(() => `${ata.codigo}-R${dois(proxima)}`);
    }
    if (!disciplina || atas === null) return [];
    const ultima = Math.max(0, ...atas.filter((a) => a.disciplina === disciplina.codigo).map((a) => a.numero));
    return arquivos.map((_, i) => `${obra.codigo}-${disciplina.codigo}-AMP${dois(ultima + i + 1)}-R00`);
  }, [ata, atas, arquivos, disciplina, obra.codigo]);

  function escolher(lista: FileList | null) {
    const todos = [...(lista ?? [])];
    const fora = todos.filter((f) => !f.name.toLowerCase().endsWith(".pdf"));
    setErro(fora.length ? `Só PDF: ${fora.map((f) => f.name).join(", ")} ficou de fora.` : null);
    const pdfs = todos.filter((f) => f.name.toLowerCase().endsWith(".pdf"));
    setArquivos(ata ? pdfs.slice(0, 1) : pdfs);
  }

  async function enviar() {
    if (!arquivos.length) return setErro("Escolha o PDF da ata.");
    if (!ata && !disciplina) return setErro("Escolha a disciplina.");
    setErro(null);
    const prontos = [...feitos];
    try {
      for (const [i, f] of arquivos.entries()) {
        if (i < prontos.length) continue;
        setAndamento(`Enviando ${i + 1} de ${arquivos.length}: ${f.name}`);
        const salva = await subir(
          obra.id,
          f,
          ata ? { ata_id: ata.id } : { disciplina_id: disciplina!.id, assunto: arquivos.length === 1 ? assunto.trim() || undefined : undefined },
        );
        prontos.push(`${f.name} → ${salva.revisoes[salva.revisoes.length - 1].codigo}`);
        setFeitos([...prontos]);
      }
      setAndamento(null);
    } catch (e) {
      setAndamento(null);
      setErro(`${mensagem(e, "O envio falhou.")}${prontos.length ? ` (${prontos.length} já enviada${prontos.length > 1 ? "s" : ""})` : ""}`);
    }
  }

  const concluido = feitos.length > 0 && feitos.length === arquivos.length && !andamento;

  return (
    <div className="fundo-modal" onMouseDown={(e) => e.target === e.currentTarget && !andamento && aoFechar(feitos.length > 0)}>
      <div className="modal-ata modal-amp" role="dialog" aria-modal="true" aria-labelledby="titulo-envio-amp">
        <header className="modal-ata-topo">
          <div>
            <span className="rotulo">
              {obra.codigo} · {obra.nome}
            </span>
            <h2 id="titulo-envio-amp" className="titulo-secao" style={{ margin: "2px 0 0" }}>
              {ata ? `Nova revisão de ${ata.codigo}` : "Enviar atas de mudança de projeto"}
            </h2>
          </div>
          <button className="botao secundario pequeno" onClick={() => aoFechar(feitos.length > 0)} disabled={!!andamento}>
            Fechar
          </button>
        </header>
        <div className="modal-ata-corpo">
          {concluido ? (
            <>
              <Aviso tom="ok" titulo={feitos.length > 1 ? `${feitos.length} atas enviadas` : "Ata enviada"}>
                <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                  {feitos.map((f) => (
                    <li key={f} className="mono" style={{ fontSize: 12.5 }}>
                      {f}
                    </li>
                  ))}
                </ul>
              </Aviso>
            </>
          ) : (
            <>
              <label className="campo" style={{ display: "block", marginTop: 12 }}>
                <span className="rotulo">{ata ? "PDF da revisão" : "PDFs das atas (com qualquer nome)"}</span>
                <input
                  type="file"
                  accept="application/pdf,.pdf"
                  multiple={!ata}
                  disabled={!!andamento}
                  onChange={(e) => {
                    setFeitos([]);
                    escolher(e.target.files);
                  }}
                />
              </label>
              {!ata && (
                <label className="campo" style={{ display: "block", marginTop: 10 }}>
                  <span className="rotulo">Disciplina</span>
                  <select
                    value={disciplinaId}
                    disabled={!!andamento}
                    onChange={(e) => setDisciplinaId(e.target.value ? Number(e.target.value) : "")}
                  >
                    <option value="">Escolha…</option>
                    {disciplinas.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.codigo} · {d.nome}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {!ata && arquivos.length <= 1 && (
                <label className="campo" style={{ display: "block", marginTop: 10 }}>
                  <span className="rotulo">Assunto (opcional)</span>
                  <input
                    value={assunto}
                    maxLength={300}
                    disabled={!!andamento}
                    onChange={(e) => setAssunto(e.target.value)}
                    placeholder="Ex.: troca da tubulação de PEX por PPR no térreo"
                  />
                </label>
              )}
              {nomes.length > 0 && (
                <div className="previa-amp">
                  <span className="rotulo">Vai ficar assim</span>
                  <ul>
                    {arquivos.slice(0, nomes.length).map((f, i) => (
                      <li key={`${f.name}-${i}`}>
                        <span className="silencioso">{f.name}</span> → <span className="mono">{nomes[i]}</span>
                        {feitos[i] && <span className="silencioso"> · enviada</span>}
                      </li>
                    ))}
                  </ul>
                  {arquivos.length > 1 && (
                    <p className="silencioso" style={{ fontSize: 12, margin: "4px 0 0" }}>
                      A numeração segue a ordem da lista. Com várias de uma vez, o assunto fica em branco: preencha
                      depois, na lista.
                    </p>
                  )}
                </div>
              )}
            </>
          )}
          {andamento && <p className="silencioso" style={{ fontSize: 12.5 }}>{andamento}</p>}
          {erro && <Aviso tom="erro">{erro}</Aviso>}
        </div>
        <footer className="modal-ata-rodape">
          <div className="linha" style={{ gap: 8 }}>
            {concluido ? (
              <button className="botao" onClick={() => aoFechar(true)}>
                Concluir
              </button>
            ) : (
              <button className="botao" disabled={!!andamento || !arquivos.length} onClick={enviar}>
                {andamento ? "Enviando…" : arquivos.length > 1 ? `Enviar ${arquivos.length} atas` : "Enviar"}
              </button>
            )}
          </div>
        </footer>
      </div>
    </div>
  );
}
