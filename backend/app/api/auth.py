import secrets
import time
import logging
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..config import settings
from ..deps import usuario_atual
from ..models import Usuario
from ..schemas import LoginEntrada, SenhaAlterar, TokenSaida, UsuarioOut
from ..security import conferir_senha, criar_token, gerar_hash_senha, ler_token, validade
from ..services import auditoria

router = APIRouter(prefix="/auth", tags=["autenticação"])
logger = logging.getLogger(__name__)


@router.get("/microsoft/status")
def microsoft_status():
    return {"configurado": bool(
        settings.entra_tenant_id.strip()
        and settings.entra_client_id.strip()
        and settings.entra_client_secret.strip()
        and (settings.ambiente != "producao" or settings.site_url.strip())
    )}


def _entra_config() -> tuple[str, str, str]:
    tenant, client, secret = (
        settings.entra_tenant_id.strip(),
        settings.entra_client_id.strip(),
        settings.entra_client_secret.strip(),
    )
    if not all((tenant, client, secret)) or (settings.ambiente == "producao" and not settings.site_url.strip()):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Login Microsoft ainda não configurado.")
    return tenant, client, secret


def _entra_urls() -> tuple[str, str]:
    # Na Vercel, SITE_URL aponta para o domínio público; em desenvolvimento a
    # API tem porta própria e o frontend volta para a origem autorizada no CORS.
    if settings.site_url.strip():
        origem = settings.site_url.strip().rstrip("/")
        return f"{origem}{settings.api_prefix}/auth/microsoft/callback", origem
    if settings.ambiente == "producao":
        origem = settings.endereco_site
        return f"{origem}{settings.api_prefix}/auth/microsoft/callback", origem
    return (
        f"{settings.base_url.rstrip('/')}{settings.api_prefix}/auth/microsoft/callback",
        settings.lista_cors[0],
    )


@router.get("/microsoft/start")
def microsoft_start(request: Request):
    tenant, client, _ = _entra_config()
    callback, _ = _entra_urls()
    estado, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    cookie = jwt.encode({"state": estado, "nonce": nonce, "exp": time.time() + 600}, settings.secret_key, algorithm="HS256")
    parametros = urlencode({
        "client_id": client,
        "response_type": "code",
        "redirect_uri": callback,
        "response_mode": "query",
        "scope": "openid profile email",
        "state": estado,
        "nonce": nonce,
    })
    resposta = RedirectResponse(f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?{parametros}")
    resposta.set_cookie("treele_entra_state", cookie, max_age=600, httponly=True, secure=callback.startswith("https://"), samesite="lax", path=f"{settings.api_prefix}/auth/microsoft")
    logger.info("Microsoft start: host=%s", request.url.hostname)
    return resposta


@router.get("/microsoft/callback", name="microsoft_callback")
def microsoft_callback(request: Request, code: str = "", state: str = "", error: str = "", db: Session = Depends(get_db)):
    tenant, client, secret = _entra_config()
    callback, frontend = _entra_urls()
    cookie = request.cookies.get("treele_entra_state", "")
    etapa = "estado"
    try:
        sessao = jwt.decode(cookie, settings.secret_key, algorithms=["HS256"])
        if not state or not secrets.compare_digest(state, sessao["state"]) or error or not code:
            raise ValueError("Estado inválido")
        with httpx.Client(timeout=10) as http:
            etapa = "troca do codigo"
            resposta_token = http.post(
                f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
                data={"client_id": client, "client_secret": secret, "grant_type": "authorization_code", "code": code, "redirect_uri": callback},
            )
            resposta_token.raise_for_status()
            id_token = resposta_token.json()["id_token"]
        etapa = "chave Microsoft"
        chave = jwt.PyJWKClient(f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys").get_signing_key_from_jwt(id_token)
        etapa = "token Microsoft"
        claims = jwt.decode(
            id_token, chave.key, algorithms=["RS256"], audience=client,
            issuer=f"https://login.microsoftonline.com/{tenant}/v2.0",
            options={"require": ["exp", "iat", "iss", "aud", "tid", "oid", "nonce"]},
        )
        if claims["tid"] != tenant or not secrets.compare_digest(claims["nonce"], sessao["nonce"]):
            raise ValueError("Identidade inválida")
    except (jwt.PyJWTError, ValueError, KeyError, httpx.HTTPError) as exc:
        # Não registrar código OAuth, token, segredo nem dados do usuário.
        logger.warning("Falha no retorno Microsoft (%s, host=%s, cookie presente: %s): %s", etapa, request.url.hostname, bool(cookie), type(exc).__name__)
        resposta = RedirectResponse(f"{frontend}/#entra_erro=Falha%20na%20autenticacao%20Microsoft", status_code=303)
    else:
        email = (claims.get("email") or claims.get("preferred_username") or "").strip().lower()
        usuario = db.scalar(select(Usuario).where(Usuario.email == email)) if email.endswith("@treele.com.br") else None
        if not email.endswith("@treele.com.br") or (usuario is not None and not usuario.ativo):
            resposta = RedirectResponse(f"{frontend}/#entra_erro=Conta%20sem%20acesso%20ao%20Projetos", status_code=303)
        else:
            if usuario is None:
                usuario = Usuario(
                    nome=(claims.get("name") or email.split("@", 1)[0]).strip()[:160],
                    email=email,
                    senha_hash=gerar_hash_senha(secrets.token_urlsafe(32)),
                    admin=False,
                    comercial=False,
                    ativo=True,
                )
                db.add(usuario)
                db.flush()
                auditoria.registrar(db, acao="usuario_criado_microsoft", entidade="usuario", entidade_id=usuario.id, usuario=usuario, request=request)
            auditoria.registrar(db, acao="login", entidade="usuario", entidade_id=usuario.id, usuario=usuario, request=request)
            db.commit()
            resposta = RedirectResponse(f"{frontend}/#entra_token={criar_token(usuario.id, usuario.senha_hash)}", status_code=303)
    resposta.delete_cookie("treele_entra_state", path=f"{settings.api_prefix}/auth/microsoft")
    resposta.headers["Cache-Control"] = "no-store"
    resposta.headers["Referrer-Policy"] = "no-referrer"
    return resposta


@router.post("/login", response_model=TokenSaida)
def login(dados: LoginEntrada, request: Request, db: Session = Depends(get_db)):
    usuario = db.scalar(select(Usuario).where(Usuario.email == dados.email.lower()))

    if (
        usuario is None
        or not usuario.ativo
        or not conferir_senha(dados.senha, usuario.senha_hash)
    ):
        # Mensagem única de propósito: não revela se o e-mail existe.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou senha incorretos.")

    auditoria.registrar(
        db, acao="login", entidade="usuario", entidade_id=usuario.id,
        usuario=usuario, request=request,
    )
    db.commit()

    return _token(usuario, dados.manter_conectado)


def _token(usuario: Usuario, manter_conectado: bool) -> TokenSaida:
    return TokenSaida(
        token=criar_token(usuario.id, usuario.senha_hash, manter_conectado),
        expira_em_minutos=int(validade(manter_conectado).total_seconds() // 60),
    )


@router.get("/eu", response_model=UsuarioOut)
def eu(usuario: Usuario = Depends(usuario_atual)):
    return usuario


@router.post("/senha", response_model=TokenSaida)
def alterar_senha(
    dados: SenhaAlterar,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    if not conferir_senha(dados.senha_atual, usuario.senha_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Senha atual incorreta.")

    usuario.senha_hash = gerar_hash_senha(dados.senha_nova)
    auditoria.registrar(
        db, acao="senha_alterada", entidade="usuario", entidade_id=usuario.id,
        usuario=usuario, request=request,
    )
    db.commit()
    # A troca derruba todas as sessões — inclusive esta. Quem trocou recebe
    # uma nova, com a mesma escolha de "manter conectado"; os outros
    # computadores precisam entrar de novo.
    atual = ler_token(request.headers.get("authorization", "").partition(" ")[2]) or {}
    return _token(usuario, bool(atual.get("lembrar")))
