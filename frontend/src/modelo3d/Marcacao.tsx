/** Marcações sobre a foto do modelo 3D (TREELE, 21/10/2026): caneta, seta,
 *  retângulo, elipse e texto, em cores fortes, com desfazer. O resultado é um
 *  PNG com a foto e as marcações juntas — o que o projetista vai ver. */

import { useEffect, useRef, useState, type PointerEvent } from "react";

type Ferramenta = "caneta" | "seta" | "retangulo" | "elipse" | "texto";
type Ponto = { x: number; y: number };
type Forma =
  | { tipo: "caneta"; cor: string; pontos: Ponto[] }
  | { tipo: "seta" | "retangulo" | "elipse"; cor: string; a: Ponto; b: Ponto }
  | { tipo: "texto"; cor: string; a: Ponto; texto: string };

const CORES = [
  { valor: "#e11d2e", nome: "Vermelho" },
  { valor: "#f59e0b", nome: "Amarelo" },
  { valor: "#2563eb", nome: "Azul" },
  { valor: "#111827", nome: "Preto" },
];
const FERRAMENTAS: { valor: Ferramenta; nome: string; icone: string }[] = [
  { valor: "caneta", nome: "Caneta", icone: "✎" },
  { valor: "seta", nome: "Seta", icone: "↗" },
  { valor: "retangulo", nome: "Retângulo", icone: "▭" },
  { valor: "elipse", nome: "Elipse", icone: "◯" },
  { valor: "texto", nome: "Texto", icone: "T" },
];

function desenhar(ctx: CanvasRenderingContext2D, forma: Forma, espessura: number) {
  ctx.strokeStyle = forma.cor;
  ctx.fillStyle = forma.cor;
  ctx.lineWidth = espessura;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.beginPath();
  switch (forma.tipo) {
    case "caneta":
      forma.pontos.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
      ctx.stroke();
      break;
    case "retangulo":
      ctx.strokeRect(forma.a.x, forma.a.y, forma.b.x - forma.a.x, forma.b.y - forma.a.y);
      break;
    case "elipse":
      ctx.ellipse(
        (forma.a.x + forma.b.x) / 2,
        (forma.a.y + forma.b.y) / 2,
        Math.abs(forma.b.x - forma.a.x) / 2,
        Math.abs(forma.b.y - forma.a.y) / 2,
        0,
        0,
        Math.PI * 2,
      );
      ctx.stroke();
      break;
    case "seta": {
      const { a, b } = forma;
      const ang = Math.atan2(b.y - a.y, b.x - a.x);
      const ponta = espessura * 5;
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(b.x, b.y);
      ctx.lineTo(b.x - ponta * Math.cos(ang - 0.45), b.y - ponta * Math.sin(ang - 0.45));
      ctx.lineTo(b.x - ponta * Math.cos(ang + 0.45), b.y - ponta * Math.sin(ang + 0.45));
      ctx.closePath();
      ctx.fill();
      break;
    }
    case "texto": {
      const tamanho = espessura * 7;
      ctx.font = `600 ${tamanho}px system-ui, sans-serif`;
      ctx.textBaseline = "top";
      // Contorno branco para ler sobre qualquer fundo.
      ctx.lineWidth = espessura * 1.6;
      ctx.strokeStyle = "#ffffff";
      ctx.strokeText(forma.texto, forma.a.x, forma.a.y);
      ctx.fillText(forma.texto, forma.a.x, forma.a.y);
      break;
    }
  }
}

export interface Gerador {
  foto: () => Promise<Blob>;
  marcacoes: () => Promise<Blob | null>;
}

function paraPng(c: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolver, rejeitar) =>
    c.toBlob((b) => (b ? resolver(b) : rejeitar(new Error("Sem imagem."))), "image/png"),
  );
}

export default function Marcacao({
  imagem,
  aoMudar,
}: {
  imagem: Blob;
  /** Chamado a cada mudança: a foto com os desenhos e, sem a foto, só os
   *  desenhos (null se não houver nenhum) — esses voltam na cena 3D. */
  aoMudar: (gerar: Gerador) => void;
}) {
  const tela = useRef<HTMLCanvasElement>(null);
  const [foto, setFoto] = useState<HTMLImageElement | null>(null);
  const [formas, setFormas] = useState<Forma[]>([]);
  const [rascunho, setRascunho] = useState<Forma | null>(null);
  const [ferramenta, setFerramenta] = useState<Ferramenta>("elipse");
  const [cor, setCor] = useState(CORES[0].valor);
  const [texto, setTexto] = useState("");

  useEffect(() => {
    const url = URL.createObjectURL(imagem);
    const img = new Image();
    img.onload = () => setFoto(img);
    img.src = url;
    return () => URL.revokeObjectURL(url);
  }, [imagem]);

  // Grossa o bastante para ver de longe, em qualquer resolução da foto.
  const espessura = foto ? Math.max(4, Math.round(Math.max(foto.naturalWidth, foto.naturalHeight) / 160)) : 4;

  useEffect(() => {
    const c = tela.current;
    if (!c || !foto) return;
    c.width = foto.naturalWidth;
    c.height = foto.naturalHeight;
    const ctx = c.getContext("2d")!;
    ctx.drawImage(foto, 0, 0);
    for (const f of formas) desenhar(ctx, f, espessura);
    if (rascunho) desenhar(ctx, rascunho, espessura);
  }, [foto, formas, rascunho, espessura]);

  useEffect(() => {
    aoMudar({
      foto: () => paraPng(tela.current!),
      marcacoes: async () => {
        if (!foto || !formas.length) return null;
        const c = document.createElement("canvas");
        c.width = foto.naturalWidth;
        c.height = foto.naturalHeight;
        const ctx = c.getContext("2d")!;
        for (const f of formas) desenhar(ctx, f, espessura);
        return paraPng(c);
      },
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [formas, foto, espessura]);

  function ponto(e: PointerEvent<HTMLCanvasElement>): Ponto {
    const r = e.currentTarget.getBoundingClientRect();
    return {
      x: ((e.clientX - r.left) / r.width) * e.currentTarget.width,
      y: ((e.clientY - r.top) / r.height) * e.currentTarget.height,
    };
  }

  function inicio(e: PointerEvent<HTMLCanvasElement>) {
    const p = ponto(e);
    if (ferramenta === "texto") {
      if (texto.trim()) setFormas((fs) => [...fs, { tipo: "texto", cor, a: p, texto: texto.trim() }]);
      return;
    }
    e.currentTarget.setPointerCapture(e.pointerId);
    setRascunho(
      ferramenta === "caneta" ? { tipo: "caneta", cor, pontos: [p] } : { tipo: ferramenta, cor, a: p, b: p },
    );
  }

  function movimento(e: PointerEvent<HTMLCanvasElement>) {
    if (!rascunho) return;
    const p = ponto(e);
    setRascunho(rascunho.tipo === "caneta" ? { ...rascunho, pontos: [...rascunho.pontos, p] } : { ...rascunho, b: p } as Forma);
  }

  function fim() {
    if (rascunho) setFormas((fs) => [...fs, rascunho]);
    setRascunho(null);
  }

  return (
    <div className="marcacao">
      <div className="marcacao-ferramentas" role="toolbar" aria-label="Marcações">
        {FERRAMENTAS.map((f) => (
          <button
            key={f.valor}
            type="button"
            className={ferramenta === f.valor ? "ativo" : undefined}
            aria-pressed={ferramenta === f.valor}
            title={f.nome}
            onClick={() => setFerramenta(f.valor)}
          >
            <span aria-hidden="true">{f.icone}</span> {f.nome}
          </button>
        ))}
        <span className="marcacao-divisor" />
        {CORES.map((c) => (
          <button
            key={c.valor}
            type="button"
            className={`marcacao-cor ${cor === c.valor ? "ativo" : ""}`}
            style={{ background: c.valor }}
            aria-label={c.nome}
            aria-pressed={cor === c.valor}
            title={c.nome}
            onClick={() => setCor(c.valor)}
          />
        ))}
        <span className="marcacao-divisor" />
        <button type="button" disabled={!formas.length} onClick={() => setFormas((fs) => fs.slice(0, -1))}>
          Desfazer
        </button>
        <button type="button" disabled={!formas.length} onClick={() => setFormas([])}>
          Limpar
        </button>
      </div>
      {ferramenta === "texto" && (
        <input
          className="marcacao-texto"
          value={texto}
          maxLength={120}
          onChange={(e) => setTexto(e.target.value)}
          placeholder="Escreva o texto e clique na imagem onde ele vai"
        />
      )}
      <canvas
        ref={tela}
        className={`marcacao-tela ferramenta-${ferramenta}`}
        onPointerDown={inicio}
        onPointerMove={movimento}
        onPointerUp={fim}
        onPointerCancel={fim}
      />
    </div>
  );
}
