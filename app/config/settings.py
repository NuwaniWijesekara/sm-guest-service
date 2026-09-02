from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    guest_database_url:        str = "postgresql://postgres:postgres@postgres:5432/guest_db"
    photographer_database_url: str = "postgresql://postgres:postgres@postgres:5432/scanme_db"
    redis_url:                 str = "redis://localhost:6379/0"
    aws_access_key_id:         str = ""
    aws_secret_access_key:     str = ""
    aws_region:                str = "ap-south-1"
    s3_bucket_name:            str = ""
    aws_s3_bucket_name:        str = ""
    similarity_threshold:      float = 80.0
    max_match_results:         int   = 50
    max_selfie_bytes:          int   = 15 * 1024 * 1024
    frontend_origin:           str   = "http://localhost:3000"
    face_det_size:             int   = 1024
    face_det_thresh:           float = 0.4
    jwt_secret:                str   = "change_me_in_production"
    jwt_algorithm:             str   = "HS256"
    jwt_expire_minutes:        int   = 10080
    google_client_id:          str   = ""

settings = Settings()