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

    def _url(self, chave: str, acao: str, extra: dict | None = None) -> str:
        exp = int(time.time()) + settings.url_expira_segundos
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
        from botocore.exceptions import ClientError

        try:
            self.cliente.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.cliente.create_bucket(Bucket=self.bucket)

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
