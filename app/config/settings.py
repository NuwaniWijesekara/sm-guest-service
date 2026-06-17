from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url:        str = "postgresql://postgres:postgres@postgres:5432/scanme_db"
    similarity_threshold: float = 0.4
    max_match_results:   int   = 50
    max_selfie_bytes:    int   = 15 * 1024 * 1024
    frontend_origin:     str   = "http://localhost:3000"

settings = Settings()