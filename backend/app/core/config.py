from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ResolveFlow API"
    database_url: str = (
        "mysql+pymysql://resolve_flow:resolve_flow@localhost:3306/"
        "resolve_flow?charset=utf8mb4"
    )
    auto_create_tables: bool = False
    seed_demo_data: bool = True
    ai_provider: str = "rules"
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_timeout_seconds: float = 12.0
    rag_enabled: bool = False
    milvus_uri: str = "http://milvus:19530"
    milvus_collection_name: str = "resolveflow_knowledge_chunks"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dimension: int = 512

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
