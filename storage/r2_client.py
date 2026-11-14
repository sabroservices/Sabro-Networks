import os
import io
import mimetypes

class CloudflareR2Client:
    """
    Cloudflare R2 Object Storage Client for Sabro Networks.
    Provides S3-compatible zero-cost storage for avatars, customer documents,
    database exports, and audit backups.
    """
    def __init__(self):
        self.account_id = os.environ.get("CLOUDFLARE_R2_ACCOUNT_ID", "").strip()
        self.access_key_id = os.environ.get("CLOUDFLARE_R2_ACCESS_KEY_ID", "").strip()
        self.secret_access_key = os.environ.get("CLOUDFLARE_R2_SECRET_ACCESS_KEY", "").strip()
        self.bucket_name = os.environ.get("CLOUDFLARE_R2_BUCKET_NAME", "sabro-networks-storage").strip()
        self.public_domain = os.environ.get("CLOUDFLARE_R2_PUBLIC_URL", "").strip().rstrip("/")
        self._s3_client = None

    def is_configured(self):
        """Returns True if all required Cloudflare R2 credentials are present."""
        return bool(self.account_id and self.access_key_id and self.secret_access_key and self.bucket_name)

    def _get_client(self):
        if not self.is_configured():
            return None
        if self._s3_client is None:
            import boto3
            from botocore.config import Config
            self._s3_client = boto3.client(
                "s3",
                endpoint_url=f"https://{self.account_id}.r2.cloudflarestorage.com",
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                region_name="auto",
                config=Config(signature_version="s3v4")
            )
        return self._s3_client

    def upload_file(self, file_data, key, content_type=None):
        """
        Uploads file bytes or stream to Cloudflare R2.
        Returns the public/accessible URL or key.
        """
        key = key.lstrip("/")
        client = self._get_client()
        if not client:
            return None

        if not content_type:
            content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"

        if isinstance(file_data, bytes):
            stream = io.BytesIO(file_data)
        elif hasattr(file_data, "read"):
            stream = file_data
        else:
            raise ValueError("file_data must be bytes or a file-like stream")

        client.upload_fileobj(
            stream,
            self.bucket_name,
            key,
            ExtraArgs={"ContentType": content_type}
        )
        return self.get_file_url(key)

    def get_file_url(self, key):
        """Returns the public CDN URL or signed retrieval endpoint for a file key."""
        key = key.lstrip("/")
        if self.public_domain:
            return f"{self.public_domain}/{key}"
        return f"https://{self.bucket_name}.r2.cloudflarestorage.com/{key}"

    def download_file(self, key):
        """Downloads file content as bytes from Cloudflare R2."""
        key = key.lstrip("/")
        client = self._get_client()
        if not client:
            return None
        buf = io.BytesIO()
        client.download_fileobj(self.bucket_name, key, buf)
        buf.seek(0)
        return buf.read()

    def delete_file(self, key):
        """Deletes an object from Cloudflare R2."""
        key = key.lstrip("/")
        client = self._get_client()
        if not client:
            return False
        client.delete_object(Bucket=self.bucket_name, Key=key)
        return True


# Global default instance
r2_storage = CloudflareR2Client()
