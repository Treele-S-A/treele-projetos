"""O e-mail com a cara da Treèle (06/10/2026).

HTML de e-mail não é HTML de site: Outlook desenha com o motor do Word, Gmail
corta <style> em várias situações. Por isso tabela para o layout, estilo
inline em tudo, fonte de sistema e o botão feito de tabela pintada — o jeito
que aparece igual em todo lugar. O símbolo vai dentro da mensagem (imagem
relacionada, "cid:"), não por link: programa que bloqueia imagem de fora
mostra mesmo assim.

A versão em texto puro continua indo junto, para quem lê sem HTML.
"""

from dataclasses import dataclass
from html import escape
from pathlib import Path

SIMBOLO = Path(__file__).resolve().parent.parent / "recursos" / "simbolo-email.png"

FONTE = "'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
TINTA = "#22312f"
TINTA_2 = "#5b6866"
PETROLEO = "#2f4c52"
NEVOA = "#f3efe6"
TRACO = "#ebe5d8"


@dataclass(frozen=True)
class Selo:
    rotulo: str
    cor: str
    fundo: str


# O que gerou o aviso, com as cores dos status da interface.
SELOS = {
    "solicitacao_revisao": Selo("Revisão solicitada", "#84590d", "#fdf0cc"),
    "revisao_autorizada": Selo("Revisão autorizada", PETROLEO, "#e3ebec"),
    "solicitacao_recusada": Selo("Revisão não autorizada", "#a23d27", "#f6e3de"),
    "revisao_enviada": Selo("Revisão enviada", "#2f6f7c", "#e1eef1"),
    "revisao_liberada": Selo("Liberada para obra", "#3d7330", "#e4eedf"),
    "revisao_reprovada": Selo("Revisão reprovada", "#a23d27", "#f6e3de"),
    "avaliacao_chat": Selo("Chat · 👎", "#a23d27", "#f6e3de"),
    "teste": Selo("Teste de e-mail", PETROLEO, "#e3ebec"),
}


def _paragrafos(texto: str) -> str:
    """O texto do aviso em blocos. Bloco que começa com "Rótulo:" vira rótulo
    pequeno e citação — é como "O que deve mudar:" e "Motivo:" se destacam."""
    partes = []
    for bloco in texto.strip().split("\n\n"):
        primeira, _, resto = bloco.partition("\n")
        if primeira.endswith(":") and resto:
            partes.append(
                f'<p style="margin:18px 0 6px;font-size:11px;letter-spacing:.08em;'
                f'text-transform:uppercase;font-weight:700;color:{TINTA_2};">'
                f"{escape(primeira[:-1])}</p>"
                f'<p style="margin:0 0 16px;padding:10px 14px;border-left:3px solid {TRACO};'
                f'background:#faf8f3;font-size:14px;line-height:1.55;color:{TINTA};">'
                f'{escape(resto).replace(chr(10), "<br>")}</p>'
            )
        else:
            partes.append(
                f'<p style="margin:0 0 12px;font-size:15px;line-height:1.6;color:{TINTA};">'
                f'{escape(bloco).replace(chr(10), "<br>")}</p>'
            )
    return "".join(partes)


def html(
    *,
    tipo: str,
    saudacao: str,
    titulo: str,
    texto: str,
    obra: str,
    subtitulo: str | None = None,
    cor_obra: str | None,
    link: str,
    rotulo_botao: str = "Abrir documento",
    cid_simbolo: str,
) -> str:
    selo = SELOS.get(tipo, SELOS["teste"])
    acento = cor_obra or PETROLEO
    # Prévia que o programa de e-mail mostra ao lado do assunto.
    previa = escape(texto.strip().split("\n")[0][:140])
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>{escape(titulo)}</title>
</head>
<body style="margin:0;padding:0;background:{NEVOA};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{previa}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{NEVOA};">
<tr><td align="center" style="padding:28px 12px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;font-family:{FONTE};">

<tr><td style="background:{PETROLEO};border-radius:14px 14px 0 0;padding:18px 26px;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
<td width="40" height="40" style="width:40px;height:40px;background:#ffffff;border-radius:50%;text-align:center;vertical-align:middle;">
<img src="cid:{cid_simbolo}" width="32" height="32" alt="" style="display:block;margin:4px auto;border:0;">
</td>
<td style="width:12px;"></td>
<td style="vertical-align:middle;">
<div style="font-size:18px;font-weight:700;color:#ffffff;line-height:1.1;">Projetos</div>
<div style="font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:#b9cbcd;margin-top:3px;">Treèle Construtora</div>
</td>
</tr></table>
</td></tr>

<tr><td style="font-size:0;line-height:0;height:4px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
<td width="33%" style="height:4px;background:#7cb93c;"></td>
<td width="34%" style="height:4px;background:#1ba0e1;"></td>
<td width="33%" style="height:4px;background:#f7b616;"></td>
</tr></table>
</td></tr>

<tr><td style="background:#ffffff;border-left:4px solid {acento};padding:28px 30px 30px;border-radius:0 0 14px 14px;">
<p style="margin:0 0 14px;">
<span style="display:inline-block;padding:4px 11px;border-radius:999px;background:{selo.fundo};color:{selo.cor};font-size:11px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;">{escape(selo.rotulo)}</span>
</p>
<p style="margin:0 0 4px;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:{TINTA_2};font-weight:600;">{escape(obra)}</p>
<h1 style="margin:0 0 {"4px" if subtitulo else "20px"};font-size:22px;line-height:1.3;color:{TINTA};font-weight:700;">{escape(titulo)}</h1>
{f'<p style="margin:0 0 20px;font-family:Consolas,Menlo,monospace;font-size:13px;color:{TINTA_2};">{escape(subtitulo)}</p>' if subtitulo else ""}
<p style="margin:0 0 12px;font-size:15px;line-height:1.6;color:{TINTA};">{escape(saudacao)}</p>
{_paragrafos(texto)}
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin-top:24px;"><tr>
<td style="background:{PETROLEO};border-radius:9px;">
<a href="{escape(link, quote=True)}" style="display:inline-block;padding:13px 26px;font-family:{FONTE};font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;border-radius:9px;">{escape(rotulo_botao)} &rarr;</a>
</td>
</tr></table>
<p style="margin:14px 0 0;font-size:12px;line-height:1.5;color:{TINTA_2};">Se o botão não abrir, copie o endereço:<br><a href="{escape(link, quote=True)}" style="color:#2f6f7c;word-break:break-all;">{escape(link)}</a></p>
</td></tr>

<tr><td style="padding:18px 30px 0;font-size:12px;line-height:1.5;color:{TINTA_2};text-align:center;">
Aviso automático do sistema de projetos da Treèle Construtora. Não responda este e-mail.
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""
