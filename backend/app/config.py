"""Configuração da aplicação, lida de variáveis de ambiente ou do arquivo .env."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_nome: str = "TREELE — Gestão de Projetos"
    ambiente: str = "dev"

    # Trocar obrigatoriamente em produção (ver README).
    secret_key: str = "dev-apenas-troque-em-producao"
    token_expira_minutos: int = 60 * 12

    # SQLite por padrão para rodar sem Docker; o docker-compose injeta Postgres.
    database_url: str = f"sqlite:///{(DATA_DIR / 'treele.db').as_posix()}"

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
    # Prefixo sob o qual a API é servida quando há proxy na frente. Em produção
    # o Caddy atende /api/* e remove o prefixo antes de repassar; sem informar
    # isto aqui, a documentação da API geraria links sem o /api.
    root_path: str = ""
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Primeiro acesso. Sem ADMIN_SENHA definida, uma senha aleatória é gerada
    # e impressa uma única vez no console na primeira inicialização.
    # Domínio real de propósito: `.local` é TLD reservado e o validador de
    # e-mail o recusa, o que deixaria o admin sem conseguir entrar.
    admin_email: str = "admin@treele.com.br"
    admin_senha: str | None = None

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


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if s.storage_backend == "local":
        s.storage_local_dir.mkdir(parents=True, exist_ok=True)
    return s


settings = get_settings()
