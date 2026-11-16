/** Conflitos do 3D na ata de análise crítica (TREELE, 16/11/2026): quando a
 *  revisão corrige conflitos — o pedido de revisão ou a reprovação saiu deles
 *  —, a ata mostra de onde veio cada correção e a situação de cada conflito.
 *  No formulário é a situação de agora, com o aviso dos que continuam ativos;
 *  na ata registrada, o retrato do dia (ver services/conflitos_correcao). */

import type { ConflitoNaAta, OrigemConflitosAta } from "./api";

const ROTULO = { novo: "Novo", ativo: "Ainda ativo", aprovado: "Aprovado", resolvido: "Resolvido" } as const;

function data(iso: string | null | undefined) {
  return iso ? new Date(iso).toLocaleDateString("pt-BR") : "-";
}

function medida(c: ConflitoNaAta) {
  const cm = (c.medida_cm ?? 0).toFixed(1).replace(".", ",");
  return c.tipo === "interferencia" ? `entra ${cm} cm` : `a ${cm} cm`;
}

export function situacaoDoConflito(c: ConflitoNaAta, revisao?: string) {
  if (c.situacao === "resolvido") return `Resolvido${c.resolvido_em ? ` em ${data(c.resolvido_em)}` : ""}`;
  if (c.situacao === "aprovado") return `Aprovado${c.justificativa ? `: ${c.justificativa}` : ""}`;
  return `${ROTULO[c.situacao]}${c.conferido === false && revisao ? ` (a detecção ainda não rodou com a R${revisao})` : ""}`;
}

/** Os conflitos que ainda aparecem: o aviso do formulário. */
export function conflitosAbertos(origens: OrigemConflitosAta[]) {
  const abertos = origens.flatMap((o) => o.conflitos.filter((c) => c.situacao === "novo" || c.situacao === "ativo"));
  return { abertos, semConferir: abertos.filter((c) => c.conferido === false) };
}

export default function QuadroConflitosAta({
  origens,
  varias,
  className = "",
}: {
  origens: OrigemConflitosAta[];
  /** Mais de uma revisão na ata: mostra o documento de cada origem. */
  varias: boolean;
  className?: string;
}) {
  return (
    <table className={`quadro-conflitos-ata ${className}`}>
      <thead>
        <tr>
          <th>Nº</th>
          <th>DISCIPLINAS</th>
          <th>PEÇAS EM CONFLITO</th>
          <th>MEDIDA</th>
          <th>SITUAÇÃO</th>
        </tr>
      </thead>
      {origens.map((o) => (
        <tbody key={`${o.tipo}-${o.id}`}>
          <tr className="origem">
            <td colSpan={5}>
              <strong>{o.origem}</strong>
              {varias && ` · ${o.documento} R${o.revisao}`} · {data(o.data)}
              {o.por && ` · ${o.por}`}
              {o.descricao && <em style={{ display: "block", whiteSpace: "pre-line" }}>{o.descricao}</em>}
            </td>
          </tr>
          {o.conflitos.map((c) => (
            <tr key={c.id}>
              <td className="mono">#{c.id}</td>
              <td>{c.disciplinas}</td>
              <td>
                {c.peca_a}
                {c.documento_a && <span className="silencioso"> ({c.documento_a})</span>}
                <br />× {c.peca_b}
                {c.documento_b && <span className="silencioso"> ({c.documento_b})</span>}
              </td>
              <td style={{ whiteSpace: "nowrap" }}>{medida(c)}</td>
              <td className={c.situacao === "novo" || c.situacao === "ativo" ? "aberto" : undefined}>
                {situacaoDoConflito(c, o.revisao)}
              </td>
            </tr>
          ))}
        </tbody>
      ))}
    </table>
  );
}

/** Os conflitos apontados numa reprovação, dentro da "Solicitação de
 *  alterações". */
export function ConflitosApontados({ conflitos }: { conflitos: ConflitoNaAta[] }) {
  return (
    <span className="conflitos-apontados">
      <strong>Conflitos apontados:</strong>
      {conflitos.map((c) => (
        <span key={c.id} style={{ display: "block" }}>
          #{c.id} {c.disciplinas}: {c.peca_a} × {c.peca_b} ({medida(c)})
        </span>
      ))}
    </span>
  );
}
