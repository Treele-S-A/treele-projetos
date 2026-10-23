"""Configuração da aplicação, lida de variáveis de ambiente ou do arquivo .env."""

import os
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
    # "Manter conectado" no login (07/10/2026): a sessão vale isto nesta
    # máquina, em vez das 12 horas. Limitado de propósito.
    token_lembrar_dias: int = 30

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
    # Logo fica na tela o expediente inteiro; link de uma hora quebraria a
    # imagem de quem deixa a aba aberta. Arquivo de projeto continua em uma.
    url_imagem_expira_segundos: int = 12 * 3600
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

    # E-mail das notificações, por SMTP — serve Resend, Microsoft 365, Google
    # Workspace ou qualquer outro. Sem EMAIL_SMTP_HOST o e-mail fica desligado
    # e o aviso aparece só no sistema.
    email_smtp_host: str = ""
    email_smtp_porta: int = 587
    email_smtp_usuario: str = ""
    email_smtp_senha: str = ""
    # Quem aparece como remetente: "Treèle Projetos <projetos@treele.com.br>".
    email_remetente: str = ""
    # Chat do acervo (Fase 2): chave da API do Gemini. Vazia = chat desligado,
    # e o botão nem aparece. O modelo é configurável para trocar sem código.
    gemini_api_key: str = ""
    chat_modelo: str = "gemini-3.8-flash"
    # Reservas, em ordem, separadas por vírgula: entram quando o principal está
    # sobrecarregado (503), sem cota (429) ou indisponível (404). A cota
    # gratuita é por modelo, então cada reserva tem a sua. O gemini-2.5-flash
    # não serve: o Google não o libera mais para chave nova (07/10/2026).
    chat_modelo_reserva: str = "gemini-3.7-flash,gemini-3.5-flash"
    # Maior PDF que o assistente lê. O PDF vai junto da chamada ao modelo; acima
    # disto a chamada passa do tamanho aceito ou do tempo da função.
    chat_pdf_max_mb: int = 14
    # Claude (Anthropic), em teste desde 16/10/2026: com ANTHROPIC_API_KEY o
    # chat usa o Claude no lugar do Gemini. CHAT_FORNECEDOR ("claude" ou
    # "gemini") força um dos dois quando as duas chaves estão configuradas.
    anthropic_api_key: str = ""
    # Só para chave criada fora de um workspace: a Anthropic pede o ID do
    # workspace (wrkspc_...) em cada chamada. Chave de workspace dispensa.
    anthropic_workspace_id: str = ""
    chat_modelo_claude: str = "claude-haiku-5-5"
    chat_fornecedor: str = ""
    # Quem recebe e-mail a cada 👎 no chat (vírgula separa vários; vazio
    # desliga). Pedido de 21/10/2026: só o estágio de projetos.
    chat_avisar_avaliacoes: str = "estagio.projetos@treele.com.br"

    # Endereço das telas, para os links dos e-mails. Vazio = descobre sozinho
    # (ver endereco_site).
    site_url: str = ""

    # Login Microsoft opcional (Entra ID). O segredo pertence somente ao
    # backend; sem os três, o botão avisa que não está configurado.
    entra_tenant_id: str = ""
    entra_client_id: str = ""
    entra_client_secret: str = ""

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
    def chat_fornecedor_ativo(self) -> str | None:
        """"claude", "gemini" ou None (chat desligado)."""
        chaves = {
            "claude": self.anthropic_api_key.strip(),
            "gemini": self.gemini_api_key.strip(),
        }
        escolhido = self.chat_fornecedor.strip().lower()
        if escolhido in chaves:
            return escolhido if chaves[escolhido] else None
        return next((nome for nome, chave in chaves.items() if chave), None)

    @property
    def chat_ligado(self) -> bool:
        return self.chat_fornecedor_ativo is not None

    @property
    def email_ligado(self) -> bool:
        return bool(self.email_smtp_host.strip())

    @property
    def endereco_site(self) -> str:
        """Endereço das telas, para os links dos e-mails.

        Na Vercel, o domínio de produção vem dela mesma
        (VERCEL_PROJECT_PRODUCTION_URL): a BASE_URL nunca foi definida lá, e o
        primeiro e-mail de teste saiu com link para localhost. Fora dela, a API
        mora no mesmo endereço com o prefixo /api ou em endereço próprio (dev).
        """
        if self.site_url.strip():
            return self.site_url.strip().rstrip("/")
        vercel = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL", "").strip()
        if vercel:
            return f"https://{vercel}"
        base = self.base_url.rstrip("/")
        if self.api_prefix and base.endswith(self.api_prefix):
            base = base[: -len(self.api_prefix)]
        return base

    @property
    def lista_cors(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def tamanho_max_bytes(self) -> int:
        return self.tamanho_max_mb * 1024 * 1024


def _problema_na_chave(chave: str) -> str | None:
    """O que está errado com a SECRET_KEY, sem nunca repetir o valor dela."""
    if chave == SECRET_KEY_DEV:
        return (
            "SECRET_KEY não chegou ao sistema. Confira o nome exato da variável "
            "e se ela está marcada para o ambiente Production."
        )
    if chave.upper().startswith("SECRET_KEY"):
        return (
            "SECRET_KEY foi colada com o nome junto (\"SECRET_KEY = ...\"). "
            "O valor é só a chave."
        )
    if chave != chave.strip() or chave[:1] in "\"'":
        return "SECRET_KEY tem espaço ou aspas nas pontas. Cole só a chave."
    if len(chave) < 32:
        return (
            f"SECRET_KEY tem {len(chave)} caractere(s); precisa de pelo menos 32. "
            'Gere com `python -c "import secrets; print(secrets.token_urlsafe(48))"`.'
        )
    return None


def _conferir_producao(s: Settings) -> None:
    """Em produção, recusa subir com configuração faltando — listando tudo.

    A SECRET_KEY assina as sessões *e* os links de download: com a chave de
    exemplo, qualquer um forja um acesso. Falhar ruidosamente na subida é
    melhor que rodar meses assim — é o tipo de erro que ninguém percebe,
    porque o sistema funciona perfeitamente enquanto está errado.

    Todos os problemas saem numa mensagem só: na hospedagem, cada rodada de
    "corrige, publica, lê o log" custa minutos, e descobrir as variáveis que
    faltam uma por vez multiplica isso.

    A conferência fica aqui, e não num validador do pydantic, de propósito: o
    erro de validação do pydantic imprime o modelo inteiro, e aí a senha do
    administrador iria junto para o log da hospedagem. Pelo mesmo motivo, as
    mensagens dizem o que falta ou o tamanho — nunca o valor.
    """
    if s.ambiente != "producao":
        return

    problemas = []
    if erro := _problema_na_chave(s.secret_key):
        problemas.append(erro)

    # Banco não definido cai no SQLite padrão, que em produção vira um banco
    # vazio e descartável (e, na Vercel, nem abre: o disco é só leitura).
    # SQLite escolhido de propósito continua valendo.
    if s.database_url == Settings.model_fields["database_url"].default:
        problemas.append("DATABASE_URL não definida.")
    elif not s.database_url.startswith(("postgresql", "sqlite")):
        # Só o esquema aparece na mensagem: o resto da string tem a senha.
        # Caso real: o endereço do storage (https://…) colado no lugar dela.
        esquema = s.database_url.split("://", 1)[0] if "://" in s.database_url else ""
        problemas.append(
            (f'DATABASE_URL começa com "{esquema}://", ' if esquema else
             "DATABASE_URL não tem o formato de uma string de conexão, ")
            + "mas precisa ser a do Postgres (Supabase: Connect → Transaction "
            "pooler), que começa com postgresql://."
        )
    elif "[YOUR-PASSWORD]" in s.database_url:
        problemas.append(
            "DATABASE_URL ainda tem [YOUR-PASSWORD]: troque pela senha do banco."
        )

    if s.storage_backend == "s3":
        faltando = [
            nome
            for nome, valor in (
                ("S3_ENDPOINT", s.s3_endpoint),
                ("S3_ACCESS_KEY", s.s3_access_key),
                ("S3_SECRET_KEY", s.s3_secret_key),
            )
            if not (valor or "").strip()
        ]
        if faltando:
            problemas.append(f"Não definida(s): {', '.join(faltando)}.")
        endpoint = (s.s3_endpoint or "").strip()
        if endpoint and not endpoint.startswith(("https://", "http://")):
            problemas.append(
                "S3_ENDPOINT precisa começar com https:// "
                "(Supabase: Project Settings → Storage → S3 Connection)."
            )

    # E-mail é opcional, mas pela metade é erro: sem remetente o servidor
    # recusa tudo, e o problema só apareceria no primeiro aviso.
    if s.email_ligado:
        faltando = [
            nome
            for nome, valor in (
                ("EMAIL_REMETENTE", s.email_remetente),
                ("EMAIL_SMTP_USUARIO", s.email_smtp_usuario),
                ("EMAIL_SMTP_SENHA", s.email_smtp_senha),
            )
            if not valor.strip()
        ]
        if faltando:
            problemas.append(
                f"EMAIL_SMTP_HOST está definida, mas falta: {', '.join(faltando)}. "
                "Para desligar o e-mail, apague EMAIL_SMTP_HOST."
            )

    if problemas:
        raise RuntimeError(
            "Configuração de produção incompleta — nada foi iniciado:\n"
            + "\n".join(f"  - {p}" for p in problemas)
        )


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    _conferir_producao(s)
    # Pasta só é criada quando algo vai mesmo ser gravado nela. Em produção nem
    # o banco (Postgres) nem os arquivos (S3/R2) moram no disco — e na Vercel o
    # disco é só leitura: criar a pasta à toa derrubaria a subida.
    if s.database_url.startswith("sqlite:///"):
        Path(s.database_url.removeprefix("sqlite:///")).parent.mkdir(
            parents=True, exist_ok=True
        )
    if s.storage_backend == "local":
        s.storage_local_dir.mkdir(parents=True, exist_ok=True)
    return s


settings = get_settings()
