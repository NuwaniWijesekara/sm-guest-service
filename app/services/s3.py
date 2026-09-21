import os
import logging
import boto3
from botocore.config import Config
from urllib.parse import urlparse, unquote
from ..config.settings import settings

logger = logging.getLogger(__name__)

class S3Service:
    def __init__(self):
        region = (
            getattr(settings, 'aws_region', None)
            or os.getenv('AWS_REGION')
            or 'ap-south-1'
        )
        access_key = (
            getattr(settings, 'aws_access_key_id', None)
            or os.getenv('AWS_ACCESS_KEY_ID')
        )
        secret_key = (
            getattr(settings, 'aws_secret_access_key', None)
            or os.getenv('AWS_SECRET_ACCESS_KEY')
        )
        self.bucket = (
            getattr(settings, 's3_bucket_name', None)
            or getattr(settings, 'aws_s3_bucket_name', None)
            or os.getenv('AWS_S3_BUCKET_NAME')
            or os.getenv('S3_BUCKET_NAME')
            or ''
        )

        endpoint_url = f"https://s3.{region}.amazonaws.com"

        self.client = boto3.client(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            endpoint_url=endpoint_url,
            config=Config(
                signature_version='s3v4',
                s3={'addressing_style': 'virtual'}
            )
        )

    def _extract_key(self, url_or_key: str) -> str:
        if not url_or_key:
            return ""
        clean_url = url_or_key.split('?')[0]
        if "events/" in clean_url:
            key = "events/" + clean_url.split("events/", 1)[1]
        elif clean_url.startswith("http://") or clean_url.startswith("https://"):
            key = urlparse(clean_url).path.lstrip('/')
        else:
            key = clean_url.lstrip('/')
        return unquote(key)

    def generate_presigned_url(self, url_or_key: str | None, expiration: int = 3600) -> str | None:
        if not url_or_key:
            return None
        
        extracted_key = self._extract_key(url_or_key)
        bucket_name = (
            self.bucket
            or os.getenv('AWS_S3_BUCKET_NAME')
            or os.getenv('S3_BUCKET_NAME')
        )
        
        try:
            return self.client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': extracted_key},
                ExpiresIn=expiration
            )
        except Exception as e:
            logger.error(f"Failed to generate presigned URL for key '{extracted_key}' in bucket '{bucket_name}': {e}")
            return url_or_key

s3_service = S3Service()
