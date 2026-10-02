import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  api,
  ErroApi,
  type NomeAnalisado,
  type Padrao,
} from "../api";
import { Aviso, Carregando } from "../componentes";
import { useSessao } from "../sessao";

type Estado = "pronto" | "invalido" | "enviando" | "concluido" | "erro";

/** Mesmo mínimo do servidor (app/services/titulos.py). */
const TITULO_MIN = 3;
/** Mesmo mínimo do servidor (app/services/titulos.py). */
const DESCRICAO_MIN = 5;

interface Item {
  arquivo: File;
  analise: NomeAnalisado;
  estado: Estado;
  progresso: number;
  mensagem?: string;
  documentoId?: number;
}

interface RespostaIniciar {
  arquivo_id: number;
  revisao_id: number;
  documento_id: number;
  url: string;
  metodo: string;
  headers: Record<string, string>;
  direto: boolean;
}

/** Envia os bytes com XHR — `fetch` não reporta progresso de upload. */
function enviarBytes(
  url: string,
  metodo: string,
  headers: Record<string, string>,
  arquivo: File,
  aoProgredir: (fracao: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(metodo, url);
    Object.entries(headers).forEach(([k, v]) => xhr.setRequestHeader(k, v));
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) aoProgredir(e.loaded / e.total);
    };
    xhr.onload = () =>
      xhr.status >= 200 && xhr.status < 300
        ? resolve()
        : reject(new Error(`O armazenamento recusou o arquivo (HTTP ${xhr.status}).`));
    xhr.onerror = () => reject(new Error("A conexão caiu durante o envio."));
    xhr.send(arquivo);
  });
}

function chaveRevisao(item: Item): string {
  return `${item.analise.codigo_documento}|${item.analise.revisao}`;
}

export default function Enviar() {
  const { obraId } = useParams();
  const { obras } = useSessao();
  const obra = obras.find((o) => o.id === Number(obraId));

  const [padrao, setPadrao] = useState<Padrao | null>(null);
  const [itens, setItens] = useState<Item[]>([]);
  const [analisando, setAnalisando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sobre, setSobre] = useState(false);
  // Um título por documento novo, não por arquivo: PDF e DWG da mesma prancha
  // nova dividem o mesmo campo.
  const [titulos, setTitulos] = useState<Record<string, string>>({});
  // "O que mudou" é por revisão nova, não por arquivo: PDF e DWG da mesma
  // revisão dividem o campo. Chave: "CÓDIGO|REVISÃO".
  const [descricoes, setDescricoes] = useState<Record<string, string>>({});
  const entradaRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api
      .get<Padrao>(`/obras/${obraId}/padrao`)
      .then(setPadrao)
      .catch(() => setPadrao(null));
  }, [obraId]);

  async function analisar(arquivos: File[]) {
    if (arquivos.length === 0) return;
    setErro(null);
    setAnalisando(true);
    try {
      const r = await api.post<{ resultados: NomeAnalisado[] }>(
        `/obras/${obraId}/nomenclatura/validar`,
        { nomes: arquivos.map((a) => a.name) },
      );
      setItens((antigos) => [
        ...antigos,
        ...arquivos.map((arquivo, i) => ({
          arquivo,
          analise: r.resultados[i],
          estado: (r.resultados[i].valido ? "pronto" : "invalido") as Estado,
          progresso: 0,
        })),
      ]);
    } catch (ex) {
      setErro(ex instanceof ErroApi ? ex.message : "Não foi possível conferir os nomes.");
    } finally {
      setAnalisando(false);
    }
  }

  function atualizar(indice: number, mudanca: Partial<Item>) {
    setItens((antigos) => antigos.map((it, i) => (i === indice ? { ...it, ...mudanca } : it)));
  }

  async function enviarTudo() {
    setEnviando(true);
    setErro(null);

    for (let i = 0; i < itens.length; i++) {
      const item = itens[i];
      if (item.estado !== "pronto" && item.estado !== "erro") continue;

      atualizar(i, { estado: "enviando", progresso: 0, mensagem: undefined });
      try {
        const inicio = await api.post<RespostaIniciar>(`/obras/${obraId}/uploads/iniciar`, {
          nome_arquivo: item.arquivo.name,
          tamanho: item.arquivo.size,
          content_type: item.arquivo.type || "application/octet-stream",
          substituir: true,
          titulo: tituloDe(item),
          descricao: descricaoDe(item),
        });

        await enviarBytes(inicio.url, inicio.metodo, inicio.headers, item.arquivo, (f) =>
          atualizar(i, { progresso: f }),
        );

        await api.post(`/arquivos/${inicio.arquivo_id}/confirmar`);
        atualizar(i, {
          estado: "concluido",
          progresso: 1,
          documentoId: inicio.documento_id,
        });
      } catch (ex) {
        // O servidor pediu "o que mudou" que a tela não sabia que faltava
        // (análise feita antes de outra pessoa mexer, ou tela antiga): em vez
        // de só falhar, abre o campo para esta revisão e espera o preenchimento.
        if (
          ex instanceof ErroApi &&
          ex.status === 422 &&
          ex.message.includes("revisão nova") &&
          !item.analise.precisa_descricao
        ) {
          atualizar(i, {
            estado: "pronto",
            analise: { ...item.analise, precisa_descricao: true },
          });
          continue;
        }
        const mensagem =
          ex instanceof ErroApi
            ? [ex.message, ...ex.erros].join(" ")
            : ex instanceof Error
              ? ex.message
              : "Falhou.";
        atualizar(i, { estado: "erro", mensagem });
      }
    }

    setEnviando(false);
  }

  const pendentes = itens.filter((i) => i.estado === "pronto" || i.estado === "erro");
  const prontos = pendentes.length;

  // Documentos desta remessa que o servidor vai exigir título — quem decide é
  // ele (precisa_titulo), com a mesma regra do envio.
  const semTitulo = [
    ...pendentes
      .filter((i) => i.analise.precisa_titulo && i.analise.codigo_documento)
      .reduce((mapa, i) => {
        const codigo = i.analise.codigo_documento as string;
        mapa.set(codigo, [...(mapa.get(codigo) ?? []), i.arquivo.name]);
        return mapa;
      }, new Map<string, string[]>()),
  ];
  const faltam = semTitulo.filter(
    ([codigo]) => (titulos[codigo] ?? "").trim().length < TITULO_MIN,
  ).length;

  // Revisões novas desta remessa: quem sobe o primeiro arquivo diz o que mudou.
  const semDescricao = [
    ...pendentes
      .filter((i) => i.analise.precisa_descricao && i.analise.codigo_documento)
      .reduce((mapa, i) => {
        const chave = chaveRevisao(i);
        mapa.set(chave, [...(mapa.get(chave) ?? []), i.arquivo.name]);
        return mapa;
      }, new Map<string, string[]>()),
  ];
  const faltamDescricoes = semDescricao.filter(
    ([chave]) => (descricoes[chave] ?? "").trim().length < DESCRICAO_MIN,
  ).length;

  function descricaoDe(item: Item): string | undefined {
    if (!item.analise.precisa_descricao) return undefined;
    return descricoes[chaveRevisao(item)]?.trim() || undefined;
  }

  function tituloDe(item: Item): string | undefined {
    const codigo = item.analise.codigo_documento;
    if (!codigo || !item.analise.precisa_titulo) return undefined;
    return titulos[codigo]?.trim() || undefined;
  }
  const invalidos = itens.filter((i) => i.estado === "invalido").length;
  const concluidos = itens.filter((i) => i.estado === "concluido").length;

  if (!obra) return <Carregando />;

  return (
    <>
      <div className="cabecalho-area">
        <div>
          <span className="rotulo">
            {obra.codigo} · {obra.nome}
          </span>
          <h1>Enviar arquivos</h1>
        </div>
        <Link className="botao secundario" to={`/obras/${obra.id}/acervo`}>
          Ver acervo
        </Link>
      </div>

      {erro && <Aviso tom="erro">{erro}</Aviso>}

      {padrao && (
        <Aviso tom="info" titulo="Padrão de nomenclatura desta obra">
          <div className="mono" style={{ marginTop: 4 }}>
            {padrao.template}
          </div>
          {padrao.exemplo && (
            <div style={{ marginTop: 4, fontSize: 12 }}>
              Exemplo: <span className="mono">{padrao.exemplo}</span>
            </div>
          )}
          <div style={{ marginTop: 4, fontSize: 12 }}>
            Formatos aceitos: {padrao.extensoes.map((e) => `.${e}`).join(", ")}. O DWG precisa
            subir com o PDF plotado e o RVT com o IFC exportado para a revisão poder ser liberada.
          </div>
        </Aviso>
      )}

      <div className="folha">
        <div className="folha-corpo">
          <div
            className={`area-solta ${sobre ? "sobre" : ""}`}
            onClick={() => entradaRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setSobre(true);
            }}
            onDragLeave={() => setSobre(false)}
            onDrop={(e) => {
              e.preventDefault();
              setSobre(false);
              analisar(Array.from(e.dataTransfer.files));
            }}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") entradaRef.current?.click();
            }}
          >
            <strong>Solte os arquivos aqui</strong>
            <div className="silencioso" style={{ marginTop: 4, fontSize: 13 }}>
              ou clique para escolher. Os nomes são conferidos antes de qualquer byte subir.
            </div>
            <input
              ref={entradaRef}
              type="file"
              multiple
              hidden
              onChange={(e) => {
                analisar(Array.from(e.target.files ?? []));
                e.target.value = "";
              }}
            />
          </div>

          {analisando && <Carregando texto="Conferindo os nomes" />}

          {itens.length > 0 && (
            <>
              <div className="lista-envio">
                {itens.map((item, i) => (
                  <Linha
                    key={`${item.arquivo.name}-${i}`}
                    item={item}
                    titulo={
                      item.analise.documento_titulo ??
                      titulos[item.analise.codigo_documento ?? ""]?.trim() ??
                      null
                    }
                  />
                ))}
              </div>

              {semTitulo.length > 0 && (
                <div className="titulos-novos">
                  <span className="rotulo">
                    {semTitulo.length === 1
                      ? "Documento novo — dê um título"
                      : `${semTitulo.length} documentos novos — dê um título a cada um`}
                  </span>
                  <p className="silencioso">
                    É por ele que a equipe encontra a prancha na lista e na pasta. Vale para
                    todas as revisões seguintes — na próxima, ninguém precisa digitar de novo.
                  </p>
                  {semTitulo.map(([codigo, arquivos]) => (
                    <label className="campo-titulo" key={codigo}>
                      <span className="codigo">{codigo}</span>
                      <input
                        value={titulos[codigo] ?? ""}
                        onChange={(e) =>
                          setTitulos((t) => ({ ...t, [codigo]: e.target.value }))
                        }
                        placeholder="Ex.: Planta de Forma — Pav. Tipo"
                        maxLength={300}
                        disabled={enviando}
                        aria-label={`Título de ${codigo}`}
                      />
                      <span className="silencioso">
                        {arquivos.length === 1 ? "1 arquivo" : `${arquivos.length} arquivos`}
                      </span>
                    </label>
                  ))}
                </div>
              )}

              {semDescricao.length > 0 && (
                <div className="titulos-novos">
                  <span className="rotulo">
                    {semDescricao.length === 1
                      ? "Revisão nova — conte o que mudou"
                      : `${semDescricao.length} revisões novas — conte o que mudou em cada uma`}
                  </span>
                  <p className="silencioso">
                    É o que a obra lê antes de executar. Só o primeiro arquivo de cada revisão
                    pede isto; os seguintes da mesma revisão aproveitam.
                  </p>
                  {semDescricao.map(([chave, arquivos]) => {
                    const [codigo, revisao] = chave.split("|");
                    return (
                      <label className="campo-titulo campo-descricao" key={chave}>
                        <span className="codigo">
                          {codigo} · R{revisao}
                        </span>
                        <textarea
                          value={descricoes[chave] ?? ""}
                          onChange={(e) =>
                            setDescricoes((d) => ({ ...d, [chave]: e.target.value }))
                          }
                          placeholder={
                            Number(revisao) === 0 || revisao === "A"
                              ? "Ex.: Emissão inicial."
                              : "Ex.: Ajuste de armadura da viga V12 e revisão das cotas do eixo 4."
                          }
                          maxLength={2000}
                          rows={2}
                          disabled={enviando}
                          aria-label={`O que mudou em ${codigo} R${revisao}`}
                        />
                        <span className="silencioso">
                          {arquivos.length === 1 ? "1 arquivo" : `${arquivos.length} arquivos`}
                        </span>
                      </label>
                    );
                  })}
                </div>
              )}

              <div className="linha" style={{ marginTop: 14 }}>
                <button
                  className="botao"
                  disabled={enviando || prontos === 0 || faltam > 0 || faltamDescricoes > 0}
                  onClick={enviarTudo}
                >
                  {enviando
                    ? "Enviando…"
                    : `Enviar ${prontos} arquivo${prontos === 1 ? "" : "s"}`}
                </button>
                <button
                  className="botao secundario"
                  disabled={enviando}
                  onClick={() => setItens([])}
                >
                  Limpar lista
                </button>
                {(faltam > 0 || faltamDescricoes > 0) && !enviando && (
                  <span className="silencioso" style={{ fontSize: 12.5 }}>
                    {[
                      faltam === 1
                        ? "Falta o título de 1 documento."
                        : faltam > 1
                          ? `Falta o título de ${faltam} documentos.`
                          : "",
                      faltamDescricoes === 1
                        ? "Falta dizer o que mudou em 1 revisão."
                        : faltamDescricoes > 1
                          ? `Falta dizer o que mudou em ${faltamDescricoes} revisões.`
                          : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                  </span>
                )}
                <div className="espaco" />
                {invalidos > 0 && (
                  <span className="silencioso" style={{ fontSize: 12 }}>
                    {invalidos} fora do padrão {invalidos === 1 ? "não será enviado" : "não serão enviados"}
                  </span>
                )}
              </div>

              {concluidos > 0 && !enviando && (
                <div style={{ marginTop: 14 }}>
                  <Aviso tom="ok" titulo={`${concluidos} arquivo(s) no acervo`}>
                    Revisão nova entra como <strong>em revisão</strong> — abra o documento para
                    liberar para obra. Arquivo acrescentado a uma revisão já liberada continua
                    liberado.
                  </Aviso>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}

function Linha({ item, titulo }: { item: Item; titulo: string | null }) {
  const a = item.analise;
  return (
    <div className={`linha-envio ${item.estado === "invalido" ? "invalida" : ""}`}>
      <div style={{ minWidth: 0 }}>
        <div className="mono" style={{ fontSize: 12, overflowWrap: "anywhere" }}>
          {item.arquivo.name}
        </div>
        {item.estado !== "invalido" && titulo && <div className="titulo-envio">{titulo}</div>}

        {item.estado === "invalido" && (
          <ul className="erros">
            {a.erros.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        )}

        {item.estado !== "invalido" && (
          <div className="extraido">
            <span>{a.codigo_documento}</span>
            <span>REV {a.revisao}</span>
            <span>{a.disciplina}</span>
            <span>{a.fase}</span>
            {a.revisao_status === "liberado_para_obra" ? (
              <span style={{ color: "var(--liberado)" }}>
                será acrescentado à revisão já liberada
              </span>
            ) : (
              a.revisao_existe && (
                <span style={{ color: "var(--revisao)" }}>revisão já existe</span>
              )
            )}
            {!a.documento_existe && <span style={{ color: "var(--liberado)" }}>documento novo</span>}
          </div>
        )}

        {item.estado === "erro" && item.mensagem && (
          <ul className="erros">
            <li>{item.mensagem}</li>
          </ul>
        )}

        {item.estado === "enviando" && (
          <div className="barra">
            <i style={{ width: `${Math.round(item.progresso * 100)}%` }} />
          </div>
        )}
      </div>

      <div style={{ textAlign: "right", whiteSpace: "nowrap" }}>
        {item.estado === "concluido" && item.documentoId ? (
          <Link className="link-doc" to={`/documentos/${item.documentoId}`}>
            Abrir documento
          </Link>
        ) : (
          <span className="rotulo">
            {
              {
                pronto: "Pronto",
                invalido: "Fora do padrão",
                enviando: `${Math.round(item.progresso * 100)}%`,
                concluido: "Enviado",
                erro: "Falhou",
              }[item.estado]
            }
          </span>
        )}
      </div>
    </div>
  );
}
