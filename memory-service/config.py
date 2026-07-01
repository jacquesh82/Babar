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

    # --- Embeddings ---
    embedding_dim: int = 1536
    embedding_backend: str = "local"

    # --- Context builder ---
    context_token_budget: int = 2000

    # --- Consolidation ---
    consolidation_cron: str = "0 3 * * *"
    contradiction_strategy: str = "lww"

    # --- Multi-tenant : "header" | "jwt" | "single" ---
    tenant_mode: str = "header"

    @property
    def asyncpg_dsn(self) -> str:
        """DSN utilisable par asyncpg (retire le suffixe de dialecte SQLAlchemy)."""
        return self.database_url.replace("+asyncpg", "", 1)


@lru_cache
def get_settings() -> Settings:
    """Retourne l'instance unique de configuration (mise en cache)."""
    return Settings()


settings = get_settings()
