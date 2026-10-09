import { useId, useState, type CSSProperties, type ReactNode } from "react";
import { ROTULO_STATUS, type Obra, type StatusRevisao } from "./api";

/** Servido pela própria aplicação (frontend/public). */
export const SIMBOLO = "/simbolo-treele.png";

/** A cor de identidade da obra vira variável CSS: o degradê, o brilho e a
 *  marca d'água saem dela no CSS. Sem cor, o CSS cai no petróleo. */
export function estiloDaObra(obra?: Pick<Obra, "cor"> | null): CSSProperties | undefined {
  return obra?.cor ? ({ "--cor-obra": obra.cor } as CSSProperties) : undefined;
}

/**
 * Capa da obra: faixa na cor do empreendimento, logo num selo claro e o logo
 * de novo, grande e apagado, como a estampa dos painéis da treèle.
 */
export function CapaObra({
  obra,
  children,
  className = "",
}: {
  obra: Pick<Obra, "cor" | "logo_url">;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`capa-obra ${className}`} style={estiloDaObra(obra)}>
      <span className="capa-fundo" aria-hidden="true" />
      {obra.logo_url && (
        <img className="capa-estampa" src={obra.logo_url} alt="" aria-hidden="true" />
      )}
      <span className="selo-logo">
        <LogoObra obra={obra} reserva={<img className="sem-logo" src={SIMBOLO} alt="" />} />
      </span>
      {children}
    </div>
  );
}

/**
 * Logo do empreendimento, ou a reserva quando não há — ou quando o endereço
 * assinado venceu (aba aberta há mais de 12 h). Imagem quebrada nunca aparece.
 */
export function LogoObra({
  obra,
  className,
  alt = "",
  reserva = null,
}: {
  obra: Pick<Obra, "logo_url">;
  className?: string;
  alt?: string;
  reserva?: ReactNode;
}) {
  // Guarda QUAL endereço falhou: trocar o logo traz um endereço novo, e ele
  // merece nova chance.
  const [falhou, setFalhou] = useState<string | null>(null);
  if (!obra.logo_url || falhou === obra.logo_url) return <>{reserva}</>;
  return (
    <img
      className={className}
      src={obra.logo_url}
      alt={alt}
      onError={() => setFalhou(obra.logo_url)}
    />
  );
}

export function Rotulo({ children }: { children: ReactNode }) {
  return <span className="rotulo">{children}</span>;
}

export function Estado({ status }: { status: StatusRevisao }) {
  return <span className={`estado estado-${status}`}>{ROTULO_STATUS[status]}</span>;
}

/** O que corre no arco de baixo. Curto de propósito: um carimbo se lê de
 *  relance, e texto comprido no arco vira letra espremida. */
const TEXTO_SELO: Record<StatusRevisao, string> = {
  liberado_para_obra: "Liberado para obra",
  em_revisao: "Em revisão",
  obsoleto: "Obsoleto",
  cancelado: "Cancelado",
  reprovado: "Reprovada",
};

/**
 * O carimbo de liberação — redondo, como o de borracha que a construtora bate
 * na prancha. Nome da treèle no arco de cima, o estado no de baixo (os dois de
 * pé, como num selo de verdade), o símbolo e a revisão no centro. Um por tela,
 * na revisão em destaque.
 */
export function Selo({
  status,
  numero,
  data,
}: {
  status: StatusRevisao;
  numero?: string;
  data?: string | null;
}) {
  // Um id por carimbo: os arcos do texto são referenciados por id, e dois
  // carimbos na mesma página não podem disputar o mesmo.
  const id = useId();
  const topo = `${id}-topo`;
  const base = `${id}-base`;

  // Embaixo do número: a data da liberação, ou o aviso que o obsoleto exige.
  const nota = status === "obsoleto" ? "Não executar" : data;

  const legenda = [
    numero ? `Revisão R${numero}` : "Revisão",
    TEXTO_SELO[status].toLowerCase(),
    status === "obsoleto" ? "não executar" : data ? `em ${data}` : null,
  ]
    .filter(Boolean)
    .join(" — ");

  return (
    <div className={`selo selo-${status}`} role="img" aria-label={legenda}>
      <svg viewBox="0 0 160 160" aria-hidden="true">
        <defs>
          {/* A faixa de texto vai do anel r=52 ao r=72; o meio dela é r=62.
              Por cima, horário: as letras ficam de pé para fora, então a base
              da linha fica abaixo do meio. Por baixo, anti-horário: de pé
              para dentro, base acima do meio. */}
          <path id={topo} d="M 22.5 80 A 57.5 57.5 0 0 1 137.5 80" />
          <path id={base} d="M 13.5 80 A 66.5 66.5 0 0 0 146.5 80" />
        </defs>
        <circle cx="80" cy="80" r="77" fill="none" stroke="currentColor" strokeWidth="3" />
        <circle cx="80" cy="80" r="72" fill="none" stroke="currentColor" strokeWidth="1" />
        <circle cx="80" cy="80" r="52" fill="none" stroke="currentColor" strokeWidth="1.2" />
        <circle cx="18" cy="80" r="2.2" fill="currentColor" />
        <circle cx="142" cy="80" r="2.2" fill="currentColor" />
        <text className="selo-texto">
          <textPath href={`#${topo}`} startOffset="50%" textAnchor="middle">
            TREÈLE CONSTRUTORA
          </textPath>
        </text>
        <text className="selo-texto selo-texto-base">
          <textPath href={`#${base}`} startOffset="50%" textAnchor="middle">
            {TEXTO_SELO[status].toUpperCase()}
          </textPath>
        </text>
      </svg>
      <div className="selo-miolo">
        <span className="selo-simbolo" />
        {numero && <span className="selo-rev">R{numero}</span>}
        {nota && <span className="selo-data">{nota}</span>}
      </div>
    </div>
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
  return (
    <div className="carregando" role="status">
      <img src={SIMBOLO} alt="" />
      <span>{texto}…</span>
    </div>
  );
}

export function CampoCarimbo({ rotulo, valor }: { rotulo: string; valor: ReactNode }) {
  return (
    <div className="carimbo-campo">
      <Rotulo>{rotulo}</Rotulo>
      <div className="valor">{valor ?? "—"}</div>
    </div>
  );
}
