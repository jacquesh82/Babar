"""Configuration centralisée (12-factor) chargée depuis l'environnement / .env.

Toutes les valeurs proviennent de variables d'environnement (voir ``.env.example``).
Aucun secret n'est codé en dur. Ce module est importable par l'app et le worker.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # --- API ---
    app_env: str = "local"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    # --- PostgreSQL ---
    database_url: str = "postgresql+asyncpg://memory:change-me@postgres:5432/memory"

    # --- Redis ---
    redis_url: str = "redis://redis:6379/0"

    # --- Backends pluggables (seams modèles ; défauts = déterministes/local) ---
    embedding_dim: int = 1536
    embedding_backend: str = "local"  # storage/vector_store
    extraction_backend: str = "heuristic"  # ingestion/extractor
    coref_backend: str = "rules"  # ingestion/coref_resolver

    # --- Context builder ---
    context_token_budget: int = 2000

    # --- Consolidation ---
    consolidation_cron: str = "0 3 * * *"
    contradiction_strategy: str = "lww"

    # --- Multi-tenant : "header" | "jwt" | "oidc" | "single" ---
    tenant_mode: str = "header"

    # --- Auth JWT HS256 (mode tenant_mode="jwt") ---
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_tenant_claim: str = "tenant_id"
    jwt_user_claim: str = "user_id"

    # --- Auth OIDC / Mindlog.id (mode tenant_mode="oidc") ---
    # Provider OAuth 2.1 / OIDC émettant des JWT ES256 vérifiés via JWKS.
    # Mindlog.id (https://id.mindlog.today) : JWKS sur un chemin NON standard
    # (/oauth/jwks) → OIDC_JWKS_URI doit être fixé explicitement.
    oidc_issuer: str = ""  # ex: https://id.mindlog.today  (vérif du claim `iss`)
    oidc_jwks_uri: str = ""  # ex: https://id.mindlog.today/oauth/jwks
    # `aud` attendu. IMPORTANT : Mindlog.id ne supporte pas encore les resource
    # indicators (RFC 8707) → le `aud` ne cible pas la ressource. Tant que ce
    # n'est pas résolu côté provider, laisser une valeur stricte ici fait échouer
    # la validation (fail-closed voulu) : NE PAS exposer publiquement avant.
    oidc_audience: str = "https://memory.mindlog.today/mcp"
    oidc_algorithms: str = "RS256,ES256"
    # Mindlog.id n'émet pas de claim d'organisation → `sub` sert de tenant
    # (une mémoire isolée par identité Mindlog.id).
    oidc_tenant_claim: str = "sub"  # claim → tenant_id (isolation)
    oidc_user_claim: str = "sub"  # claim → user_id

    # --- Métadonnées OAuth de cette ressource MCP (flux OAuth MCP complet) ---
    public_base_url: str = "https://memory.mindlog.today"
    mcp_resource: str = "https://memory.mindlog.today/mcp"

    @property
    def asyncpg_dsn(self) -> str:
        """DSN utilisable par asyncpg (retire le suffixe de dialecte SQLAlchemy)."""
        return self.database_url.replace("+asyncpg", "", 1)


@lru_cache
def get_settings() -> Settings:
    """Retourne l'instance unique de configuration (mise en cache)."""
    return Settings()


settings = get_settings()
