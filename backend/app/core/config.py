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
    llm_timeout_seconds: float = 12.0
    qwen_api_key: str | None = None
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-turbo"
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    dispatcher_llm_provider: str | None = None
    dispatcher_llm_model: str | None = None
    knowledge_llm_provider: str | None = None
    knowledge_llm_model: str | None = None
    risk_llm_provider: str | None = None
    risk_llm_model: str | None = None
    reply_llm_provider: str | None = None
    reply_llm_model: str | None = None
    rag_enabled: bool = False
    milvus_uri: str = "http://milvus:19530"
    milvus_collection_name: str = "resolveflow_knowledge_chunks"
    rag_min_score: float = 0.12
    embedding_model: str = "local-chinese-ngram-v1"
    embedding_dimension: int = 512
    auth_enabled: bool = False
    auth_secret: str | None = None
    auth_token_ttl_minutes: int = 60
    auth_admin_username: str = "admin"
    auth_admin_password: str | None = None
    auth_supervisor_username: str = "supervisor"
    auth_supervisor_password: str | None = None
    auth_agent_username: str = "agent"
    auth_agent_password: str | None = None
    processing_max_attempts: int = 3

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
