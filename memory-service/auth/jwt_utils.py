"""Vérification/émission de JWT HS256 — sans dépendance externe.

Implémentation stdlib (hmac + hashlib + base64) volontairement minimale et
auto-portée : HS256 uniquement, vérification de signature et d'expiration. Elle
couvre le besoin d'isolation multi-tenant par JWT sans tirer de dépendance
cryptographique. Un backend RS/ES256 (clé publique) pourrait la remplacer.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any


class JWTError(Exception):
    """JWT malformé, signature invalide, algorithme non supporté ou expiré."""


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def encode_hs256(payload: dict[str, Any], secret: str) -> str:
    """Émet un JWT signé HS256 (utilitaire de test / d'émission de jetons)."""
    header = {"alg": "HS256", "typ": "JWT"}
    header_seg = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_seg = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header_seg}.{payload_seg}".encode()
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{header_seg}.{payload_seg}.{_b64url_encode(signature)}"


def decode_hs256(token: str, secret: str, *, now: float | None = None) -> dict[str, Any]:
    """Vérifie un JWT HS256 et retourne ses claims.

    Args:
        now: horodatage Unix pour la vérification ``exp`` (si absent, non vérifiée).

    Raises:
        JWTError: format invalide, algorithme ≠ HS256, signature KO, ou expiré.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise JWTError("format JWT invalide")
    header_seg, payload_seg, signature_seg = parts

    try:
        header = json.loads(_b64url_decode(header_seg))
    except Exception as exc:  # noqa: BLE001
        raise JWTError("en-tête illisible") from exc
    if header.get("alg") != "HS256":
        raise JWTError(f"algorithme non supporté : {header.get('alg')}")

    signing_input = f"{header_seg}.{payload_seg}".encode()
    expected = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, _b64url_decode(signature_seg)):
        raise JWTError("signature invalide")

    try:
        payload = json.loads(_b64url_decode(payload_seg))
    except Exception as exc:  # noqa: BLE001
        raise JWTError("charge utile illisible") from exc

    exp = payload.get("exp")
    if exp is not None and now is not None and now >= float(exp):
        raise JWTError("jeton expiré")
    return payload
