"""
Image storage and processing service
Handles S3 uploads, compression, resizing, and signed URLs
Supports both local file storage (development) and S3 (production)
"""

import io
import tempfile
import uuid
import hashlib
import unicodedata
from typing import Optional, Tuple, List
from datetime import datetime
from pathlib import Path
from PIL import Image
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config as BotoConfig
from fastapi import UploadFile, HTTPException
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class ImageSize:
    """Image size configurations"""

    THUMBNAIL = "thumbnail"
    MEDIUM = "medium"
    LARGE = "large"
    ORIGINAL = "original"


class ImageService:
    """Service for handling image storage and processing"""

    def __init__(self):
        """Initialize image service (S3 or local storage)"""
        # Parse size configurations
        self.thumbnail_size = tuple(map(int, settings.THUMBNAIL_SIZE.split(",")))
        self.medium_size = tuple(map(int, settings.MEDIUM_SIZE.split(",")))
        self.large_size = tuple(map(int, settings.LARGE_SIZE.split(",")))

        # Parse allowed types
        self.allowed_types = settings.ALLOWED_IMAGE_TYPES.split(",")
        self.max_size_bytes = settings.MAX_IMAGE_SIZE_MB * 1024 * 1024

        # Check if using local storage
        self.use_local_storage = settings.USE_LOCAL_STORAGE

        if self.use_local_storage:
            # Set up local storage directory
            self.upload_dir = Path(settings.LOCAL_UPLOAD_DIR)
            self.upload_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Using local file storage: {self.upload_dir.absolute()}")
        else:
            # Initialize S3 client
            s3_config = BotoConfig(
                signature_version="s3v4", region_name=settings.AWS_REGION
            )

            s3_kwargs = {
                "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
                "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
                "config": s3_config,
            }

            # Add endpoint URL if using CloudFlare R2 or MinIO
            if settings.S3_ENDPOINT_URL:
                s3_kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL

            self.s3_client = boto3.client("s3", **s3_kwargs)
            self.bucket_name = settings.S3_BUCKET_NAME
            logger.info(f"Using S3 storage: {self.bucket_name}")

    def validate_image(self, file: UploadFile) -> None:
        """
        Validate image file type and size

        Args:
            file: Uploaded file

        Raises:
            HTTPException: If validation fails
        """
        # Check content type
        if file.content_type not in self.allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid image type. Allowed types: {', '.join(self.allowed_types)}",
            )

        # Check file size
        file.file.seek(0, 2)  # Seek to end
        file_size = file.file.tell()
        file.file.seek(0)  # Reset to beginning

        if file_size > self.max_size_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"Image too large. Maximum size: {settings.MAX_IMAGE_SIZE_MB}MB",
            )

    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename to only include ASCII characters

        Args:
            filename: Original filename

        Returns:
            ASCII-only filename safe for S3 metadata
        """
        # Normalize unicode characters to ASCII equivalents
        ascii_filename = unicodedata.normalize("NFKD", filename)
        ascii_filename = ascii_filename.encode("ascii", "ignore").decode("ascii")

        # Replace any remaining non-alphanumeric characters (except . - _) with underscore
        ascii_filename = "".join(
            c if c.isalnum() or c in ".-_ " else "_" for c in ascii_filename
        )

        # Replace spaces with underscores
        ascii_filename = ascii_filename.replace(" ", "_")

        return ascii_filename

    def _generate_unique_filename(
        self, original_filename: str, size: str = "original"
    ) -> str:
        """
        Generate unique filename with hash

        Args:
            original_filename: Original file name
            size: Image size variant

        Returns:
            Unique filename
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        ext = original_filename.rsplit(".", 1)[-1].lower()

        # Create hash from original filename + timestamp
        hash_input = f"{original_filename}{timestamp}{unique_id}"
        file_hash = hashlib.md5(hash_input.encode()).hexdigest()[:8]

        if size == "original":
            return f"{timestamp}_{file_hash}.{ext}"
        else:
            return f"{timestamp}_{file_hash}_{size}.{ext}"

    def _get_s3_key(self, filename: str, folder: str = "products") -> str:
        """
        Generate S3 key with folder structure

        Args:
            filename: File name
            folder: Folder name (products, avatars, etc.)

        Returns:
            S3 key path
        """
        year_month = datetime.utcnow().strftime("%Y/%m")
        return f"{folder}/{year_month}/{filename}"

    def _compress_and_resize(
        self,
        image_data: bytes,
        target_size: Optional[Tuple[int, int]] = None,
        quality: int = 85,
    ) -> Tuple[bytes, str]:
        """
        Compress and resize image

        Args:
            image_data: Original image bytes
            target_size: Target size (width, height) or None for no resize
            quality: JPEG quality (1-100)

        Returns:
            Tuple of (compressed image bytes, format)
        """
        # Open image
        image = Image.open(io.BytesIO(image_data))

        # Convert RGBA to RGB if needed (for JPEG)
        if image.mode == "RGBA":
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[3])
            image = background
        elif image.mode not in ("RGB", "L"):
            image = image.convert("RGB")

        # Resize if target size specified
        if target_size:
            # Maintain aspect ratio
            image.thumbnail(target_size, Image.Resampling.LANCZOS)

        # Save to bytes
        output = io.BytesIO()
        format = "JPEG" if image.format not in ("PNG", "WEBP", "GIF") else image.format

        if format == "JPEG":
            image.save(output, format=format, quality=quality, optimize=True)
        elif format == "PNG":
            image.save(output, format=format, optimize=True)
        elif format == "WEBP":
            image.save(output, format=format, quality=quality)
        else:
            image.save(output, format=format)

        return output.getvalue(), format.lower()

    async def upload_image(
        self, file: UploadFile, folder: str = "products", generate_variants: bool = True
    ) -> dict:
        """
        Upload image to storage (S3 or local) with multiple size variants

        Args:
            file: Uploaded file
            folder: Folder (products, avatars, etc.)
            generate_variants: Whether to generate thumbnail/medium/large variants

        Returns:
            Dict with URLs for all variants
        """
        # Validate image
        self.validate_image(file)

        # Read image data
        image_data = await file.read()

        # Generate unique filename
        original_filename = file.filename or "image.jpg"
        sanitized_filename = self._sanitize_filename(original_filename)
        base_filename = self._generate_unique_filename(original_filename)

        try:
            if self.use_local_storage:
                # Upload to local filesystem
                return await self._upload_local(
                    image_data=image_data,
                    original_filename=original_filename,
                    base_filename=base_filename,
                    folder=folder,
                    generate_variants=generate_variants,
                )
            else:
                # Upload to S3
                return await self._upload_s3(
                    image_data=image_data,
                    original_filename=original_filename,
                    sanitized_filename=sanitized_filename,
                    base_filename=base_filename,
                    folder=folder,
                    generate_variants=generate_variants,
                )

        except Exception as e:
            logger.error(f"Image upload error: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Failed to upload image: {str(e)}"
            )

    async def _upload_local(
        self,
        image_data: bytes,
        original_filename: str,
        base_filename: str,
        folder: str,
        generate_variants: bool,
    ) -> dict:
        """Upload image to local filesystem"""
        results = {}

        # Create folder structure
        year_month = datetime.utcnow().strftime("%Y/%m")
        folder_path = self.upload_dir / folder / year_month
        folder_path.mkdir(parents=True, exist_ok=True)

        # Upload original
        original_path = folder_path / base_filename
        compressed_data, format_type = self._compress_and_resize(
            image_data, target_size=None, quality=settings.IMAGE_QUALITY
        )

        with open(original_path, "wb") as f:
            f.write(compressed_data)

        # Generate URL path (relative to uploads directory)
        original_key = f"{folder}/{year_month}/{base_filename}"
        results["original"] = f"/uploads/{original_key}"
        results["s3_key"] = original_key

        # Generate and save variants
        if generate_variants:
            variants = [
                (ImageSize.THUMBNAIL, self.thumbnail_size),
                (ImageSize.MEDIUM, self.medium_size),
                (ImageSize.LARGE, self.large_size),
            ]

            for size_name, size_tuple in variants:
                variant_filename = self._generate_unique_filename(
                    original_filename, size_name
                )
                variant_path = folder_path / variant_filename

                variant_data, variant_format = self._compress_and_resize(
                    image_data, target_size=size_tuple, quality=settings.IMAGE_QUALITY
                )

                with open(variant_path, "wb") as f:
                    f.write(variant_data)

                variant_key = f"{folder}/{year_month}/{variant_filename}"
                results[size_name] = f"/uploads/{variant_key}"

        logger.info(f"Successfully uploaded image to local storage: {original_key}")
        return results

    async def _upload_s3(
        self,
        image_data: bytes,
        original_filename: str,
        sanitized_filename: str,
        base_filename: str,
        folder: str,
        generate_variants: bool,
    ) -> dict:
        """Upload image to S3"""
        results = {}

        try:
            # Upload original
            original_key = self._get_s3_key(base_filename, folder)
            compressed_data, format_type = self._compress_and_resize(
                image_data,
                target_size=None,  # Keep original size
                quality=settings.IMAGE_QUALITY,
            )

            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=original_key,
                Body=compressed_data,
                ContentType=f"image/{format_type}",
                CacheControl="max-age=31536000",  # 1 year
                Metadata={
                    "original-filename": sanitized_filename,
                    "uploaded-at": datetime.utcnow().isoformat(),
                },
            )

            results["original"] = self._get_public_url(original_key)
            results["s3_key"] = original_key

            # Generate and upload variants
            if generate_variants:
                variants = [
                    (ImageSize.THUMBNAIL, self.thumbnail_size),
                    (ImageSize.MEDIUM, self.medium_size),
                    (ImageSize.LARGE, self.large_size),
                ]

                for size_name, size_tuple in variants:
                    variant_filename = self._generate_unique_filename(
                        original_filename, size_name
                    )
                    variant_key = self._get_s3_key(variant_filename, folder)

                    variant_data, variant_format = self._compress_and_resize(
                        image_data,
                        target_size=size_tuple,
                        quality=settings.IMAGE_QUALITY,
                    )

                    self.s3_client.put_object(
                        Bucket=self.bucket_name,
                        Key=variant_key,
                        Body=variant_data,
                        ContentType=f"image/{variant_format}",
                        CacheControl="max-age=31536000",
                        Metadata={"variant": size_name, "original-key": original_key},
                    )

                    results[size_name] = self._get_public_url(variant_key)

            logger.info(f"Successfully uploaded image to S3: {original_key}")
            return results

        except ClientError as e:
            logger.error(f"S3 upload error: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to upload image to S3")

    def _get_public_url(self, s3_key: str) -> str:
        """
        Get public URL for S3 object

        Args:
            s3_key: S3 object key

        Returns:
            Public URL
        """
        if settings.CDN_BASE_URL:
            # Use CDN URL if configured
            return f"{settings.CDN_BASE_URL.rstrip('/')}/{s3_key}"
        elif settings.S3_ENDPOINT_URL:
            # Use custom endpoint (R2, MinIO)
            return f"{settings.S3_ENDPOINT_URL.rstrip('/')}/{settings.S3_BUCKET_NAME}/{s3_key}"
        else:
            # Use standard S3 URL
            return f"https://{settings.S3_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/{s3_key}"

    def generate_presigned_url(self, s3_key: str, expiration: int = 3600) -> str:
        """
        Generate presigned URL for private objects

        Args:
            s3_key: S3 object key
            expiration: URL expiration in seconds (default 1 hour)

        Returns:
            Presigned URL
        """
        if self.use_local_storage:
            raise HTTPException(
                status_code=503,
                detail="Signed URLs require object storage",
            )

        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": s3_key},
                ExpiresIn=expiration,
            )
            return url
        except ClientError as e:
            logger.error(f"Failed to generate presigned URL: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to generate signed URL")

    async def delete_image(self, s3_key: str) -> bool:
        """
        Delete image from S3

        Args:
            s3_key: S3 object key

        Returns:
            True if successful
        """
        if self.use_local_storage:
            upload_root = self.upload_dir.resolve()
            image_path = (upload_root / s3_key).resolve()
            try:
                image_path.relative_to(upload_root)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid image key")

            if not image_path.is_file():
                return False
            image_path.unlink()
            logger.info(f"Deleted local image: {s3_key}")
            return True

        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            logger.info(f"Deleted image: {s3_key}")
            return True
        except ClientError as e:
            logger.error(f"Failed to delete image: {str(e)}")
            return False

    def local_storage_is_healthy(self) -> bool:
        """Probe that the configured local upload directory is writable."""
        if not self.use_local_storage:
            return False
        try:
            self.upload_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=self.upload_dir) as probe:
                probe.write(b"ok")
                probe.flush()
            return True
        except OSError:
            return False

    async def delete_images(self, s3_keys: List[str]) -> dict:
        """
        Delete multiple images from the configured storage backend.

        Args:
            s3_keys: List of storage object keys

        Returns:
            Dict with success/failure counts
        """
        if not s3_keys:
            return {"deleted": 0, "failed": 0}

        if self.use_local_storage:
            deleted = 0
            for s3_key in s3_keys:
                try:
                    if await self.delete_image(s3_key):
                        deleted += 1
                except OSError as e:
                    logger.error(f"Failed to delete local image {s3_key}: {str(e)}")

            failed = len(s3_keys) - deleted
            logger.info(f"Batch delete: {deleted} succeeded, {failed} failed")
            return {"deleted": deleted, "failed": failed}

        objects = [{"Key": key} for key in s3_keys]

        try:
            response = self.s3_client.delete_objects(
                Bucket=self.bucket_name, Delete={"Objects": objects}
            )

            deleted = len(response.get("Deleted", []))
            failed = len(response.get("Errors", []))

            logger.info(f"Batch delete: {deleted} succeeded, {failed} failed")
            return {"deleted": deleted, "failed": failed}

        except ClientError as e:
            logger.error(f"Batch delete error: {str(e)}")
            return {"deleted": 0, "failed": len(s3_keys)}

    def get_image_info(self, s3_key: str) -> Optional[dict]:
        """
        Get image metadata from S3

        Args:
            s3_key: S3 object key

        Returns:
            Dict with image info or None if not found
        """
        try:
            response = self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)

            return {
                "size": response["ContentLength"],
                "content_type": response["ContentType"],
                "last_modified": response["LastModified"],
                "etag": response["ETag"],
                "metadata": response.get("Metadata", {}),
            }
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return None
            logger.error(f"Failed to get image info: {str(e)}")
            return None


# Singleton instance
image_service = ImageService()
