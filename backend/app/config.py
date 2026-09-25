"""Configuração da aplicação, lida de variáveis de ambiente ou do arquivo .env."""

import re
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SECRET_KEY_DEV = "dev-apenas-troque-em-producao"

# backend/
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_nome: str = "Treèle — Controle de revisões"
    ambiente: str = "dev"

    # Trocar obrigatoriamente em produção (ver README) — e a validação abaixo
    # garante que isso não passe batido.
    secret_key: str = SECRET_KEY_DEV
    token_expira_minutos: int = 60 * 12

    # SQLite por padrão para rodar sem Docker; o docker-compose injeta Postgres.
    database_url: str = f"sqlite:///{(DATA_DIR / 'treele.db').as_posix()}"

    # Vazio = as tabelas vão para o schema padrão do banco ("public"), como
    # sempre foi. Preencher isola este sistema num schema próprio dentro de um
    # banco Postgres que também serve outra aplicação — o caso de reaproveitar
    # um projeto Supabase já existente. Nunca mudar o padrão para um valor
    # fixo: quem já roda em Postgres dedicado tem os dados em "public", e
    # trocar o schema por baixo faria o sistema achar o banco vazio na
    # próxima subida.
    db_schema: str = ""

    # "local" grava em disco e assina URLs pela própria API.
    # "s3" usa MinIO/S3 com URLs pré-assinadas (o navegador fala direto com o storage).
    storage_backend: str = "local"
    storage_local_dir: Path = DATA_DIR / "storage"

    # Dois endereços de propósito. Dentro do Docker a API fala com o MinIO pela
    # rede interna ("http://minio:9000"), mas a URL pré-assinada que ela devolve
    # é aberta pelo NAVEGADOR, que não resolve "minio" — essa precisa do endereço
    # público. Assinar com o endereço público é o correto: a assinatura SigV4
    # cobre o cabeçalho Host, e o Host que o MinIO recebe é justamente o público.
    s3_endpoint: str | None = None
    s3_endpoint_interno: str | None = None
    s3_region: str = "us-east-1"
    s3_bucket: str = "treele-projetos"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None

    url_expira_segundos: int = 3600
    tamanho_max_mb: int = 2048

    base_url: str = "http://localhost:8000"

    # Prefixo das rotas da API. Vazio quando a API tem endereço próprio (é o
    # caso do desenvolvimento e dos testes). "/api" quando ela divide o
    # endereço com a interface — aí o prefixo é o que evita que /obras da API
    # colida com /obras da tela.
    api_prefix: str = ""

    # Pasta com a interface já compilada. Quando existe, a aplicação serve as
    # telas além da API, num processo só. Vazio = a interface é servida à parte.
    estaticos_dir: Path | None = None
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Primeiro acesso. Sem ADMIN_SENHA definida, uma senha aleatória é gerada
    # e impressa uma única vez no console na primeira inicialização.
    # Domínio real de propósito: `.local` é TLD reservado e o validador de
    # e-mail o recusa, o que deixaria o admin sem conseguir entrar.
    admin_email: str = "admin@treele.com.br"
    admin_senha: str | None = None

    @field_validator("db_schema")
    @classmethod
    def _schema_seguro(cls, valor: str) -> str:
        """Identificador simples, porque vai direto para dentro de SQL.

        O schema vem de variável de ambiente, não de entrada de usuário, mas um
        valor mal colado viraria SQL solto no `SET search_path` — mesmo cuidado
        do storage.py com nome de arquivo.
        """
        if valor and not re.fullmatch(r"[a-z_][a-z0-9_]*", valor):
            raise ValueError(
                "DB_SCHEMA inválido: use letras minúsculas, números e underscore."
            )
        return valor

    @field_validator("estaticos_dir", mode="before")
    @classmethod
    def _vazio_e_nenhum(cls, valor):
        """ESTATICOS_DIR vazia quer dizer "sem interface", não "pasta atual".

        Sem isto, `Path("")` vira `.`, que existe — e a subida cai procurando
        `./assets`, justamente quando alguém tentou desligar a interface.
        """
        if isinstance(valor, str) and not valor.strip():
            return None
        return valor

    @field_validator("database_url")
    @classmethod
    def _driver_explicito(cls, valor: str) -> str:
        """Hospedagens gerenciadas entregam a URL como `postgres://`.

        O SQLAlchemy não reconhece esse esquema e escolheria o psycopg2, que
        nem está instalado. Normalizar aqui evita um erro na subida que não diz
        nada sobre a causa.
        """
        for prefixo in ("postgres://", "postgresql://"):
            if valor.startswith(prefixo):
                return "postgresql+psycopg://" + valor[len(prefixo) :]
        return valor

    @property
    def s3_endpoint_servidor(self) -> str | None:
        """Endereço que a própria API usa. Cai no público quando não há rede interna."""
        return self.s3_endpoint_interno or self.s3_endpoint

    @property
    def lista_cors(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def tamanho_max_bytes(self) -> int:
        return self.tamanho_max_mb * 1024 * 1024


def _conferir_chave(s: Settings) -> None:
    """Em produção, recusa subir com chave fraca ou com a de desenvolvimento.

    Essa chave assina as sessões *e* os links de download: com ela, qualquer um
    forja um acesso. Falhar ruidosamente na subida é melhor que rodar meses com
    a chave de exemplo — é o tipo de erro que ninguém percebe, porque o sistema
    funciona perfeitamente enquanto está errado.

    A conferência fica aqui, e não num validador do pydantic, de propósito: o
    erro de validação do pydantic imprime o modelo inteiro, e aí a senha do
    administrador iria junto para o log da hospedagem.
    """
    if s.ambiente != "producao":
        return
    if s.secret_key == SECRET_KEY_DEV or len(s.secret_key) < 32:
        raise RuntimeError(
            "SECRET_KEY inválida para produção: defina uma chave própria de pelo "
            'menos 32 caracteres. Gere com `python -c "import secrets; '
            'print(secrets.token_urlsafe(48))"`.'
        )


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    _conferir_chave(s)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if s.storage_backend == "local":
        s.storage_local_dir.mkdir(parents=True, exist_ok=True)
    return s


settings = get_settings()
