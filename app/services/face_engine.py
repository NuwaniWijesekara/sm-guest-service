import logging
import boto3
from botocore.exceptions import ClientError
from ..config.settings import settings

logger = logging.getLogger(__name__)

class FaceEngine:
    """Singleton AWS Rekognition service wrapper — guest service (selfie side)."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.client = boto3.client(
                'rekognition',
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
                region_name=settings.aws_region,
            )
        return cls._instance

    def load(self):
        """No-op retained for backwards compatibility."""
        pass

    def search_faces_by_image(self, selfie_bytes: bytes, collection_id: str, threshold: float = 80.0) -> list[dict]:
        """
        Passes guest selfie bytes to boto3.client('rekognition').search_faces_by_image.
        Returns list of matched dicts containing face_id and similarity score.
        """
        try:
            response = self.client.search_faces_by_image(
                CollectionId=collection_id,
                Image={'Bytes': selfie_bytes},
                FaceMatchThreshold=threshold,
                MaxFaces=settings.max_match_results
            )
            matches = []
            for face_match in response.get('FaceMatches', []):
                matches.append({
                    'face_id': face_match['Face']['FaceId'],
                    'similarity': face_match.get('Similarity', 0.0)
                })
            logger.info(f"search_faces_by_image found {len(matches)} match(es) in collection {collection_id}")
            return matches
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code in ('InvalidParameterException', 'InvalidImageFormatException') and 'No face' in str(e):
                logger.warning(f"No face detected in selfie: {e}")
                return []
            elif error_code == 'ResourceNotFoundException':
                logger.warning(f"Collection {collection_id} not found in Rekognition.")
                return []
            else:
                logger.error(f"Rekognition search_faces_by_image error: {e}")
                raise

    def search_faces(self, face_id: str, collection_id: str, threshold: float = 80.0) -> list[dict]:
        """
        Searches faces by an existing Rekognition FaceId.
        """
        try:
            response = self.client.search_faces(
                CollectionId=collection_id,
                FaceId=face_id,
                FaceMatchThreshold=threshold,
                MaxFaces=settings.max_match_results
            )
            matches = []
            for face_match in response.get('FaceMatches', []):
                matches.append({
                    'face_id': face_match['Face']['FaceId'],
                    'similarity': face_match.get('Similarity', 0.0)
                })
            return matches
        except ClientError as e:
            logger.warning(f"search_faces error for {face_id} in {collection_id}: {e}")
            return []

    def index_selfie(self, selfie_bytes: bytes, collection_id: str) -> str | None:
        """
        Indexes a selfie image bytes and returns the primary FaceId string.
        """
        try:
            response = self.client.index_faces(
                CollectionId=collection_id,
                Image={'Bytes': selfie_bytes},
                DetectionAttributes=['DEFAULT'],
                MaxFaces=1,
                QualityFilter='AUTO'
            )
            face_records = response.get('FaceRecords', [])
            if face_records:
                return face_records[0]['Face']['FaceId']
            return None
        except ClientError as e:
            logger.error(f"Failed to index selfie: {e}")
            return None

face_engine = FaceEngine()