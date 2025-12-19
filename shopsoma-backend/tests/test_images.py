"""
Unit tests for image upload and storage
"""
import pytest
import io
from PIL import Image
from httpx import AsyncClient
from unittest.mock import Mock, patch, AsyncMock
from fastapi import UploadFile

from app.services.image_service import image_service


class TestImageValidation:
    """Test image validation"""

    @pytest.mark.asyncio
    async def test_valid_image_types(self):
        """Test that valid image types are accepted"""
        valid_types = ["image/jpeg", "image/png", "image/webp", "image/gif"]

        for content_type in valid_types:
            # Create mock file
            file = Mock(spec=UploadFile)
            file.content_type = content_type
            file.file = io.BytesIO(b"fake image data")
            file.file.seek(0, 2)  # Seek to end
            file.file.tell = Mock(return_value=1024)  # 1KB

            # Should not raise
            image_service.validate_image(file)

    @pytest.mark.asyncio
    async def test_invalid_image_type(self):
        """Test that invalid image types are rejected"""
        file = Mock(spec=UploadFile)
        file.content_type = "application/pdf"
        file.file = io.BytesIO(b"fake data")
        file.file.seek(0, 2)
        file.file.tell = Mock(return_value=1024)

        with pytest.raises(Exception) as exc:
            image_service.validate_image(file)

        assert "Invalid image type" in str(exc.value.detail)

    @pytest.mark.asyncio
    async def test_image_too_large(self):
        """Test that oversized images are rejected"""
        file = Mock(spec=UploadFile)
        file.content_type = "image/jpeg"
        file.file = io.BytesIO(b"fake data")
        file.file.seek(0, 2)
        # Simulate 15MB file (exceeds 10MB limit)
        file.file.tell = Mock(return_value=15 * 1024 * 1024)

        with pytest.raises(Exception) as exc:
            image_service.validate_image(file)

        assert "too large" in str(exc.value.detail)


class TestImageCompression:
    """Test image compression and resizing"""

    def create_test_image(self, size=(1000, 1000), mode='RGB', format='JPEG'):
        """Helper to create test image"""
        img = Image.new(mode, size, color='red')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format=format)
        return img_bytes.getvalue()

    def test_compress_jpeg(self):
        """Test JPEG compression"""
        original_data = self.create_test_image()
        compressed, format_type = image_service._compress_and_resize(
            original_data,
            target_size=None,
            quality=85
        )

        assert format_type == 'jpeg'
        assert len(compressed) < len(original_data)  # Should be compressed

    def test_resize_image(self):
        """Test image resizing"""
        original_data = self.create_test_image(size=(2000, 2000))
        resized, _ = image_service._compress_and_resize(
            original_data,
            target_size=(800, 800),
            quality=85
        )

        # Check resized image dimensions
        img = Image.open(io.BytesIO(resized))
        assert img.width <= 800
        assert img.height <= 800

    def test_rgba_to_rgb_conversion(self):
        """Test RGBA to RGB conversion for JPEG"""
        original_data = self.create_test_image(mode='RGBA', format='PNG')
        compressed, format_type = image_service._compress_and_resize(
            original_data,
            target_size=None,
            quality=85
        )

        # Should convert to JPEG
        img = Image.open(io.BytesIO(compressed))
        assert img.mode == 'RGB'

    def test_maintain_aspect_ratio(self):
        """Test that resizing maintains aspect ratio"""
        # Create 2000x1000 image (2:1 ratio)
        original_data = self.create_test_image(size=(2000, 1000))
        resized, _ = image_service._compress_and_resize(
            original_data,
            target_size=(800, 800),  # Max dimensions
            quality=85
        )

        img = Image.open(io.BytesIO(resized))
        # Should maintain 2:1 ratio, so width should be 800, height should be 400
        assert img.width == 800
        assert img.height == 400


class TestFilenameGeneration:
    """Test unique filename generation"""

    def test_unique_filenames(self):
        """Test that generated filenames are unique"""
        filenames = set()
        for _ in range(100):
            filename = image_service._generate_unique_filename("test.jpg")
            assert filename not in filenames
            filenames.add(filename)

    def test_filename_with_size_variant(self):
        """Test filename generation for size variants"""
        original = image_service._generate_unique_filename("test.jpg", "original")
        thumbnail = image_service._generate_unique_filename("test.jpg", "thumbnail")
        medium = image_service._generate_unique_filename("test.jpg", "medium")

        assert "_thumbnail" in thumbnail
        assert "_medium" in medium
        assert "_original" not in original and "_thumbnail" not in original

    def test_s3_key_structure(self):
        """Test S3 key path structure"""
        key = image_service._get_s3_key("test.jpg", "products")

        # Should have structure: folder/year/month/filename
        parts = key.split('/')
        assert len(parts) == 4
        assert parts[0] == "products"
        assert len(parts[1]) == 4  # Year
        assert len(parts[2]) == 2  # Month


class TestImageEndpoints:
    """Test image API endpoints"""

    @pytest.mark.asyncio
    async def test_upload_image_unauthorized(self, client: AsyncClient):
        """Test image upload without authentication"""
        # Create fake image file
        img = Image.new('RGB', (100, 100), color='red')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG')
        img_bytes.seek(0)

        files = {'file': ('test.jpg', img_bytes, 'image/jpeg')}
        response = await client.post("/api/v1/images/upload", files=files)

        assert response.status_code == 403  # Not authenticated

    @pytest.mark.asyncio
    async def test_upload_image_as_customer(self, client: AsyncClient, customer_user):
        """Test that customers cannot upload images"""
        img = Image.new('RGB', (100, 100), color='red')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG')
        img_bytes.seek(0)

        files = {'file': ('test.jpg', img_bytes, 'image/jpeg')}
        response = await client.post(
            "/api/v1/images/upload",
            files=files,
            headers=customer_user["headers"]
        )

        assert response.status_code == 403  # Customers can't upload

    @pytest.mark.asyncio
    async def test_upload_image_success(
        self,
        client: AsyncClient,
        vendor_user
    ):
        """Test successful image upload"""
        # Mock S3 client
        with patch.object(image_service, 's3_client') as mock_s3:
            mock_s3.put_object = Mock()

            img = Image.new('RGB', (100, 100), color='red')
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='JPEG')
            img_bytes.seek(0)

            files = {'file': ('test.jpg', img_bytes, 'image/jpeg')}
            response = await client.post(
                "/api/v1/images/upload",
                files=files,
                headers=vendor_user["headers"]
            )

            assert response.status_code == 201
            data = response.json()
            assert 'original' in data
            assert 'thumbnail' in data
            assert 'medium' in data
            assert 'large' in data
            assert 's3_key' in data

    @pytest.mark.asyncio
    async def test_batch_upload_limit(self, client: AsyncClient, vendor_user):
        """Test batch upload respects 10 image limit"""
        # Try to upload 11 images
        files = []
        for i in range(11):
            img = Image.new('RGB', (100, 100), color='red')
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='JPEG')
            img_bytes.seek(0)
            files.append(('files', (f'test{i}.jpg', img_bytes, 'image/jpeg')))

        response = await client.post(
            "/api/v1/images/upload/batch",
            files=files,
            headers=vendor_user["headers"]
        )

        assert response.status_code == 400
        assert "Maximum 10 images" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_generate_signed_url(self, client: AsyncClient, vendor_user):
        """Test signed URL generation"""
        request_data = {
            "s3_key": "products/2025/11/test.jpg",
            "expiration": 3600
        }

        with patch.object(image_service, 's3_client') as mock_s3:
            mock_s3.generate_presigned_url = Mock(
                return_value="https://signed-url.com/image.jpg"
            )

            response = await client.post(
                "/api/v1/images/signed-url",
                json=request_data,
                headers=vendor_user["headers"]
            )

            assert response.status_code == 200
            data = response.json()
            assert 'url' in data
            assert 'expires_in' in data
            assert 'expires_at' in data

    @pytest.mark.asyncio
    async def test_delete_image(self, client: AsyncClient, vendor_user):
        """Test image deletion"""
        with patch.object(image_service, 's3_client') as mock_s3:
            mock_s3.delete_object = Mock()

            s3_key = "products/2025/11/test.jpg"
            response = await client.delete(
                f"/api/v1/images/{s3_key}",
                headers=vendor_user["headers"]
            )

            assert response.status_code == 200
            data = response.json()
            assert data['success'] is True

    @pytest.mark.asyncio
    async def test_image_health_check(self, client: AsyncClient):
        """Test image service health check endpoint"""
        with patch.object(image_service, 's3_client') as mock_s3:
            mock_s3.head_bucket = Mock()

            response = await client.get("/api/v1/images/health")

            assert response.status_code == 200
            data = response.json()
            assert data['status'] == 'healthy'
            assert 'bucket' in data


class TestURLGeneration:
    """Test URL generation for different configurations"""

    def test_standard_s3_url(self):
        """Test standard S3 URL generation"""
        url = image_service._get_public_url("products/2025/11/test.jpg")

        assert "s3" in url
        assert "products/2025/11/test.jpg" in url

    @patch('app.core.config.settings.CDN_BASE_URL', 'https://cdn.shopsoma.com')
    def test_cdn_url(self):
        """Test CDN URL generation when configured"""
        url = image_service._get_public_url("products/2025/11/test.jpg")

        assert url.startswith('https://cdn.shopsoma.com')
        assert "products/2025/11/test.jpg" in url
