import type { ReactNode } from "react";
import { ROTULO_STATUS, type StatusRevisao } from "./api";

export function Rotulo({ children }: { children: ReactNode }) {
  return <span className="rotulo">{children}</span>;
}

export function Estado({ status }: { status: StatusRevisao }) {
  return <span className={`estado estado-${status}`}>{ROTULO_STATUS[status]}</span>;
}

/** O carimbo de borracha. Um por tela, na revisão em destaque. */
export function Selo({ status }: { status: StatusRevisao }) {
  const cor: Record<StatusRevisao, string> = {
    liberado_para_obra: "var(--liberado)",
    em_revisao: "var(--revisao)",
    obsoleto: "var(--obsoleto)",
    cancelado: "var(--cancelado)",
  };
  const texto: Record<StatusRevisao, string> = {
    liberado_para_obra: "Liberado para obra",
    em_revisao: "Em revisão",
    obsoleto: "Obsoleto",
    cancelado: "Cancelado",
  };
  return (
    <span className="selo" style={{ color: cor[status] }}>
      {texto[status]}
    </span>
  );
}

export function Aviso({
  tom = "info",
  titulo,
  itens,
  children,
}: {
  tom?: "erro" | "atencao" | "ok" | "info";
  titulo?: string;
  itens?: string[];
  children?: ReactNode;
}) {
  return (
    <div className={`aviso aviso-${tom}`} role={tom === "erro" ? "alert" : undefined}>
      <div>
        {titulo && <strong>{titulo}</strong>}
        {children}
        {itens && itens.length > 0 && (
          <ul>
            {itens.map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export function Vazio({ titulo, children }: { titulo: string; children?: ReactNode }) {
  return (
    <div className="vazio">
      <strong>{titulo}</strong>
      {children}
    </div>
  );
}

export function Carregando({ texto = "Carregando" }: { texto?: string }) {
  return <div className="carregando">{texto}…</div>;
}

export function CampoCarimbo({ rotulo, valor }: { rotulo: string; valor: ReactNode }) {
  return (
    <div className="carimbo-campo">
      <Rotulo>{rotulo}</Rotulo>
      <div className="valor">{valor ?? "—"}</div>
    </div>
  );
}
