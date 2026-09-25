/**
 * Preparo do logo no navegador, antes de enviar.
 *
 * Duas coisas acontecem aqui, e as duas são pelo resultado na tela, não pelo
 * servidor: a imagem é reduzida (lado maior de 640 px — o logo nunca aparece
 * maior que isso, e quem está na obra baixa pelo 4G) e as margens vazias são
 * cortadas. Arquivo de logo costuma vir com muita sobra transparente em volta,
 * e no cartão da obra isso vira um logo minúsculo no meio de um branco.
 */

const LADO_MAXIMO = 640;
const TIPOS = ["image/png", "image/jpeg", "image/webp"];

/** Pixel conta como "desenho": não é transparente nem branco de fundo. */
function temTinta(r: number, g: number, b: number, a: number): boolean {
  if (a <= 16) return false;
  return !(r > 244 && g > 244 && b > 244);
}

/** Retângulo que contém o desenho, nas coordenadas do canvas medido. */
function contornoDoDesenho(ctx: CanvasRenderingContext2D, largura: number, altura: number) {
  const { data } = ctx.getImageData(0, 0, largura, altura);
  let x0 = largura;
  let y0 = altura;
  let x1 = -1;
  let y1 = -1;
  for (let y = 0; y < altura; y++) {
    for (let x = 0; x < largura; x++) {
      const i = (y * largura + x) * 4;
      if (temTinta(data[i], data[i + 1], data[i + 2], data[i + 3])) {
        if (x < x0) x0 = x;
        if (x > x1) x1 = x;
        if (y < y0) y0 = y;
        if (y > y1) y1 = y;
      }
    }
  }
  // Imagem toda vazia (ou toda branca): não há o que cortar.
  if (x1 < 0) return { x: 0, y: 0, largura, altura };
  return { x: x0, y: y0, largura: x1 - x0 + 1, altura: y1 - y0 + 1 };
}

function novoCanvas(largura: number, altura: number) {
  const tela = document.createElement("canvas");
  tela.width = largura;
  tela.height = altura;
  const ctx = tela.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("Este navegador não conseguiu preparar a imagem.");
  ctx.imageSmoothingQuality = "high";
  return { tela, ctx };
}

export async function prepararLogo(arquivo: File): Promise<Blob> {
  if (!TIPOS.includes(arquivo.type)) {
    throw new Error("Escolha uma imagem PNG, JPG ou WebP. SVG não é aceito.");
  }

  let imagem: ImageBitmap;
  try {
    imagem = await createImageBitmap(arquivo);
  } catch {
    throw new Error("Não foi possível abrir esta imagem. O arquivo pode estar corrompido.");
  }

  // Mede o contorno numa versão reduzida (rápido), depois corta no original
  // (nítido): cortar a versão reduzida perderia resolução justamente nos
  // logos que têm mais margem.
  const escalaMedida = Math.min(1, LADO_MAXIMO / Math.max(imagem.width, imagem.height));
  const lm = Math.max(1, Math.round(imagem.width * escalaMedida));
  const am = Math.max(1, Math.round(imagem.height * escalaMedida));
  const medida = novoCanvas(lm, am);
  medida.ctx.drawImage(imagem, 0, 0, lm, am);
  const c = contornoDoDesenho(medida.ctx, lm, am);

  // Uma pequena folga em volta, para o desenho não encostar na borda.
  const folga = Math.round(Math.max(c.largura, c.altura) * 0.03);
  const sx = Math.max(0, (c.x - folga) / escalaMedida);
  const sy = Math.max(0, (c.y - folga) / escalaMedida);
  const sl = Math.min(imagem.width - sx, (c.largura + 2 * folga) / escalaMedida);
  const sa = Math.min(imagem.height - sy, (c.altura + 2 * folga) / escalaMedida);

  const escala = Math.min(1, LADO_MAXIMO / Math.max(sl, sa));
  const final = novoCanvas(Math.max(1, Math.round(sl * escala)), Math.max(1, Math.round(sa * escala)));
  final.ctx.drawImage(imagem, sx, sy, sl, sa, 0, 0, final.tela.width, final.tela.height);
  imagem.close();

  // JPEG continua JPEG: não tem transparência a preservar e sai bem menor.
  // O resto vira PNG, que guarda o fundo transparente.
  const tipo = arquivo.type === "image/jpeg" ? "image/jpeg" : "image/png";
  const blob = await new Promise<Blob | null>((ok) => final.tela.toBlob(ok, tipo, 0.9));
  if (!blob) throw new Error("Não foi possível preparar a imagem.");
  return blob;
}
