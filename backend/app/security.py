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


def criar_token(usuario_id: int) -> str:
    expira = datetime.now(timezone.utc) + timedelta(minutes=settings.token_expira_minutos)
    payload = {"sub": str(usuario_id), "exp": expira}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def ler_token(token: str) -> int | None:
    """Devolve o id do usuário, ou None se o token for inválido/expirado."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
