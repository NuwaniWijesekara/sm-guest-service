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
    max_match_results:         int   = 50
    max_selfie_bytes:          int   = 15 * 1024 * 1024
    frontend_origin:           str   = "http://localhost:3000"
    # Required — must match sm-photographer-service (the token issuer). No
    # default, so a missing JWT_SECRET fails at startup instead of accepting
    # tokens signed with a publicly known value.
    jwt_secret:                str
    jwt_algorithm:             str   = "HS256"
    # Lifetime of presigned photo URLs handed to guests. Kept short so a
    # leaked/forwarded URL stops working soon after access is revoked.
    photo_url_ttl_seconds:     int   = 3600

settings = Settings()