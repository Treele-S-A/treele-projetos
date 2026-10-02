"""Armazenamento dos arquivos.

Regra de arquitetura: o arquivo **nunca** trafega pela API. O navegador recebe
uma URL assinada de curta duração e fala direto com o storage. Sem isso, um DWG
de 800 MB ocupa um worker inteiro no upload e a obra no 4G não baixa nada.

Dois back-ends com a mesma interface:

* ``local``  — grava em disco e assina URLs com HMAC servidas pela própria API.
  Serve para rodar hoje, sem Docker.
* ``s3``     — MinIO (auto-hospedado) ou S3/R2/B2. É o modo de produção.

Trocar de um para o outro é uma variável de ambiente; nenhum outro arquivo muda.
"""

import hashlib
import hmac
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlencode

from ..config import settings

_RE_INSEGURO = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass
class DestinoUpload:
    url: str
    metodo: str
    headers: dict[str, str]
    direto: bool  # True = o navegador envia direto ao storage


def _ascii_seguro(valor: str) -> str:
    nfkd = unicodedata.normalize("NFKD", valor)
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return _RE_INSEGURO.sub("_", sem_acento).strip("._-") or "arquivo"


# Imagem reconhecida pelos primeiros bytes, não pela extensão nem pelo
# Content-Type que o navegador declara — os dois são o remetente dizendo o que
# quer. SVG fica de fora de propósito: é texto, pode carregar script, e aberto
# direto no navegador roda.
_ASSINATURAS_IMAGEM = (
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
)


def detectar_imagem(dados: bytes) -> tuple[str, str] | None:
    """(tipo, extensão) se os bytes forem PNG, JPEG ou WebP; senão None."""
    for assinatura, tipo, extensao in _ASSINATURAS_IMAGEM:
        if dados.startswith(assinatura):
            return tipo, extensao
    if len(dados) >= 12 and dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


def chave_logo(obra_codigo: str, extensao: str) -> str:
    """Chave do logo da obra. Leva um sufixo aleatório: trocar o logo muda o
    endereço, e nenhum navegador fica mostrando o antigo guardado."""
    import secrets

    return "/".join(
        ["obras", _ascii_seguro(obra_codigo), "_marca", f"logo-{secrets.token_hex(6)}.{extensao}"]
    )


def chave_anexo(obra_codigo: str, codigo_documento: str, solicitacao_id: int, nome: str) -> str:
    """Chave do anexo de uma solicitação de revisão. O sufixo aleatório deixa
    dois anexos de mesmo nome (duas fotos "IMG_0001.jpg") conviverem."""
    import secrets

    return "/".join(
        [
            "obras",
            _ascii_seguro(obra_codigo),
            _ascii_seguro(codigo_documento),
            "_solicitacoes",
            str(solicitacao_id),
            f"{secrets.token_hex(4)}-{_ascii_seguro(nome)}",
        ]
    )


def montar_chave(
    obra_codigo: str, codigo_documento: str, revisao: str, nome_arquivo: str
) -> str:
    """Chave do objeto no storage.

    Legível de propósito: se um dia for preciso resgatar tudo sem o sistema,
    a estrutura de pastas do bucket já conta a história.
    """
    return "/".join(
        [
            "obras",
            _ascii_seguro(obra_codigo),
            _ascii_seguro(codigo_documento),
            f"R{_ascii_seguro(revisao)}",
            _ascii_seguro(nome_arquivo),
        ]
    )


class ArmazenamentoLocal:
    def __init__(self) -> None:
        self.raiz = Path(settings.storage_local_dir)
        self.raiz.mkdir(parents=True, exist_ok=True)

    # -- assinatura ------------------------------------------------------
    def _assinar(self, chave: str, acao: str, exp: int) -> str:
        msg = f"{acao}|{chave}|{exp}".encode("utf-8")
        return hmac.new(
            settings.secret_key.encode("utf-8"), msg, hashlib.sha256
        ).hexdigest()

    def conferir_assinatura(self, chave: str, acao: str, exp: int, sig: str) -> bool:
        if exp < int(time.time()):
            return False
        return hmac.compare_digest(self._assinar(chave, acao, exp), sig)

    def _url(
        self, chave: str, acao: str, extra: dict | None = None, expira: int | None = None
    ) -> str:
        exp = int(time.time()) + (expira or settings.url_expira_segundos)
        params = {
            "chave": chave,
            "acao": acao,
            "exp": exp,
            "assinatura": self._assinar(chave, acao, exp),
        }
        params.update(extra or {})
        return f"{settings.base_url.rstrip('/')}/storage/local?{urlencode(params)}"

    # -- caminho ---------------------------------------------------------
    def caminho(self, chave: str) -> Path:
        destino = (self.raiz / chave).resolve()
        raiz = self.raiz.resolve()
        # Impede que uma chave forjada ("../../etc/passwd") escape da raiz.
        if raiz != destino and raiz not in destino.parents:
            raise ValueError("Chave de armazenamento inválida.")
        return destino

    # -- interface pública ------------------------------------------------
    def destino_upload(self, chave: str, content_type: str) -> DestinoUpload:
        return DestinoUpload(
            url=self._url(chave, "put"),
            metodo="PUT",
            headers={"Content-Type": content_type},
            direto=False,
        )

    def url_download(self, chave: str, nome_arquivo: str) -> str:
        return self._url(chave, "get", {"nome": nome_arquivo})

    def url_visualizar(self, chave: str, nome_arquivo: str) -> str:
        # Como na imagem: o tipo não vai na URL, o endpoint confere os bytes.
        return self._url(chave, "pdf", {"nome": nome_arquivo})

    def url_anexo(self, chave: str, nome_arquivo: str, tipo: str) -> str:
        # Foto ou PDF; o endpoint descobre qual pelos bytes.
        return self._url(chave, "anexo", {"nome": nome_arquivo})

    def url_imagem(self, chave: str, tipo: str) -> str:
        # O tipo não vai na URL: ela é assinada só sobre chave, ação e prazo, e
        # um parâmetro solto deixaria quem tem o link escolher o Content-Type.
        # O endpoint descobre o tipo pelos bytes do arquivo.
        return self._url(chave, "img", expira=settings.url_imagem_expira_segundos)

    def gravar_bytes(self, chave: str, dados: bytes, tipo: str) -> None:
        self.gravar(chave, [dados])

    def gravar(self, chave: str, pedacos) -> tuple[int, str]:
        destino = self.caminho(chave)
        destino.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        tamanho = 0
        temporario = destino.with_suffix(destino.suffix + ".parcial")
        with open(temporario, "wb") as fh:
            for pedaco in pedacos:
                digest.update(pedaco)
                tamanho += len(pedaco)
                fh.write(pedaco)
        temporario.replace(destino)
        return tamanho, digest.hexdigest()

    def info(self, chave: str) -> tuple[bool, int]:
        try:
            caminho = self.caminho(chave)
        except ValueError:
            return False, 0
        if not caminho.is_file():
            return False, 0
        return True, caminho.stat().st_size

    def remover(self, chave: str) -> None:
        try:
            self.caminho(chave).unlink(missing_ok=True)
        except ValueError:
            pass


class ArmazenamentoS3:
    """Dois clientes, de propósito.

    ``cliente`` usa o endereço que a API alcança (dentro do Docker, a rede
    interna). ``assinador`` usa o endereço público, porque quem abre a URL
    pré-assinada é o navegador — e ele não resolve o nome de serviço do Docker.

    Assinar com o endereço público é correto e não é gambiarra: a SigV4 cobre o
    cabeçalho Host, e o Host que chega ao MinIO é exatamente o público. Quando os
    dois endereços são iguais (S3 de verdade), o mesmo cliente serve para tudo.
    """

    def __init__(self) -> None:
        import boto3  # importado aqui: só é dependência no modo s3
        from botocore.client import Config

        self.bucket = settings.s3_bucket
        config = Config(signature_version="s3v4")
        credenciais = {
            "region_name": settings.s3_region,
            "aws_access_key_id": settings.s3_access_key,
            "aws_secret_access_key": settings.s3_secret_key,
            "config": config,
        }

        interno = settings.s3_endpoint_servidor
        self.cliente = boto3.client("s3", endpoint_url=interno, **credenciais)
        self.assinador = (
            self.cliente
            if settings.s3_endpoint in (None, interno)
            else boto3.client("s3", endpoint_url=settings.s3_endpoint, **credenciais)
        )

    def garantir_bucket(self) -> None:
        """Cria o bucket se ele não existir — e nunca derruba a subida.

        No MinIO a chave é de administrador e o bucket nasce aqui. Em serviço
        gerenciado (R2, S3) o bucket é criado no painel e a chave costuma ter
        permissão só sobre os objetos: criar bucket é negado, e `head_bucket`
        pode ser negado junto mesmo com o bucket existindo.

        Por isso a falha aqui vira aviso, não exceção. Recusar a subida
        deixaria o sistema inteiro fora do ar — inclusive o catálogo, que nem
        depende do storage — por causa de uma permissão que talvez esteja
        certa. O erro real, se houver, aparece no primeiro envio, dizendo o
        que é.
        """
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            self.cliente.head_bucket(Bucket=self.bucket)
            return
        except (ClientError, BotoCoreError) as erro:
            motivo = erro

        try:
            self.cliente.create_bucket(Bucket=self.bucket)
        except (ClientError, BotoCoreError):
            print(
                f"aviso: não foi possível confirmar o bucket '{self.bucket}' "
                f"({motivo}). Se ele existe e a chave enxerga os objetos, está "
                "tudo certo; senão, o primeiro envio vai falhar.",
                flush=True,
            )

    def destino_upload(self, chave: str, content_type: str) -> DestinoUpload:
        url = self.assinador.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": chave, "ContentType": content_type},
            ExpiresIn=settings.url_expira_segundos,
        )
        return DestinoUpload(
            url=url,
            metodo="PUT",
            headers={"Content-Type": content_type},
            direto=True,
        )

    def url_download(self, chave: str, nome_arquivo: str) -> str:
        disposicao = f"attachment; filename*=UTF-8''{quote(nome_arquivo)}"
        return self.assinador.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": chave,
                "ResponseContentDisposition": disposicao,
            },
            ExpiresIn=settings.url_expira_segundos,
        )

    def url_visualizar(self, chave: str, nome_arquivo: str) -> str:
        # Abrir no navegador: "inline" e PDF fixados na assinatura. O nome vai
        # junto para o caso de a pessoa salvar a partir do visualizador.
        disposicao = f"inline; filename*=UTF-8''{quote(nome_arquivo)}"
        return self.assinador.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": chave,
                "ResponseContentType": "application/pdf",
                "ResponseContentDisposition": disposicao,
            },
            ExpiresIn=settings.url_expira_segundos,
        )

    def url_anexo(self, chave: str, nome_arquivo: str, tipo: str) -> str:
        # Abrir no navegador, com o tipo decidido no cadastro do anexo (só
        # imagem ou PDF passam), fixado na assinatura.
        disposicao = f"inline; filename*=UTF-8''{quote(nome_arquivo)}"
        return self.assinador.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": chave,
                "ResponseContentType": tipo,
                "ResponseContentDisposition": disposicao,
            },
            ExpiresIn=settings.url_expira_segundos,
        )

    def url_imagem(self, chave: str, tipo: str) -> str:
        # "inline" e o tipo fixados na própria assinatura: quem tem o link não
        # consegue trocar nenhum dos dois.
        return self.assinador.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": chave,
                "ResponseContentType": tipo,
                "ResponseContentDisposition": "inline",
            },
            ExpiresIn=settings.url_imagem_expira_segundos,
        )

    def gravar_bytes(self, chave: str, dados: bytes, tipo: str) -> None:
        # Única escrita que passa pela API: o logo tem no máximo 1 MB, e
        # precisa ser conferido byte a byte antes de ser guardado.
        self.cliente.put_object(
            Bucket=self.bucket, Key=chave, Body=dados, ContentType=tipo
        )

    def info(self, chave: str) -> tuple[bool, int]:
        from botocore.exceptions import ClientError

        try:
            r = self.cliente.head_object(Bucket=self.bucket, Key=chave)
        except ClientError:
            return False, 0
        return True, int(r.get("ContentLength", 0))

    def remover(self, chave: str) -> None:
        self.cliente.delete_object(Bucket=self.bucket, Key=chave)


def obter_armazenamento():
    if settings.storage_backend == "s3":
        return ArmazenamentoS3()
    return ArmazenamentoLocal()


armazenamento = obter_armazenamento()
