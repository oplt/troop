import asyncio
from dataclasses import dataclass
from enum import StrEnum
from functools import cached_property

from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)


class StorageNotConfiguredError(RuntimeError):
    pass


class ObjectStorageError(RuntimeError):
    pass


class StorageAssetClass(StrEnum):
    PRIVATE = "private"
    PUBLIC_ASSET = "public_asset"


@dataclass(frozen=True)
class StoredObject:
    object_key: str
    bucket: str
    access_url: str | None = None


class ObjectStorage:
    @property
    def is_configured(self) -> bool:
        return bool(settings.STORAGE_BUCKET)

    def private_bucket(self) -> str:
        return settings.STORAGE_BUCKET

    def public_asset_bucket(self) -> str:
        if settings.STORAGE_PUBLIC_ASSET_BUCKET:
            return settings.STORAGE_PUBLIC_ASSET_BUCKET
        return settings.STORAGE_BUCKET

    def _bucket_for(self, asset_class: StorageAssetClass) -> str:
        if asset_class == StorageAssetClass.PUBLIC_ASSET:
            return self.public_asset_bucket()
        return self.private_bucket()

    def _bucket_allows_public_reads(self, bucket: str) -> bool:
        if bucket != self.private_bucket():
            return True
        return settings.STORAGE_PUBLIC_READ and not settings.is_production

    def _infer_bucket(self, object_key: str) -> str:
        if object_key.startswith("avatars/"):
            return self.public_asset_bucket()
        return self.private_bucket()

    @cached_property
    def _client(self):
        try:
            import boto3
            from botocore.client import Config
        except ImportError as exc:
            raise ObjectStorageError(
                "Object storage dependencies are not installed. Run `uv sync` in `backend/`."
            ) from exc

        session = boto3.session.Session()
        return session.client(
            "s3",
            region_name=settings.STORAGE_REGION,
            endpoint_url=settings.STORAGE_ENDPOINT_URL or None,
            aws_access_key_id=settings.STORAGE_ACCESS_KEY or None,
            aws_secret_access_key=settings.STORAGE_SECRET_KEY or None,
            use_ssl=settings.STORAGE_USE_SSL,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path" if settings.STORAGE_FORCE_PATH_STYLE else "auto"},
                connect_timeout=settings.STORAGE_CONNECT_TIMEOUT_SECONDS,
                read_timeout=settings.STORAGE_READ_TIMEOUT_SECONDS,
                retries={"max_attempts": settings.STORAGE_MAX_ATTEMPTS, "mode": "standard"},
            ),
        )

    async def ensure_bucket(self) -> None:
        if not self.is_configured or not settings.STORAGE_AUTO_CREATE_BUCKET:
            return

        await self._ensure_bucket(
            self.private_bucket(),
            public_read=self._bucket_allows_public_reads(self.private_bucket()),
        )
        public_bucket = settings.STORAGE_PUBLIC_ASSET_BUCKET
        if public_bucket and public_bucket != self.private_bucket():
            await self._ensure_bucket(public_bucket, public_read=True)

    async def _ensure_bucket(self, bucket: str, *, public_read: bool) -> None:
        def _ensure() -> None:
            try:
                self._client.head_bucket(Bucket=bucket)
            except Exception:
                create_kwargs = {"Bucket": bucket}
                if settings.STORAGE_REGION != "us-east-1":
                    create_kwargs["CreateBucketConfiguration"] = {
                        "LocationConstraint": settings.STORAGE_REGION
                    }
                self._client.create_bucket(**create_kwargs)

            if public_read:
                self._client.put_bucket_policy(
                    Bucket=bucket,
                    Policy=(
                        "{"
                        '"Version":"2012-10-17",'
                        '"Statement":[{'
                        '"Effect":"Allow",'
                        '"Principal":"*",'
                        '"Action":["s3:GetObject"],'
                        f'"Resource":["arn:aws:s3:::{bucket}/*"]'
                        "}]}"
                    ),
                )

        try:
            await asyncio.to_thread(_ensure)
        except Exception as exc:
            logger.warning("failed to ensure storage bucket %s: %s", bucket, exc)

    async def upload_bytes(
        self,
        *,
        object_key: str,
        body: bytes,
        content_type: str,
        asset_class: StorageAssetClass = StorageAssetClass.PRIVATE,
    ) -> StoredObject:
        if not self.is_configured:
            raise StorageNotConfiguredError(
                "Object storage is not configured. Set STORAGE_BUCKET and storage credentials."
            )

        bucket = self._bucket_for(asset_class)
        public_object = (
            asset_class == StorageAssetClass.PUBLIC_ASSET
            and self._bucket_allows_public_reads(bucket)
        )
        cache_control = (
            "public, max-age=31536000, immutable" if public_object else "private, no-store"
        )

        def _upload() -> None:
            put_kwargs: dict = {
                "Bucket": bucket,
                "Key": object_key,
                "Body": body,
                "ContentType": content_type,
                "CacheControl": cache_control,
            }
            if public_object:
                put_kwargs["ACL"] = "public-read"
            self._client.put_object(**put_kwargs)

        try:
            await asyncio.to_thread(_upload)
        except Exception as exc:
            label = "public asset" if asset_class == StorageAssetClass.PUBLIC_ASSET else "object"
            raise ObjectStorageError(f"Failed to upload {label} to object storage") from exc

        access_url = self.public_url_for(object_key, bucket=bucket) if public_object else None
        return StoredObject(object_key=object_key, bucket=bucket, access_url=access_url)

    async def presigned_get_url(
        self,
        object_key: str,
        *,
        bucket: str | None = None,
        expires_seconds: int | None = None,
    ) -> str:
        if not self.is_configured:
            raise StorageNotConfiguredError(
                "Object storage is not configured. Set STORAGE_BUCKET and storage credentials."
            )
        target_bucket = bucket or self._infer_bucket(object_key)
        ttl = expires_seconds or settings.STORAGE_PRESIGNED_URL_TTL_SECONDS

        def _presign() -> str:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": target_bucket, "Key": object_key},
                ExpiresIn=max(60, ttl),
            )

        try:
            return await asyncio.to_thread(_presign)
        except Exception as exc:
            raise ObjectStorageError(
                f"Failed to create presigned URL for object {object_key}"
            ) from exc

    async def resolve_access_url(
        self,
        object_key: str | None,
        *,
        asset_class: StorageAssetClass = StorageAssetClass.PRIVATE,
    ) -> str | None:
        if not object_key or not self.is_configured:
            return None
        bucket = self._bucket_for(asset_class)
        if asset_class == StorageAssetClass.PUBLIC_ASSET and self._bucket_allows_public_reads(
            bucket
        ):
            return self.public_url_for(object_key, bucket=bucket)
        return await self.presigned_get_url(object_key, bucket=bucket)

    async def download_bytes(self, *, object_key: str, bucket: str | None = None) -> bytes:
        if not self.is_configured:
            raise StorageNotConfiguredError(
                "Object storage is not configured. Set STORAGE_BUCKET and storage credentials."
            )
        target_bucket = bucket or self._infer_bucket(object_key)

        def _download() -> bytes:
            resp = self._client.get_object(Bucket=target_bucket, Key=object_key)
            return resp["Body"].read()

        try:
            return await asyncio.to_thread(_download)
        except Exception as exc:
            raise ObjectStorageError(f"Failed to download object {object_key}") from exc

    async def delete_object(self, object_key: str | None, *, bucket: str | None = None) -> None:
        if not self.is_configured or not object_key:
            return
        target_bucket = bucket or self._infer_bucket(object_key)

        def _delete() -> None:
            self._client.delete_object(Bucket=target_bucket, Key=object_key)

        try:
            await asyncio.to_thread(_delete)
        except Exception as exc:
            logger.warning("failed to delete storage object %s: %s", object_key, exc)

    def public_url_for(self, object_key: str, *, bucket: str | None = None) -> str:
        target_bucket = bucket or self.private_bucket()
        if settings.STORAGE_PUBLIC_BASE_URL and target_bucket == self.private_bucket():
            return f"{settings.STORAGE_PUBLIC_BASE_URL.rstrip('/')}/{object_key}"

        if settings.STORAGE_ENDPOINT_URL:
            base = settings.STORAGE_ENDPOINT_URL.rstrip("/")
            return f"{base}/{target_bucket}/{object_key}"

        if settings.STORAGE_REGION == "us-east-1":
            return f"https://{target_bucket}.s3.amazonaws.com/{object_key}"

        return f"https://{target_bucket}.s3.{settings.STORAGE_REGION}.amazonaws.com/{object_key}"


object_storage = ObjectStorage()
