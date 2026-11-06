"""Erros de validação em português (TREELE, 04/11/2026).

O FastAPI responde 422 com o texto do Pydantic, em inglês, e a tela mostrava
isso como veio: "String should have at least 8 characters". A resposta também
trazia de volta o valor digitado, inclusive a senha. Aqui sai só o que a pessoa
precisa ler, com o nome do campo como ele aparece nas telas.
"""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

NOMES = {
    "email": "E-mail",
    "senha": "Senha",
    "senha_atual": "Senha atual",
    "senha_nova": "Senha nova",
    "nome": "Nome",
    "codigo": "Código",
    "endereco": "Endereço",
    "razao_social": "Razão social",
    "nome_fantasia": "Nome fantasia",
    "cnpj": "CNPJ",
    "cod_sienge": "Código Sienge",
    "telefone": "Telefone",
    "contato": "Contato",
    "empresa": "Empresa",
    "titulo": "Título",
    "descricao": "Descrição",
    "motivo": "Motivo",
    "justificativa": "Justificativa",
    "observacao": "Observação",
    "observacoes": "Observações",
    "comentario": "Comentário",
    "nome_arquivo": "Nome do arquivo",
    "data": "Data",
    "inicio": "Início",
    "duracao": "Duração",
    "fase": "Fase",
    "area": "Área",
    "responsavel": "Responsável",
    "disciplinas": "Disciplinas",
    "obras": "Obras",
    "funcao": "Função",
    "papel": "Papel",
    "qualidade": "Qualidade",
    "documentacao": "Documentação",
    "prazo": "Prazo",
    "atendimento": "Atendimento",
    "empreendimento": "Empreendimento",
    "escopo": "Escopo",
}

DATAS = {"date_parsing", "date_type", "date_from_datetime_parsing", "date_from_datetime_inexact",
         "datetime_parsing", "datetime_type", "datetime_from_date_parsing"}
NUMEROS = {"int_parsing", "int_type", "int_from_float", "float_parsing", "float_type", "decimal_parsing", "decimal_type"}


def _nome_do_campo(loc: tuple) -> str:
    # O último texto do caminho: ("body", "respostas", 3, "comentario") é "comentario".
    campo = next((str(p) for p in reversed(loc) if isinstance(p, str) and p not in ("body", "query", "path")), "")
    if not campo:
        return "Campo"
    return NOMES.get(campo, campo.replace("_", " ").capitalize())


def _quantidade(n: object, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def mensagem(erro: dict) -> str:
    tipo = erro.get("type", "")
    ctx = erro.get("ctx") or {}
    campo = _nome_do_campo(tuple(erro.get("loc") or ()))

    if tipo == "missing":
        return f"{campo}: preenchimento obrigatório."
    if tipo == "string_too_short":
        minimo = ctx.get("min_length", 1)
        if minimo == 1:
            return f"{campo}: preenchimento obrigatório."
        return f"{campo}: precisa ter pelo menos {_quantidade(minimo, 'caractere', 'caracteres')}."
    if tipo == "string_too_long":
        return f"{campo}: pode ter no máximo {_quantidade(ctx.get('max_length'), 'caractere', 'caracteres')}."
    if tipo == "too_short":
        return f"{campo}: escolha pelo menos {_quantidade(ctx.get('min_length', 1), 'item', 'itens')}."
    if tipo == "too_long":
        return f"{campo}: são no máximo {_quantidade(ctx.get('max_length'), 'item', 'itens')}."
    if tipo == "greater_than_equal":
        return f"{campo}: o mínimo é {ctx.get('ge')}."
    if tipo == "greater_than":
        return f"{campo}: precisa ser maior que {ctx.get('gt')}."
    if tipo == "less_than_equal":
        return f"{campo}: o máximo é {ctx.get('le')}."
    if tipo == "less_than":
        return f"{campo}: precisa ser menor que {ctx.get('lt')}."
    if tipo in NUMEROS:
        return f"{campo}: precisa ser um número."
    if tipo in DATAS:
        return f"{campo}: data inválida."
    if tipo in ("literal_error", "enum"):
        return f"{campo}: opção inválida."
    if tipo == "json_invalid":
        return "O pedido chegou com formato inválido."
    if tipo == "value_error":
        texto = str(erro.get("msg", ""))
        if "email address" in texto:
            return "E-mail inválido: confira se está completo, como nome@empresa.com.br."
        # As mensagens dos nossos validadores já são em português.
        return texto.removeprefix("Value error, ")
    return f"{campo}: valor inválido."


async def tratar_validacao(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Sem "input" e sem "ctx": a resposta não devolve o que foi digitado.
    detalhe = [
        {"type": e.get("type"), "loc": list(e.get("loc") or ()), "msg": mensagem(e)}
        for e in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": detalhe})
