/** Cronograma de projetos em Gantt — PRO-FL-001 (TREELE, 03/11/2026).
 *
 *  Um por obra, só para os coordenadores dela. À esquerda, a tabela editável
 *  (nome, responsável, duração em dias úteis, início, término, progresso e
 *  predecessoras no formato do MS Project: "3; 5II+2; 7TT"); à direita, as
 *  barras, que se arrastam (muda o "não iniciar antes de") e se esticam pela
 *  ponta (muda a duração). As datas, a folga e o caminho crítico vêm
 *  calculados do servidor (services/cronograma.py): a tela não faz conta de
 *  agenda, só desenha e manda o que a pessoa mudou. */

import { useEffect, useMemo, useRef, useState, type PointerEvent as PE, type ReactNode } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { api, ErroApi, formatarData } from "../api";
import { Aviso, Carregando, Vazio } from "../componentes";
import { CHAVE_OBRA } from "../sessao";

type Tipo = "TI" | "II" | "TT";
interface Vinculo {
  predecessora_id: number;
  tipo: Tipo;
  defasagem: number;
}
interface Atividade {
  id: number;
  numero: number;
  fase: string;
  nome: string;
  area: string | null;
  responsavel: string | null;
  duracao: number;
  inicio_fixo: string | null;
  progresso: number;
  observacao: string | null;
  inicio: string;
  termino: string;
  folga: number;
  critica: boolean;
  atrasada: boolean;
  predecessoras: Vinculo[];
}
interface Dados {
  obra: { id: number; codigo: string; nome: string };
  existe: boolean;
  inicio?: string;
  termino?: string;
  progresso?: number;
  atualizado_em?: string | null;
  atualizado_por?: string | null;
  atividades: Atividade[];
}
interface ObraDoCronograma {
  id: number;
  codigo: string;
  nome: string;
  tem_cronograma: boolean;
  atualizado_em: string | null;
}

// ------------------------------------------------------------ datas
// Dias úteis de segunda a sexta, a mesma régua do servidor.
const DIA = 86_400_000;
const SEGUNDA = Date.UTC(2000, 0, 3);
const ms = (iso: string) => Date.parse(`${iso}T00:00:00Z`);
const iso = (t: number) => new Date(t).toISOString().slice(0, 10);
const somarDias = (d: string, n: number) => iso(ms(d) + n * DIA);
const diasEntre = (a: string, b: string) => Math.round((ms(b) - ms(a)) / DIA);
function indice(d: string): number {
  const dias = Math.round((ms(d) - SEGUNDA) / DIA);
  const semanas = Math.floor(dias / 7);
  return semanas * 5 + Math.min(dias - semanas * 7, 5);
}
function dataDoIndice(i: number): string {
  const semanas = Math.floor(i / 5);
  return iso(SEGUNDA + (semanas * 7 + (i - semanas * 5)) * DIA);
}
const fimDeSemana = (d: string) => [0, 6].includes(new Date(ms(d)).getUTCDay());
const curta = (d: string) => `${d.slice(8, 10)}/${d.slice(5, 7)}`;
const completa = (d: string) => `${d.slice(8, 10)}/${d.slice(5, 7)}/${d.slice(0, 4)}`;
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const hoje = () => iso(Date.now() - new Date().getTimezoneOffset() * 60_000);

// ------------------------------------------------------------ predecessoras em texto
function vinculosEmTexto(a: Atividade, numeroDe: Map<number, number>): string {
  return a.predecessoras
    .map((v) => {
      const n = numeroDe.get(v.predecessora_id) ?? "?";
      const tipo = v.tipo === "TI" ? "" : v.tipo;
      const def = v.defasagem ? (v.defasagem > 0 ? `+${v.defasagem}` : `${v.defasagem}`) : "";
      return `${n}${tipo}${def}`;
    })
    .join("; ");
}

/** "3; 5II+2; 7TT-1" → vínculos. Aceita também FS/SS/FF (MS Project em inglês). */
function textoEmVinculos(texto: string, idDe: Map<number, number>): Vinculo[] | string {
  const saida: Vinculo[] = [];
  for (const parte of texto.split(/[;,]/).map((p) => p.trim()).filter(Boolean)) {
    const m = /^(\d+)\s*(TI|II|TT|FS|SS|FF)?\s*([+-]\s*\d+)?\s*(du|d)?$/i.exec(parte);
    if (!m) return `Não entendi "${parte}". Use o número da linha, o tipo e a defasagem: 3; 5II+2; 7TT.`;
    const id = idDe.get(Number(m[1]));
    if (id === undefined) return `Não existe a linha ${m[1]}.`;
    const bruto = (m[2] ?? "TI").toUpperCase();
    const tipo = ({ FS: "TI", SS: "II", FF: "TT" } as Record<string, Tipo>)[bruto] ?? (bruto as Tipo);
    saida.push({ predecessora_id: id, tipo, defasagem: m[3] ? Number(m[3].replace(/\s/g, "")) : 0 });
  }
  return saida;
}

// ------------------------------------------------------------ escala
type Zoom = "dia" | "semana" | "mes";
const PX: Record<Zoom, number> = { dia: 26, semana: 9, mes: 3.2 };
const LINHA = 32;
const CABECALHO = 46;
const COLUNAS = "40px minmax(220px, 1fr) 112px 58px 92px 84px 54px 104px";
const LARGURA_TABELA = 800;

// ============================================================ páginas

/** /cronograma: abre o da obra ativa, se a pessoa coordena; senão, a lista. */
export function EscolherCronograma() {
  const [lista, setLista] = useState<ObraDoCronograma[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const ativa = Number(localStorage.getItem(CHAVE_OBRA)) || null;

  useEffect(() => {
    api.get<ObraDoCronograma[]>("/cronogramas").then(setLista)
      .catch((ex) => setErro(ex instanceof ErroApi ? ex.message : "Não foi possível carregar as obras."));
  }, []);

  if (lista && ativa && lista.some((o) => o.id === ativa)) return <Navigate to={`/obras/${ativa}/cronograma`} replace />;
  return (
    <>
      <div className="cabecalho-area">
        <div>
          <span className="rotulo">Qualidade · PRO-FL-001</span>
          <h1>Cronograma de projetos</h1>
        </div>
      </div>
      <div className="folha">
        {erro && <div className="folha-corpo"><Aviso tom="erro">{erro}</Aviso></div>}
        {!lista && !erro && <Carregando texto="Buscando as obras" />}
        {lista && lista.length === 0 && (
          <Vazio titulo="Nenhuma obra para você">O cronograma de projetos é dos coordenadores de cada obra.</Vazio>
        )}
        {lista && lista.length > 0 && (
          <ul className="lista-cronogramas">
            {lista.map((o) => (
              <li key={o.id}>
                <Link to={`/obras/${o.id}/cronograma`}>
                  <strong>{o.codigo}</strong> · {o.nome}
                </Link>
                <span className="silencioso">
                  {o.tem_cronograma
                    ? `atualizado ${o.atualizado_em ? formatarData(o.atualizado_em) : ""}`
                    : "sem cronograma ainda"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}

export default function Cronograma() {
  const { obraId } = useParams();
  const [dados, setDados] = useState<Dados | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<ErroApi | null>(null);
  const url = `/obras/${obraId}/cronograma`;

  useEffect(() => {
    setDados(null);
    setErro(null);
    api.get<Dados>(url).then(setDados)
      .catch((ex) => setErro(ex instanceof ErroApi ? ex.message : "Não foi possível carregar o cronograma."));
  }, [url]);

  /** Toda alteração devolve o cronograma recalculado. */
  async function salvar(p: Promise<Dados>): Promise<boolean> {
    setAviso(null);
    try {
      setDados(await p);
      return true;
    } catch (ex) {
      setAviso(ex instanceof ErroApi ? ex : new ErroApi(0, "Não foi possível salvar."));
      return false;
    }
  }

  return (
    <>
      <div className="cabecalho-area">
        <div>
          <span className="rotulo">Qualidade · PRO-FL-001</span>
          <h1>Cronograma de projetos{dados ? ` · ${dados.obra.codigo}` : ""}</h1>
        </div>
        <Link to="/cronograma" className="botao secundario pequeno" onClick={() => localStorage.removeItem(CHAVE_OBRA)}>
          Outra obra
        </Link>
      </div>
      {erro && <div className="folha"><div className="folha-corpo"><Aviso tom="erro">{erro}</Aviso></div></div>}
      {!dados && !erro && <Carregando texto="Montando o cronograma" />}
      {aviso && (
        <div className="gantt-aviso">
          <Aviso tom="erro" titulo={aviso.message} itens={aviso.erros} />
        </div>
      )}
      {dados && !dados.existe && <CriarCronograma url={url} obra={dados.obra} salvar={salvar} />}
      {dados && dados.existe && <Gantt dados={dados} url={url} salvar={salvar} />}
    </>
  );
}

function CriarCronograma({ url, obra, salvar }: { url: string; obra: Dados["obra"]; salvar: (p: Promise<Dados>) => Promise<boolean> }) {
  const [inicio, setInicio] = useState(hoje());
  const [ocupado, setOcupado] = useState(false);
  async function criar(modelo: boolean) {
    setOcupado(true);
    await salvar(api.post<Dados>(url, { inicio, modelo }));
    setOcupado(false);
  }
  return (
    <div className="folha">
      <div className="folha-corpo gantt-criar">
        <h2>{obra.codigo} · {obra.nome} ainda não tem cronograma</h2>
        <p className="silencioso">
          O modelo traz 56 atividades em 8 fases, das planilhas PRO-FL-001 e do macrofluxo do Vivere Due, já com as
          predecessoras. As durações são estimadas, em dias úteis: ajuste o que for diferente nesta obra.
        </p>
        <label className="campo">
          <span className="rotulo">Início do projeto</span>
          <input type="date" value={inicio} onChange={(e) => setInicio(e.target.value)} />
        </label>
        <div className="linha" style={{ gap: 8, marginTop: 14 }}>
          <button className="botao" disabled={ocupado || !inicio} onClick={() => criar(true)}>
            {ocupado ? "Criando…" : "Criar com as atividades do modelo"}
          </button>
          <button className="botao secundario" disabled={ocupado || !inicio} onClick={() => criar(false)}>
            Começar em branco
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================================ o Gantt

type Linha =
  | { tipo: "fase"; fase: string; atividades: Atividade[]; inicio: string; termino: string; progresso: number }
  | { tipo: "atividade"; a: Atividade };

interface Arraste {
  id: number;
  modo: "mover" | "esticar";
  x0: number;
  dias: number;
}

function Gantt({ dados, url, salvar }: { dados: Dados; url: string; salvar: (p: Promise<Dados>) => Promise<boolean> }) {
  const navegar = useNavigate();
  const [zoom, setZoom] = useState<Zoom>("semana");
  const [recolhidas, setRecolhidas] = useState<Set<string>>(new Set());
  const [selecionada, setSelecionada] = useState<number | null>(null);
  const [setas, setSetas] = useState(true);
  const [critico, setCritico] = useState(true);
  const [arraste, setArraste] = useState<Arraste | null>(null);
  const rolo = useRef<HTMLDivElement>(null);
  const px = PX[zoom];
  const atividades = dados.atividades;

  const numeroDe = useMemo(() => new Map(atividades.map((a) => [a.id, a.numero])), [atividades]);
  const idDe = useMemo(() => new Map(atividades.map((a) => [a.numero, a.id])), [atividades]);
  const porId = useMemo(() => new Map(atividades.map((a) => [a.id, a])), [atividades]);
  const fases = useMemo(() => [...new Set(atividades.map((a) => a.fase))], [atividades]);

  const linhas = useMemo<Linha[]>(() => {
    const saida: Linha[] = [];
    for (const fase of fases) {
      const da = atividades.filter((a) => a.fase === fase);
      const peso = da.reduce((s, a) => s + Math.max(a.duracao, 1), 0) || 1;
      saida.push({
        tipo: "fase", fase, atividades: da,
        inicio: da.reduce((m, a) => (a.inicio < m ? a.inicio : m), da[0].inicio),
        termino: da.reduce((m, a) => (a.termino > m ? a.termino : m), da[0].termino),
        progresso: da.reduce((s, a) => s + Math.max(a.duracao, 1) * a.progresso, 0) / peso,
      });
      if (!recolhidas.has(fase)) for (const a of da) saida.push({ tipo: "atividade", a });
    }
    return saida;
  }, [atividades, fases, recolhidas]);

  // A régua: uma semana antes do começo até três depois do fim.
  const origem = useMemo(() => {
    const menor = atividades.reduce((m, a) => (a.inicio < m ? a.inicio : m), dados.inicio ?? hoje());
    const d = somarDias(menor, -7);
    return somarDias(d, -((new Date(ms(d)).getUTCDay() + 6) % 7)); // segunda-feira
  }, [atividades, dados.inicio]);
  const fim = useMemo(() => somarDias(atividades.reduce((m, a) => (a.termino > m ? a.termino : m), dados.termino ?? hoje()), 28), [atividades, dados.termino]);
  const totalDias = diasEntre(origem, fim) + 1;
  const largura = totalDias * px;
  const x = (d: string) => diasEntre(origem, d) * px;

  // Onde está cada atividade (para as setas), já com o arraste em andamento.
  const posicao = useMemo(() => {
    const m = new Map<number, { linha: number; x1: number; x2: number }>();
    linhas.forEach((l, i) => {
      if (l.tipo !== "atividade") return;
      const { a } = l;
      let ini = a.inicio;
      let ter = a.termino;
      if (arraste?.id === a.id) {
        if (arraste.modo === "mover") {
          ini = dataDoIndice(indice(a.inicio) + arraste.dias);
          ter = a.duracao > 0 ? dataDoIndice(indice(ini) + a.duracao - 1) : ini;
        } else ter = dataDoIndice(Math.max(indice(a.inicio), indice(a.termino) + arraste.dias));
      }
      m.set(a.id, { linha: i, x1: x(ini), x2: a.duracao > 0 ? x(ter) + px : x(ini) });
    });
    return m;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [linhas, arraste, px, origem]);

  function irParaHoje() {
    rolo.current?.scrollTo({ left: Math.max(0, x(hoje()) - 200), behavior: "smooth" });
  }
  useEffect(() => {
    // Ao abrir, a régua começa no início do projeto.
    rolo.current?.scrollTo({ left: Math.max(0, x(dados.inicio ?? origem) - 40) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zoom]);

  const alterar = (id: number, corpo: Partial<Atividade>) => salvar(api.patch<Dados>(`${url}/atividades/${id}`, corpo));
  const definirPredecessoras = (id: number, v: Vinculo[]) => salvar(api.put<Dados>(`${url}/atividades/${id}/predecessoras`, v));

  async function novaAtividade(fase?: string, depois?: number) {
    const alvo = fase ?? (selecionada ? porId.get(selecionada)?.fase : undefined) ?? fases[fases.length - 1] ?? "Projetos";
    await salvar(api.post<Dados>(`${url}/atividades`, {
      fase: alvo, nome: "Nova atividade", duracao: 5,
      depois_de: depois ?? (selecionada && porId.get(selecionada)?.fase === alvo ? selecionada : undefined),
    }));
  }
  async function novaFase() {
    const nome = window.prompt("Nome da nova fase:");
    if (nome?.trim()) await salvar(api.post<Dados>(`${url}/atividades`, { fase: nome.trim(), nome: "Nova atividade", duracao: 5 }));
  }
  async function mover(id: number, passo: -1 | 1) {
    const a = porId.get(id);
    if (!a) return;
    const ids = atividades.map((x) => x.id);
    const i = ids.indexOf(id);
    const j = i + passo;
    if (j < 0 || j >= ids.length || atividades[j].fase !== a.fase) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    await salvar(api.put<Dados>(`${url}/ordem`, { ids }));
  }
  async function apagar(id: number) {
    const a = porId.get(id);
    if (a && window.confirm(`Apagar a atividade ${a.numero} · ${a.nome}? Os vínculos com ela saem junto.`)) {
      if (selecionada === id) setSelecionada(null);
      await salvar(api.delete<Dados>(`${url}/atividades/${id}`));
    }
  }
  async function apagarCronograma() {
    if (!window.confirm("Apagar o cronograma inteiro desta obra? Não dá para desfazer.")) return;
    try {
      await api.delete(url);
      navegar(0);
    } catch {
      /* o aviso aparece pelo salvar na próxima ação */
    }
  }

  function exportarCsv() {
    const cab = ["Nº", "Fase", "Atividade", "Área", "Responsável", "Duração (dias úteis)", "Início", "Término", "% concluído", "Predecessoras", "Folga", "Crítica"];
    const linhasCsv = atividades.map((a) => [
      a.numero, a.fase, a.nome, a.area ?? "", a.responsavel ?? "", a.duracao, completa(a.inicio), completa(a.termino),
      a.progresso, vinculosEmTexto(a, numeroDe), a.folga, a.critica ? "sim" : "",
    ]);
    const csv = [cab, ...linhasCsv].map((l) => l.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(";")).join("\r\n");
    const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${dados.obra.codigo}-cronograma-de-projetos.csv`;
    link.click();
    URL.revokeObjectURL(link.href);
  }

  // Arrastar a barra: mover muda o "não iniciar antes de"; a ponta, a duração.
  function comecarArraste(e: PE, a: Atividade, modo: Arraste["modo"]) {
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();
    try {
      (e.target as Element).setPointerCapture(e.pointerId);
    } catch {
      /* sem captura, o rolo ainda recebe o movimento */
    }
    setSelecionada(a.id);
    setArraste({ id: a.id, modo, x0: e.clientX, dias: 0 });
  }
  function duranteArraste(e: PE) {
    if (!arraste) return;
    // Em dias úteis: arrastar uma semana anda cinco.
    const corridos = Math.round((e.clientX - arraste.x0) / px);
    const a = porId.get(arraste.id)!;
    const base = arraste.modo === "mover" ? a.inicio : a.termino;
    const dias = indice(somarDias(base, corridos)) - indice(base);
    if (dias !== arraste.dias) setArraste({ ...arraste, dias });
  }
  async function terminarArraste() {
    if (!arraste) return;
    const { id, modo, dias } = arraste;
    const a = porId.get(id)!;
    setArraste(null);
    if (!dias) return;
    if (modo === "mover") await alterar(id, { inicio_fixo: dataDoIndice(indice(a.inicio) + dias) });
    else await alterar(id, { duracao: Math.max(1, a.duracao + dias) });
  }

  const atrasadas = atividades.filter((a) => a.atrasada).length;
  const criticas = atividades.filter((a) => a.critica).length;
  const sel = selecionada ? porId.get(selecionada) ?? null : null;

  return (
    <div className="folha gantt">
      <div className="gantt-barra">
        <label className="gantt-campo">
          <span>Início do projeto</span>
          <input type="date" defaultValue={dados.inicio} key={dados.inicio}
            onBlur={(e) => e.target.value && e.target.value !== dados.inicio && salvar(api.patch<Dados>(url, { inicio: e.target.value }))} />
        </label>
        <div className="gantt-resumo">
          <span><b>{dados.termino ? completa(dados.termino) : "—"}</b> término previsto</span>
          <span><b>{(dados.progresso ?? 0).toLocaleString("pt-BR", { maximumFractionDigits: 0 })}%</b> concluído</span>
          <span className={atrasadas ? "gantt-alerta" : ""}><b>{atrasadas}</b> atrasada{atrasadas === 1 ? "" : "s"}</span>
          <span><b>{criticas}</b> no caminho crítico</span>
        </div>
        <div className="seletor-visao" role="group" aria-label="Escala">
          {(["dia", "semana", "mes"] as Zoom[]).map((z) => (
            <button key={z} className={zoom === z ? "ativo" : ""} onClick={() => setZoom(z)}>
              {z === "dia" ? "Dias" : z === "semana" ? "Semanas" : "Meses"}
            </button>
          ))}
        </div>
        <button className="botao secundario pequeno" onClick={irParaHoje}>Hoje</button>
        <label className="gantt-opcao"><input type="checkbox" checked={critico} onChange={(e) => setCritico(e.target.checked)} /> Caminho crítico</label>
        <label className="gantt-opcao"><input type="checkbox" checked={setas} onChange={(e) => setSetas(e.target.checked)} /> Vínculos</label>
        <span className="gantt-espaco" />
        <button className="botao pequeno" onClick={() => novaAtividade()}>+ Atividade</button>
        <button className="botao secundario pequeno" onClick={novaFase}>+ Fase</button>
        <button className="botao secundario pequeno"
          onClick={() => setRecolhidas(recolhidas.size ? new Set() : new Set(fases))}>
          {recolhidas.size ? "Expandir fases" : "Recolher fases"}
        </button>
        <button className="botao secundario pequeno" onClick={exportarCsv}>Exportar (Excel)</button>
      </div>

      <div className="gantt-corpo">
        <div className="gantt-rolo" ref={rolo} onPointerMove={duranteArraste} onPointerUp={terminarArraste}
          onPointerCancel={() => setArraste(null)}>
          <div className="gantt-conteudo" style={{ width: LARGURA_TABELA + largura }}>
            {/* Cabeçalho: colunas e régua */}
            <div className="gantt-linha gantt-topo" style={{ height: CABECALHO }}>
              <div className="gantt-celulas gantt-titulos" style={{ gridTemplateColumns: COLUNAS, width: LARGURA_TABELA }}>
                <span>Nº</span><span>Atividade</span><span>Responsável</span><span title="Dias úteis; 0 é marco">Dias</span>
                <span>Início</span><span>Término</span><span>%</span><span title="Ex.: 3; 5II+2; 7TT">Predec.</span>
              </div>
              <Regua origem={origem} totalDias={totalDias} px={px} zoom={zoom} />
            </div>

            <div className="gantt-linhas" style={{ position: "relative" }}>
              <Fundo origem={origem} totalDias={totalDias} px={px} zoom={zoom} altura={linhas.length * LINHA} x={x} />
              {setas && (
                <Setas atividades={atividades} posicao={posicao} largura={largura} altura={linhas.length * LINHA}
                  selecionada={selecionada} />
              )}
              {linhas.map((l) =>
                l.tipo === "fase" ? (
                  <LinhaFase key={`f:${l.fase}`} l={l} recolhida={recolhidas.has(l.fase)} x={x} px={px}
                    alternar={() => {
                      const s = new Set(recolhidas);
                      if (s.has(l.fase)) s.delete(l.fase); else s.add(l.fase);
                      setRecolhidas(s);
                    }}
                    renomear={(para) => salvar(api.patch<Dados>(`${url}/fases`, { de: l.fase, para }))}
                    adicionar={() => novaAtividade(l.fase, l.atividades[l.atividades.length - 1]?.id)} />
                ) : (
                  <LinhaAtividade key={l.a.id} a={l.a} selecionada={selecionada === l.a.id} critico={critico}
                    pos={posicao.get(l.a.id)!} numeroDe={numeroDe} idDe={idDe} px={px}
                    arrastando={arraste?.id === l.a.id}
                    aoSelecionar={() => setSelecionada(l.a.id)} alterar={alterar} definirPredecessoras={definirPredecessoras}
                    comecarArraste={comecarArraste} />
                ),
              )}
              {atividades.length === 0 && (
                <div className="gantt-vazio">Sem atividades. Use “+ Atividade” para começar.</div>
              )}
            </div>
          </div>
        </div>

        {sel && (
          <Detalhe a={sel} fases={fases} numeroDe={numeroDe} atividades={atividades} fechar={() => setSelecionada(null)}
            alterar={alterar} definirPredecessoras={definirPredecessoras} mover={mover} apagar={apagar}
            inserirAbaixo={() => novaAtividade(sel.fase, sel.id)} />
        )}
      </div>

      <div className="gantt-rodape">
        <span className="silencioso">
          Datas em dias úteis (segunda a sexta). Arraste a barra para fixar o início; puxe a ponta direita para mudar a
          duração. Predecessoras: número da linha e tipo — TI (término-início, o padrão), II (início-início), TT
          (término-término) — com defasagem em dias úteis: “5II+2”.
          {dados.atualizado_em && ` Atualizado ${formatarData(dados.atualizado_em)}${dados.atualizado_por ? ` por ${dados.atualizado_por}` : ""}.`}
        </span>
        <button className="link-perigo" onClick={apagarCronograma}>Apagar cronograma</button>
      </div>
    </div>
  );
}

// ------------------------------------------------------------ régua e fundo

function Regua({ origem, totalDias, px, zoom }: { origem: string; totalDias: number; px: number; zoom: Zoom }) {
  const meses: { x: number; w: number; rotulo: string }[] = [];
  const baixo: { x: number; rotulo: string; fds?: boolean }[] = [];
  for (let i = 0; i < totalDias; i++) {
    const d = somarDias(origem, i);
    const dia = Number(d.slice(8, 10));
    if (i === 0 || dia === 1) meses.push({ x: i * px, w: 0, rotulo: `${MESES[Number(d.slice(5, 7)) - 1]} ${d.slice(0, 4)}` });
    if (zoom === "dia") baixo.push({ x: i * px, rotulo: String(dia), fds: fimDeSemana(d) });
    else if (zoom === "semana" && new Date(ms(d)).getUTCDay() === 1) baixo.push({ x: i * px, rotulo: curta(d) });
  }
  meses.forEach((m, k) => (m.w = (k + 1 < meses.length ? meses[k + 1].x : totalDias * px) - m.x));
  return (
    <div className="gantt-regua" style={{ width: totalDias * px }}>
      <div className="gantt-regua-meses">
        {meses.map((m) => (
          <span key={m.x} style={{ left: m.x, width: m.w }}>{m.w > 34 ? m.rotulo : ""}</span>
        ))}
      </div>
      <div className="gantt-regua-baixo">
        {baixo.map((b) => (
          <span key={b.x} className={b.fds ? "fds" : ""} style={{ left: b.x, width: zoom === "dia" ? px : 7 * px }}>{b.rotulo}</span>
        ))}
      </div>
    </div>
  );
}

function Fundo({ origem, totalDias, px, zoom, altura, x }: {
  origem: string; totalDias: number; px: number; zoom: Zoom; altura: number; x: (d: string) => number;
}) {
  const faixas: ReactNode[] = [];
  for (let i = 0; i < totalDias; i++) {
    const d = somarDias(origem, i);
    if (zoom !== "mes" && fimDeSemana(d) && new Date(ms(d)).getUTCDay() === 6) {
      faixas.push(<span key={i} className="gantt-fds" style={{ left: i * px, width: 2 * px }} />);
    }
    if (d.slice(8, 10) === "01") faixas.push(<span key={`m${i}`} className="gantt-mes" style={{ left: i * px }} />);
  }
  const h = hoje();
  return (
    <div className="gantt-fundo" style={{ left: LARGURA_TABELA, width: totalDias * px, height: altura }}>
      {faixas}
      {h >= origem && diasEntre(origem, h) < totalDias && (
        <span className="gantt-hoje" style={{ left: x(h) + px / 2 }} title={`Hoje, ${completa(h)}`} />
      )}
    </div>
  );
}

function Setas({ atividades, posicao, largura, altura, selecionada }: {
  atividades: Atividade[];
  posicao: Map<number, { linha: number; x1: number; x2: number }>;
  largura: number;
  altura: number;
  selecionada: number | null;
}) {
  const caminhos: ReactNode[] = [];
  for (const a of atividades) {
    const s = posicao.get(a.id);
    if (!s) continue;
    for (const v of a.predecessoras) {
      const p = posicao.get(v.predecessora_id);
      if (!p) continue;
      const yp = p.linha * LINHA + LINHA / 2;
      const ys = s.linha * LINHA + LINHA / 2;
      const desce = ys > yp ? 1 : -1;
      let d: string;
      if (v.tipo === "II") {
        const xo = Math.min(p.x1, s.x1) - 8;
        d = `M${p.x1},${yp} H${xo} V${ys} H${s.x1 - 2}`;
      } else if (v.tipo === "TT") {
        const xo = Math.max(p.x2, s.x2) + 8;
        d = `M${p.x2},${yp} H${xo} V${ys} H${s.x2 + 2}`;
      } else if (s.x1 >= p.x2 + 12) {
        d = `M${p.x2},${yp} H${p.x2 + 6} V${ys} H${s.x1 - 2}`;
      } else {
        const meio = yp + desce * (LINHA / 2);
        d = `M${p.x2},${yp} H${p.x2 + 6} V${meio} H${s.x1 - 10} V${ys} H${s.x1 - 2}`;
      }
      const destaque = selecionada === a.id || selecionada === v.predecessora_id;
      caminhos.push(
        <path key={`${v.predecessora_id}-${a.id}`} d={d} className={destaque ? "destaque" : ""}
          markerEnd={v.tipo === "TT" ? "url(#gantt-ponta-esq)" : "url(#gantt-ponta)"} />,
      );
    }
  }
  return (
    <svg className="gantt-setas" style={{ left: LARGURA_TABELA }} width={largura} height={altura}>
      <defs>
        <marker id="gantt-ponta" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
          <path d="M0,0 L8,4 L0,8 z" />
        </marker>
        <marker id="gantt-ponta-esq" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
          <path d="M0,0 L8,4 L0,8 z" />
        </marker>
      </defs>
      {caminhos}
    </svg>
  );
}

// ------------------------------------------------------------ linhas

function LinhaFase({ l, recolhida, x, px, alternar, renomear, adicionar }: {
  l: Extract<Linha, { tipo: "fase" }>;
  recolhida: boolean;
  x: (d: string) => number;
  px: number;
  alternar: () => void;
  renomear: (para: string) => void;
  adicionar: () => void;
}) {
  const [editando, setEditando] = useState(false);
  const x1 = x(l.inicio);
  const x2 = x(l.termino) + px;
  return (
    <div className="gantt-linha gantt-linha-fase" style={{ height: LINHA }}>
      <div className="gantt-celulas" style={{ gridTemplateColumns: COLUNAS, width: LARGURA_TABELA }}>
        <button className="gantt-seta-fase" onClick={alternar} aria-label={recolhida ? "Expandir fase" : "Recolher fase"}>
          {recolhida ? "▸" : "▾"}
        </button>
        {editando ? (
          <input className="gantt-entrada" autoFocus defaultValue={l.fase}
            onBlur={(e) => { setEditando(false); if (e.target.value.trim() && e.target.value.trim() !== l.fase) renomear(e.target.value.trim()); }}
            onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); if (e.key === "Escape") setEditando(false); }} />
        ) : (
          <span className="gantt-nome-fase" onDoubleClick={() => setEditando(true)} title="Dois cliques para renomear">
            {l.fase} <small>({l.atividades.length})</small>
            <button className="gantt-mais" onClick={adicionar} title="Nova atividade nesta fase">+</button>
          </span>
        )}
        <span />
        <span className="num">{indice(l.termino) - indice(l.inicio) + 1}</span>
        <span>{curta(l.inicio)}</span>
        <span>{curta(l.termino)}</span>
        <span className="num">{Math.round(l.progresso)}</span>
        <span />
      </div>
      <div className="gantt-trilho">
        <div className="gantt-resumo-fase" style={{ left: x1, width: Math.max(4, x2 - x1) }}>
          <i style={{ width: `${l.progresso}%` }} />
        </div>
      </div>
    </div>
  );
}

function Celula({ valor, tipo = "text", salvar, rotulo, ...resto }: {
  valor: string;
  tipo?: string;
  /** false (salvar recusado) volta a célula ao valor guardado. */
  salvar: (v: string) => unknown;
  rotulo: string;
  min?: number;
  max?: number;
  className?: string;
  title?: string;
}) {
  return (
    <input className={`gantt-entrada ${resto.className ?? ""}`} type={tipo} defaultValue={valor} key={valor}
      aria-label={rotulo} title={resto.title} min={resto.min} max={resto.max}
      onBlur={async (e) => {
        const campo = e.target;
        if (campo.value !== valor && (await salvar(campo.value)) === false) campo.value = valor;
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        if (e.key === "Escape") { (e.target as HTMLInputElement).value = valor; (e.target as HTMLInputElement).blur(); }
      }} />
  );
}

function LinhaAtividade({ a, selecionada, critico, pos, numeroDe, idDe, px, arrastando, aoSelecionar, alterar, definirPredecessoras, comecarArraste }: {
  a: Atividade;
  selecionada: boolean;
  critico: boolean;
  pos: { linha: number; x1: number; x2: number };
  numeroDe: Map<number, number>;
  idDe: Map<number, number>;
  px: number;
  arrastando: boolean;
  aoSelecionar: () => void;
  alterar: (id: number, corpo: Partial<Atividade>) => Promise<boolean>;
  definirPredecessoras: (id: number, v: Vinculo[]) => Promise<boolean>;
  comecarArraste: (e: PE, a: Atividade, modo: "mover" | "esticar") => void;
}) {
  const [erroPred, setErroPred] = useState<string | null>(null);
  const marco = a.duracao === 0;
  const concluida = a.progresso >= 100;
  const classe = [
    "gantt-barra-atividade",
    concluida ? "concluida" : a.atrasada ? "atrasada" : critico && a.critica ? "critica" : "",
    arrastando ? "arrastando" : "",
  ].join(" ");
  const dica = `${a.numero} · ${a.nome}\n${completa(a.inicio)} a ${completa(a.termino)} · ${a.duracao} dias úteis · ${a.progresso}%` +
    `\nFolga: ${a.folga} dia${Math.abs(a.folga) === 1 ? "" : "s"} útil${Math.abs(a.folga) === 1 ? "" : "eis"}${a.critica ? " (caminho crítico)" : ""}` +
    (a.inicio_fixo ? `\nNão iniciar antes de ${completa(a.inicio_fixo)}` : "");
  return (
    <div className={`gantt-linha ${selecionada ? "selecionada" : ""}`} style={{ height: LINHA }} onClick={aoSelecionar}>
      <div className="gantt-celulas" style={{ gridTemplateColumns: COLUNAS, width: LARGURA_TABELA }}>
        <span className="num gantt-numero">{a.numero}</span>
        <Celula valor={a.nome} rotulo="Atividade" salvar={(v) => v.trim() && alterar(a.id, { nome: v.trim() })}
          className={a.critica && critico && !concluida ? "texto-critico" : ""} />
        <Celula valor={a.responsavel ?? ""} rotulo="Responsável" salvar={(v) => alterar(a.id, { responsavel: v })} />
        <Celula valor={String(a.duracao)} tipo="number" min={0} rotulo="Duração em dias úteis" className="num"
          salvar={(v) => v !== "" && alterar(a.id, { duracao: Math.max(0, Math.round(Number(v))) })} />
        <span className="gantt-data">
          <Celula valor={a.inicio} tipo="date" rotulo="Início"
            title={a.inicio_fixo ? `Fixado: não iniciar antes de ${completa(a.inicio_fixo)}` : "Calculado pelas predecessoras. Mudar fixa a data."}
            salvar={(v) => v && alterar(a.id, { inicio_fixo: v })} />
          {a.inicio_fixo && (
            <button className="gantt-pino" title="Data fixada por você. Clique para voltar a seguir as predecessoras."
              onClick={(e) => { e.stopPropagation(); alterar(a.id, { inicio_fixo: null }); }}>●</button>
          )}
        </span>
        <Celula valor={a.termino} tipo="date" rotulo="Término" title="Mudar o término muda a duração"
          salvar={(v) => v && alterar(a.id, { duracao: Math.max(1, indice(v) - indice(a.inicio) + 1) })} />
        <Celula valor={String(a.progresso)} tipo="number" min={0} max={100} rotulo="Porcentagem concluída" className="num"
          salvar={(v) => v !== "" && alterar(a.id, { progresso: Math.min(100, Math.max(0, Math.round(Number(v)))) })} />
        <span className="gantt-pred">
          <Celula valor={vinculosEmTexto(a, numeroDe)} rotulo="Predecessoras" className={erroPred ? "invalida" : ""}
            title={erroPred ?? "Ex.: 3; 5II+2; 7TT"}
            salvar={(v) => {
              const r = textoEmVinculos(v, idDe);
              if (typeof r === "string") { setErroPred(r); return; }
              setErroPred(null);
              return definirPredecessoras(a.id, r);
            }} />
        </span>
      </div>
      <div className="gantt-trilho">
        {marco ? (
          <span className={`gantt-marco ${concluida ? "concluida" : ""}`} style={{ left: pos.x1 + px / 2 - 7 }} title={dica}
            onPointerDown={(e) => comecarArraste(e, a, "mover")} />
        ) : (
          <div className={classe} style={{ left: pos.x1, width: Math.max(px, pos.x2 - pos.x1) }} title={dica}
            onPointerDown={(e) => comecarArraste(e, a, "mover")}>
            <i style={{ width: `${a.progresso}%` }} />
            <span className="gantt-ponta" onPointerDown={(e) => comecarArraste(e, a, "esticar")} />
          </div>
        )}
        {!marco && pos.x2 - pos.x1 < 260 && (
          <span className="gantt-rotulo-barra" style={{ left: pos.x2 + 6 }}>{a.responsavel ?? ""}</span>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------ painel da atividade

function Detalhe({ a, fases, numeroDe, atividades, fechar, alterar, definirPredecessoras, mover, apagar, inserirAbaixo }: {
  a: Atividade;
  fases: string[];
  numeroDe: Map<number, number>;
  atividades: Atividade[];
  fechar: () => void;
  alterar: (id: number, corpo: Partial<Atividade>) => Promise<boolean>;
  definirPredecessoras: (id: number, v: Vinculo[]) => Promise<boolean>;
  mover: (id: number, passo: -1 | 1) => void;
  apagar: (id: number) => void;
  inserirAbaixo: () => void;
}) {
  const [nova, setNova] = useState<Vinculo>({ predecessora_id: 0, tipo: "TI", defasagem: 0 });
  const sucessoras = atividades.filter((x) => x.predecessoras.some((v) => v.predecessora_id === a.id));
  const trocar = (k: number, v: Partial<Vinculo>) =>
    definirPredecessoras(a.id, a.predecessoras.map((x, i) => (i === k ? { ...x, ...v } : x)));
  return (
    <aside className="gantt-detalhe" aria-label="Atividade selecionada">
      <div className="gantt-detalhe-topo">
        <span className="rotulo">Atividade {a.numero}</span>
        <button className="assistente-fechar" onClick={fechar} aria-label="Fechar">×</button>
      </div>
      <label className="campo">
        <span className="rotulo">Nome</span>
        <Celula valor={a.nome} rotulo="Nome" salvar={(v) => v.trim() && alterar(a.id, { nome: v.trim() })} />
      </label>
      <label className="campo">
        <span className="rotulo">Fase</span>
        <select value={a.fase} onChange={(e) => alterar(a.id, { fase: e.target.value })}>
          {fases.map((f) => <option key={f}>{f}</option>)}
        </select>
      </label>
      <div className="gantt-detalhe-duas">
        <label className="campo">
          <span className="rotulo">Área</span>
          <Celula valor={a.area ?? ""} rotulo="Área" salvar={(v) => alterar(a.id, { area: v })} />
        </label>
        <label className="campo">
          <span className="rotulo">Responsável</span>
          <Celula valor={a.responsavel ?? ""} rotulo="Responsável" salvar={(v) => alterar(a.id, { responsavel: v })} />
        </label>
      </div>
      <div className="gantt-detalhe-duas">
        <label className="campo">
          <span className="rotulo">Duração (dias úteis)</span>
          <Celula valor={String(a.duracao)} tipo="number" min={0} rotulo="Duração"
            salvar={(v) => v !== "" && alterar(a.id, { duracao: Math.max(0, Math.round(Number(v))) })} />
        </label>
        <label className="campo">
          <span className="rotulo">Concluído: {a.progresso}%</span>
          <input type="range" min={0} max={100} step={5} defaultValue={a.progresso} key={a.progresso}
            onPointerUp={(e) => alterar(a.id, { progresso: Number((e.target as HTMLInputElement).value) })}
            onKeyUp={(e) => alterar(a.id, { progresso: Number((e.target as HTMLInputElement).value) })} />
        </label>
      </div>
      <p className="gantt-datas">
        <b>{completa(a.inicio)}</b> a <b>{completa(a.termino)}</b>
        {a.duracao === 0 && " · marco"}
        <br />
        Folga {a.folga} dia{Math.abs(a.folga) === 1 ? "" : "s"} út{Math.abs(a.folga) === 1 ? "il" : "eis"}
        {a.critica && <strong className="texto-critico"> · caminho crítico</strong>}
        {a.atrasada && <strong className="gantt-alerta"> · atrasada</strong>}
      </p>
      <label className="campo">
        <span className="rotulo">Não iniciar antes de</span>
        <span className="linha" style={{ gap: 6 }}>
          <Celula valor={a.inicio_fixo ?? ""} tipo="date" rotulo="Não iniciar antes de"
            salvar={(v) => alterar(a.id, { inicio_fixo: v || null })} />
          {a.inicio_fixo && <button className="botao secundario pequeno" onClick={() => alterar(a.id, { inicio_fixo: null })}>Tirar</button>}
        </span>
      </label>

      <div className="campo">
        <span className="rotulo">Predecessoras</span>
        {a.predecessoras.length === 0 && <p className="silencioso" style={{ margin: "2px 0" }}>Nenhuma: começa no início do projeto.</p>}
        {a.predecessoras.map((v, k) => {
          const p = atividades.find((x) => x.id === v.predecessora_id);
          return (
            <div key={v.predecessora_id} className="gantt-vinculo">
              <span title={p?.nome}>{numeroDe.get(v.predecessora_id)} · {p?.nome}</span>
              <select value={v.tipo} onChange={(e) => trocar(k, { tipo: e.target.value as Tipo })} aria-label="Tipo">
                <option value="TI">TI</option><option value="II">II</option><option value="TT">TT</option>
              </select>
              <input type="number" defaultValue={v.defasagem} key={v.defasagem} aria-label="Defasagem em dias úteis"
                onBlur={(e) => Number(e.target.value) !== v.defasagem && trocar(k, { defasagem: Math.round(Number(e.target.value)) || 0 })} />
              <button className="link-perigo" aria-label="Tirar vínculo"
                onClick={() => definirPredecessoras(a.id, a.predecessoras.filter((_, i) => i !== k))}>×</button>
            </div>
          );
        })}
        <div className="gantt-vinculo">
          <select value={nova.predecessora_id} onChange={(e) => setNova({ ...nova, predecessora_id: Number(e.target.value) })} aria-label="Nova predecessora">
            <option value={0}>Adicionar predecessora…</option>
            {atividades.filter((x) => x.id !== a.id && !a.predecessoras.some((v) => v.predecessora_id === x.id)).map((x) => (
              <option key={x.id} value={x.id}>{x.numero} · {x.nome}</option>
            ))}
          </select>
          <select value={nova.tipo} onChange={(e) => setNova({ ...nova, tipo: e.target.value as Tipo })} aria-label="Tipo">
            <option value="TI">TI</option><option value="II">II</option><option value="TT">TT</option>
          </select>
          <input type="number" value={nova.defasagem} onChange={(e) => setNova({ ...nova, defasagem: Math.round(Number(e.target.value)) || 0 })} aria-label="Defasagem" />
          <button className="botao pequeno" disabled={!nova.predecessora_id}
            onClick={async () => { if (await definirPredecessoras(a.id, [...a.predecessoras, nova])) setNova({ predecessora_id: 0, tipo: "TI", defasagem: 0 }); }}>
            +
          </button>
        </div>
        {sucessoras.length > 0 && (
          <p className="silencioso" style={{ margin: "6px 0 0" }}>
            Sucessoras: {sucessoras.map((s) => `${s.numero} · ${s.nome}`).join("; ")}
          </p>
        )}
      </div>

      <label className="campo">
        <span className="rotulo">Observação</span>
        <textarea rows={3} defaultValue={a.observacao ?? ""} key={`${a.id}:${a.observacao ?? ""}`}
          onBlur={(e) => e.target.value !== (a.observacao ?? "") && alterar(a.id, { observacao: e.target.value })} />
      </label>

      <div className="linha gantt-detalhe-acoes">
        <button className="botao secundario pequeno" onClick={() => mover(a.id, -1)} title="Subir na fase">↑</button>
        <button className="botao secundario pequeno" onClick={() => mover(a.id, 1)} title="Descer na fase">↓</button>
        <button className="botao secundario pequeno" onClick={inserirAbaixo}>Inserir abaixo</button>
        <span className="gantt-espaco" />
        <button className="botao perigo pequeno" onClick={() => apagar(a.id)}>Apagar</button>
      </div>
    </aside>
  );
}
