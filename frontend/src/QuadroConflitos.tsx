/** Conflitos entre disciplinas na página da obra (TREELE, 22/10/2026): o que
 *  as detecções do visualizador 3D guardaram, sem precisar abrir o 3D —
 *  quantos abertos por par de disciplinas, os documentos com mais conflitos e
 *  a última detecção. "Abrir no 3D" leva aos modelos atuais, com o painel de
 *  conflitos aberto no conjunto da última detecção. */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, formatarData } from "./api";

interface Resumo {
  abertos: number;
  novos: number;
  aprovados: number;
  resolvidos: number;
  pares: { disciplina_a: string; disciplina_b: string; novo: number; ativo: number; aprovado: number; resolvido: number }[];
  documentos: { documento_id: number; codigo: string; titulo: string | null; disciplina: string; abertos: number; novos: number }[];
  ultima_deteccao: { feita_em: string; feita_por: string | null; conjunto_id: number; conjunto: string; pronto: string | null } | null;
  arquivos_3d: number[];
}

export default function QuadroConflitos({ obraId }: { obraId: number }) {
  const [resumo, setResumo] = useState<Resumo | null>(null);

  useEffect(() => {
    let vivo = true;
    api
      .get<Resumo>(`/obras/${obraId}/conflitos/resumo`)
      .then((r) => vivo && setResumo(r))
      // Sem acesso (o comercial não vê) ou sem nada: o quadro não aparece.
      .catch(() => vivo && setResumo(null));
    return () => {
      vivo = false;
    };
  }, [obraId]);

  if (!resumo || resumo.abertos + resumo.aprovados + resumo.resolvidos === 0) return null;

  const ultima = resumo.ultima_deteccao;
  const conjunto = ultima ? (ultima.pronto ? `pronto-${ultima.pronto}` : `s${ultima.conjunto_id}`) : null;
  const link3d = resumo.arquivos_3d.length
    ? `/modelos?arquivos=${resumo.arquivos_3d.join(",")}&conflitos=1${conjunto ? `&conjunto=${conjunto}` : ""}`
    : null;
  const pares = resumo.pares.filter((p) => p.novo + p.ativo > 0);

  return (
    <section className="quadro-conflitos" aria-label="Conflitos entre disciplinas">
      <div className="linha" style={{ alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <div className="quadro-conflitos-total">
          <span className="rotulo">Conflitos entre disciplinas</span>
          <strong>{resumo.abertos}</strong>
          <span>
            {resumo.abertos === 1 ? "aberto" : "abertos"}
            {resumo.novos > 0 && (
              <>
                {" "}
                <span className="situacao-conflito novo">{resumo.novos} novos</span>
              </>
            )}
          </span>
          <span className="silencioso" style={{ fontSize: 12 }}>
            {resumo.aprovados} aprovados · {resumo.resolvidos} resolvidos
          </span>
        </div>

        {pares.length > 0 && (
          <ul className="quadro-conflitos-pares">
            {pares.map((p) => (
              <li key={`${p.disciplina_a}-${p.disciplina_b}`}>
                <span className="mono">
                  {p.disciplina_a} × {p.disciplina_b}
                </span>
                <b>{p.novo + p.ativo}</b>
                {p.novo > 0 && <span className="silencioso"> ({p.novo} novos)</span>}
              </li>
            ))}
          </ul>
        )}

        {resumo.documentos.length > 0 && (
          <div className="quadro-conflitos-docs">
            <span className="rotulo">Documentos com mais conflitos abertos</span>
            <ul>
              {resumo.documentos.slice(0, 6).map((d) => (
                <li key={d.documento_id}>
                  <Link to={`/documentos/${d.documento_id}`} className="mono">
                    {d.codigo}
                  </Link>
                  <span className="silencioso"> · {d.abertos}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="espaco" />
        <div className="quadro-conflitos-acoes">
          {link3d && (
            <Link className="botao pequeno" to={link3d}>
              Abrir no 3D
            </Link>
          )}
          {ultima && (
            <span className="silencioso" style={{ fontSize: 11.5 }}>
              Última detecção: {formatarData(ultima.feita_em)}
              {ultima.feita_por && `, por ${ultima.feita_por}`} · {ultima.conjunto}
            </span>
          )}
        </div>
      </div>
    </section>
  );
}
