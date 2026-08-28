from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = ""
    postgres_db: str = "postgres"

    pinecone_api_key: str = ""
    pinecone_index_name: str = "cookbook-rag"
    pinecone_sparse_index_name: str = "cookbook-rag-sparse"
    pinecone_sparse_model: str = "pinecone-sparse-english-v0"
    pinecone_namespace: str = "documents"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"

   
    gemini_api_key: str = ""
    gemini_generation_model: str = "gemini-3.6-flash"
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_embedding_dimensions: int = 1024

    ocr_enabled: bool = True
    ocr_model: str = ""
    ocr_max_bytes: int = 15_000_000
    ocr_max_output_tokens: int = 8192

    chunk_strategy: str = "recursive"
    chunk_size: int = 1000
    chunk_overlap: int = 150
    chunk_buffer_size: int = 1
    chunk_breakpoint_percentile: float = 90.0
    chunk_max_chars: int = 1500
    chunk_min_chars: int = 200

    semantic_top_k: int = 50
    keyword_top_k: int = 50
    hybrid_top_k: int = 20
    rrf_k: int = 60

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,http://localhost:5175,http://127.0.0.1:5175,http://localhost:5175/api,"

    documents_dir: str = "documents"

    @property
    def postgres_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
