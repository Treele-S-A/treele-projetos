"""Popula o sistema com uma obra de demonstração.

Serve para avaliar o fluxo com a equipe antes de migrar o acervo real. Usa só a
biblioteca padrão e fala com a API pública — nada de acesso direto ao banco.

    python scripts/dados_demo.py
    python scripts/dados_demo.py --api http://localhost:8000 --obra TRL002

Os arquivos são de brinquedo (poucos bytes com o cabeçalho certo de cada
formato). O objetivo é exercitar nomenclatura, regra de companheiro,
liberação e obsolescência — não o desempenho com arquivos grandes.
"""

import argparse
import json
import os
import urllib.error
import urllib.request

CABECALHOS = {
    "dwg": b"AC1032\x00\x00\x00\x00",
    "rvt": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
    "pdf": b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n",
    "ifc": b"ISO-10303-21;\nHEADER;\n",
}

# (disciplina, fase, sequencial, titulo, formatos, revisoes_a_liberar)
DOCUMENTOS = [
    ("ARQ", "PE", "001", "Planta Pav Terreo", ["dwg", "pdf"], ["00", "01"]),
    ("ARQ", "PE", "002", "Planta Pav Tipo", ["dwg", "pdf"], ["00"]),
    ("ARQ", "PE", "003", "Cortes AA e BB", ["dwg", "pdf"], ["00", "01", "02"]),
    ("ARQ", "PE", "010", "Modelo Federado Arquitetura", ["rvt", "ifc"], ["00"]),
    ("EST", "PE", "001", "Forma Pav Tipo", ["dwg", "pdf"], ["00", "01"]),
    ("EST", "PE", "002", "Armacao Vigas Pav Tipo", ["dwg", "pdf"], ["00"]),
    ("EST", "PB", "001", "Concepcao Estrutural", ["pdf"], ["00"]),
    ("HID", "PE", "001", "Agua Fria Pav Tipo", ["dwg", "pdf"], ["00"]),
    ("HID", "PE", "002", "Esgoto Pav Tipo", ["dwg", "pdf"], []),
    ("ELE", "PE", "001", "Pontos Eletricos Pav Tipo", ["dwg", "pdf"], ["00"]),
    ("ELE", "PE", "002", "Diagrama Unifilar", ["pdf"], ["00"]),
    ("PCI", "PE", "001", "Hidrantes e Extintores", ["dwg", "pdf"], []),
    ("COO", "PE", "001", "Modelo Federado Geral", ["ifc"], ["00"]),
]

DESCRICOES = [
    "Emissão inicial para obra.",
    "Ajuste de compatibilização com a estrutura no eixo 4.",
    "Revisão das cotas do hall e correção da paginação de piso.",
]


class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.token: str | None = None

    def _chamar(self, metodo: str, caminho: str, corpo=None, cru: bytes | None = None,
                content_type: str | None = None, url_absoluta: str | None = None):
        url = url_absoluta or f"{self.base}{caminho}"
        dados = cru if cru is not None else (
            json.dumps(corpo).encode("utf-8") if corpo is not None else None
        )
        req = urllib.request.Request(url, data=dados, method=metodo)
        if content_type:
            req.add_header("Content-Type", content_type)
        elif corpo is not None:
            req.add_header("Content-Type", "application/json")
        if self.token and url_absoluta is None:
            req.add_header("Authorization", f"Bearer {self.token}")

        try:
            with urllib.request.urlopen(req) as r:
                conteudo = r.read()
                return json.loads(conteudo) if conteudo else None
        except urllib.error.HTTPError as e:
            detalhe = e.read().decode("utf-8", "replace")
            raise SystemExit(f"\n{metodo} {url}\n  HTTP {e.code}: {detalhe}\n") from None
        except urllib.error.URLError as e:
            raise SystemExit(
                f"\nNão consegui falar com a API em {self.base}.\n"
                f"  A API está rodando?  ({e.reason})\n"
            ) from None

    def entrar(self, email: str, senha: str):
        r = self._chamar("POST", "/auth/login", {"email": email, "senha": senha})
        self.token = r["token"]

    def get(self, c):
        return self._chamar("GET", c)

    def post(self, c, corpo=None):
        return self._chamar("POST", c, corpo)

    def patch(self, c, corpo=None):
        return self._chamar("PATCH", c, corpo)


def enviar(api: Api, obra_id: int, nome: str, conteudo: bytes) -> dict:
    inicio = api.post(
        f"/obras/{obra_id}/uploads/iniciar",
        {
            "nome_arquivo": nome,
            "tamanho": len(conteudo),
            "content_type": "application/octet-stream",
            "substituir": True,
        },
    )
    api._chamar(
        inicio["metodo"],
        "",
        cru=conteudo,
        content_type=inicio["headers"].get("Content-Type", "application/octet-stream"),
        url_absoluta=inicio["url"],
    )
    api.post(f"/arquivos/{inicio['arquivo_id']}/confirmar")
    return inicio


def principal():
    p = argparse.ArgumentParser()
    # 127.0.0.1 em vez de localhost: no Windows o localhost tenta ::1 primeiro e
    # cada requisição espera ~2,3 s até cair para IPv4.
    p.add_argument("--api", default=os.environ.get("BASE_URL", "http://127.0.0.1:8000"))
    p.add_argument("--email", default=os.environ.get("ADMIN_EMAIL", "admin@treele.com.br"))
    p.add_argument("--senha", default=os.environ.get("ADMIN_SENHA", "treele-dev-2026"))
    p.add_argument("--obra", default="TRL001")
    p.add_argument("--nome-obra", default="Residencial Aurora")
    args = p.parse_args()

    api = Api(args.api)
    api.entrar(args.email, args.senha)
    print(f"Conectado em {args.api} como {args.email}")

    obras = api.get("/obras")
    obra = next((o for o in obras if o["codigo"] == args.obra.upper()), None)
    if obra is None:
        obra = api.post(
            "/obras",
            {
                "codigo": args.obra.upper(),
                "nome": args.nome_obra,
                "cliente": "Construtora Exemplo",
            },
        )
        print(f"Obra {obra['codigo']} criada.")
    else:
        print(f"Obra {obra['codigo']} já existia — complementando.")

    obra_id = obra["id"]
    codigo = obra["codigo"]
    enviados = liberados = 0

    # Não mexe no que já está no acervo: revisão liberada é imutável, e reenviar
    # nela seria recusado pela API (corretamente).
    ja_existem = {
        d["codigo"]
        for d in api.get(f"/obras/{obra_id}/documentos?por_pagina=200")["itens"]
    }

    for disciplina, fase, seq, titulo, formatos, liberar in DOCUMENTOS:
        if f"{codigo}-{disciplina}-{fase}-{seq}" in ja_existem:
            print(f"  {codigo}-{disciplina}-{fase}-{seq}  (já existe, pulando)")
            continue

        revisoes = sorted({*liberar, "00"})
        documento_id = None
        for rev in revisoes:
            revisao_id = None
            for formato in formatos:
                nome = f"{codigo}-{disciplina}-{fase}-{seq}-R{rev}.{formato}"
                corpo = CABECALHOS[formato] + f"{titulo} R{rev}".encode() + b"\n" * 64
                r = enviar(api, obra_id, nome, corpo)
                revisao_id = r["revisao_id"]
                documento_id = r["documento_id"]
                enviados += 1

            # O template padrão não tem campo de título, então ele é preenchido
            # à parte — é o que a equipe faria pela interface.
            if documento_id and rev == revisoes[0]:
                api.patch(f"/documentos/{documento_id}", {"titulo": titulo})

            if rev in liberar and revisao_id:
                api.post(
                    f"/revisoes/{revisao_id}/publicar",
                    {"descricao": DESCRICOES[min(int(rev), len(DESCRICOES) - 1)]},
                )
                liberados += 1

        print(f"  {codigo}-{disciplina}-{fase}-{seq}  {titulo}")

    print(
        f"\nPronto. {enviados} arquivos enviados, {liberados} revisões liberadas para obra."
        f"\nAbra o sistema e entre como {args.email}.\n"
    )


if __name__ == "__main__":
    principal()
