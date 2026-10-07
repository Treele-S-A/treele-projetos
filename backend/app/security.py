"""Hash de senha e emissão/validação de token.

O hash usa scrypt da biblioteca padrão — sem dependência nativa para compilar
no Windows e com parâmetros na faixa recomendada pelo OWASP.
"""

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt

from .config import settings

_N = 2**15
_R = 8
_P = 1
_TAM = 32


def _maxmem(n: int, r: int) -> int:
    """O limite padrão do OpenSSL é 32 MB e N=2^15, r=8 pede ~33 MB.

    Sem isto o hash falha com "memory limit exceeded". A folga de 2x cobre a
    contabilidade interna do OpenSSL.
    """
    return 128 * n * r * 2


def gerar_hash_senha(senha: str) -> str:
    sal = os.urandom(16)
    dk = hashlib.scrypt(
        senha.encode("utf-8"),
        salt=sal,
        n=_N,
        r=_R,
        p=_P,
        dklen=_TAM,
        maxmem=_maxmem(_N, _R),
    )
    return f"scrypt${_N}${_R}${_P}${sal.hex()}${dk.hex()}"


def conferir_senha(senha: str, armazenado: str) -> bool:
    try:
        algo, n, r, p, sal_hex, dk_hex = armazenado.split("$")
        if algo != "scrypt":
            return False
        dk = hashlib.scrypt(
            senha.encode("utf-8"),
            salt=bytes.fromhex(sal_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(dk_hex) // 2,
            maxmem=_maxmem(int(n), int(r)),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk.hex(), dk_hex)


def selo_da_senha(senha_hash: str) -> str:
    """Marca da senha atual que vai dentro do token. Trocou a senha (a pessoa
    ou o administrador), a marca muda e todas as sessões abertas caem — com
    "manter conectado" valendo 30 dias, um computador esquecido logado não
    pode continuar entrando depois da troca. É um resumo do hash, não a senha."""
    return hashlib.sha256(senha_hash.encode("utf-8")).hexdigest()[:16]


def validade(manter_conectado: bool) -> timedelta:
    if manter_conectado:
        return timedelta(days=settings.token_lembrar_dias)
    return timedelta(minutes=settings.token_expira_minutos)


def criar_token(usuario_id: int, senha_hash: str, manter_conectado: bool = False) -> str:
    payload = {
        "sub": str(usuario_id),
        "exp": datetime.now(timezone.utc) + validade(manter_conectado),
        "sv": selo_da_senha(senha_hash),
        "lembrar": manter_conectado,
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def ler_token(token: str) -> dict | None:
    """O conteúdo do token, ou None se for inválido ou estiver vencido."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        int(payload["sub"])
        return payload
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None
