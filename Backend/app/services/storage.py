"""
VoiceCraft Platform — MinIO Object Storage Service
Self-hosted, free S3-compatible storage.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import BinaryIO

from minio import Minio
from minio.error import S3Error
from minio.commonconfig import ENABLED, Filter
from minio.lifecycleconfig import LifecycleConfig, Rule, Expiration

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class StorageService:
    """Thin wrapper around MinIO client with auto-bucket creation."""

    _client: Minio | None = None

    @property
    def client(self) -> Minio:
        if self._client is None:
            self._client = Minio(
                endpoint=settings.MINIO_ENDPOINT,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=settings.MINIO_SECURE,
            )
        return self._client

    def initialize_buckets(self) -> None:
        """Ensure all required buckets exist with lifecycle policies."""
        buckets = [
            settings.MINIO_BUCKET_VOICES,
            settings.MINIO_BUCKET_AUDIO,
            settings.MINIO_BUCKET_UPLOADS,
            settings.MINIO_BUCKET_MODELS,
        ]
        for bucket in buckets:
            try:
                if not self.client.bucket_exists(bucket):
                    self.client.make_bucket(bucket)
                    logger.info("Created bucket: %s", bucket)

                    # Set lifecycle: auto-delete temp uploads after 7 days
                    if bucket == settings.MINIO_BUCKET_UPLOADS:
                        self._set_lifecycle(bucket, expiry_days=7)
            except S3Error as e:
                logger.error("Failed to create bucket %s: %s", bucket, e)

    def _set_lifecycle(self, bucket: str, expiry_days: int) -> None:
        config = LifecycleConfig([
            Rule(
                ENABLED,
                rule_filter=Filter(prefix="temp/"),
                rule_id="temp-expiry",
                expiration=Expiration(days=expiry_days),
            )
        ])
        try:
            self.client.set_bucket_lifecycle(bucket, config)
        except Exception as e:
            logger.warning("Could not set lifecycle on %s: %s", bucket, e)

    # ─────────────────────────────────────────────────────────────
    #  Upload
    # ─────────────────────────────────────────────────────────────

    def upload_file(
        self,
        bucket: str,
        object_key: str,
        file_path: str | Path,
        content_type: str = "application/octet-stream",
        metadata: dict | None = None,
    ) -> str:
        """Upload file from disk → MinIO. Returns public-style URL."""
        file_path = Path(file_path)
        file_size = file_path.stat().st_size

        self.client.fput_object(
            bucket_name=bucket,
            object_name=object_key,
            file_path=str(file_path),
            content_type=content_type,
            metadata=metadata or {},
        )
        logger.debug("Uploaded %s → %s/%s (%d bytes)", file_path.name, bucket, object_key, file_size)
        return f"{bucket}/{object_key}"

    def upload_bytes(
        self,
        bucket: str,
        object_key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict | None = None,
    ) -> str:
        """Upload raw bytes → MinIO."""
        self.client.put_object(
            bucket_name=bucket,
            object_name=object_key,
            data=io.BytesIO(data),
            length=len(data),
            content_type=content_type,
            metadata=metadata or {},
        )
        return f"{bucket}/{object_key}"

    def upload_fileobj(
        self,
        bucket: str,
        object_key: str,
        fileobj: BinaryIO,
        length: int = -1,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload file-like object → MinIO."""
        self.client.put_object(
            bucket_name=bucket,
            object_name=object_key,
            data=fileobj,
            length=length,
            content_type=content_type,
        )
        return f"{bucket}/{object_key}"

    # ─────────────────────────────────────────────────────────────
    #  Download
    # ─────────────────────────────────────────────────────────────

    def download_file(
        self,
        bucket: str,
        object_key: str,
        dest_path: str | Path,
    ) -> Path:
        """Download object → local file. Returns path."""
        dest_path = Path(dest_path)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        self.client.fget_object(bucket, object_key, str(dest_path))
        return dest_path

    def download_bytes(self, bucket: str, object_key: str) -> bytes:
        """Download object → bytes."""
        response = self.client.get_object(bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    # ─────────────────────────────────────────────────────────────
    #  Presigned URLs (for direct frontend download)
    # ─────────────────────────────────────────────────────────────

    def presigned_get_url(
        self,
        bucket: str,
        object_key: str,
        expires_seconds: int = 3600,
    ) -> str:
        """Generate presigned download URL valid for expires_seconds."""
        from datetime import timedelta
        url = self.client.presigned_get_object(
            bucket_name=bucket,
            object_name=object_key,
            expires=timedelta(seconds=expires_seconds),
        )
        return url

    def presigned_put_url(
        self,
        bucket: str,
        object_key: str,
        expires_seconds: int = 3600,
    ) -> str:
        """Generate presigned upload URL (for direct client uploads)."""
        from datetime import timedelta
        return self.client.presigned_put_object(
            bucket_name=bucket,
            object_name=object_key,
            expires=timedelta(seconds=expires_seconds),
        )

    # ─────────────────────────────────────────────────────────────
    #  Utilities
    # ─────────────────────────────────────────────────────────────

    def delete_object(self, bucket: str, object_key: str) -> None:
        try:
            self.client.remove_object(bucket, object_key)
        except S3Error as e:
            logger.warning("Delete error %s/%s: %s", bucket, object_key, e)

    def object_exists(self, bucket: str, object_key: str) -> bool:
        try:
            self.client.stat_object(bucket, object_key)
            return True
        except S3Error:
            return False

    def list_objects(self, bucket: str, prefix: str = "") -> list[str]:
        try:
            objects = self.client.list_objects(bucket, prefix=prefix, recursive=True)
            return [obj.object_name for obj in objects]
        except S3Error:
            return []

    def get_object_size(self, bucket: str, object_key: str) -> int:
        try:
            stat = self.client.stat_object(bucket, object_key)
            return stat.size
        except S3Error:
            return 0

    # ─────────────────────────────────────────────────────────────
    #  Convenience object key builders
    # ─────────────────────────────────────────────────────────────

    @staticmethod
    def voice_profile_key(org_id: str, profile_id: str, filename: str) -> str:
        return f"orgs/{org_id}/profiles/{profile_id}/{filename}"

    @staticmethod
    def training_sample_key(org_id: str, profile_id: str, sample_id: str, ext: str = "wav") -> str:
        return f"orgs/{org_id}/profiles/{profile_id}/samples/{sample_id}.{ext}"

    @staticmethod
    def generated_audio_key(org_id: str, job_id: str, ext: str = "mp3") -> str:
        return f"orgs/{org_id}/generated/{job_id}.{ext}"

    @staticmethod
    def detection_result_key(org_id: str, result_id: str) -> str:
        return f"orgs/{org_id}/detections/{result_id}/input.wav"

    @staticmethod
    def fine_tune_model_key(org_id: str, profile_id: str) -> str:
        return f"orgs/{org_id}/models/{profile_id}/"

    @staticmethod
    def composite_reference_key(org_id: str, profile_id: str) -> str:
        return f"orgs/{org_id}/profiles/{profile_id}/composite_reference.wav"


# Singleton
_storage_instance: StorageService | None = None


def get_storage() -> StorageService:
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = StorageService()
    return _storage_instance
