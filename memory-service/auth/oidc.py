"""Vérification de jetons OIDC (Mindlog.id) via JWKS — RS256/ES256.

Mindlog.id agit comme **serveur d'autorisation OAuth 2.1 / OIDC**. Les jetons
d'accès sont des JWT signés par clé asymétrique ; la clé publique correspondante
est récupérée depuis le JWKS du provider et **mise en cache** (par ``kid``).

La cryptographie est déléguée à PyJWT (+ ``cryptography``) : ré-implémenter la
vérification RSA/ECDSA à la main serait une faute de sécurité. Ce module
complète ``auth/jwt_utils`` (HS256 stdlib, mode ``jwt``) sans le remplacer : il
n'est chargé qu'en mode ``tenant_mode="oidc"``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient

from config import settings


class OIDCError(Exception):
    """Jeton OIDC invalide/non vérifiable, ou provider mal configuré."""


def _jwks_uri() -> str:
    if settings.oidc_jwks_uri:
        return settings.oidc_jwks_uri
    if not settings.oidc_issuer:
        raise OIDCError("OIDC_ISSUER (ou OIDC_JWKS_URI) non configuré")
    return settings.oidc_issuer.rstrip("/") + "/.well-known/jwks.json"


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    """Client JWKS unique : récupère et met en cache les clés de signature."""
    return PyJWKClient(_jwks_uri())


def _algorithms() -> list[str]:
    return [a.strip() for a in settings.oidc_algorithms.split(",") if a.strip()]


def _signing_key(token: str) -> Any:
    """Clé publique de signature pour ce jeton.

    Isolé pour être mockable en test (évite tout appel réseau JWKS).
    """
    return _jwks_client().get_signing_key_from_jwt(token).key


def verify_oidc_token(token: str) -> dict[str, Any]:
    """Vérifie signature + ``exp``/``iss``/``aud`` et renvoie les claims.

    Raises:
        OIDCError: signature invalide, jeton expiré, issuer/audience non conforme,
        JWKS injoignable, ou configuration absente.
    """
    try:
        key = _signing_key(token)
        return jwt.decode(
            token,
            key,
            algorithms=_algorithms(),
            audience=settings.oidc_audience or None,
            issuer=settings.oidc_issuer or None,
            options={
                "require": ["exp"],
                "verify_aud": bool(settings.oidc_audience),
                "verify_iss": bool(settings.oidc_issuer),
            },
        )
    except OIDCError:
        raise
    except Exception as exc:  # jwt.*Error, erreurs réseau JWKS, etc.
        raise OIDCError(str(exc)) from exc


def protected_resource_metadata() -> dict[str, Any]:
    """Document *OAuth Protected Resource Metadata* (RFC 9728) de cette ressource.

    Sert au flux OAuth MCP : le client MCP le lit pour découvrir quel serveur
    d'autorisation (Mindlog.id) utiliser, puis obtient un jeton pour ``resource``.
    """
    return {
        "resource": settings.mcp_resource,
        "authorization_servers": [settings.oidc_issuer] if settings.oidc_issuer else [],
        "bearer_methods_supported": ["header"],
    }
