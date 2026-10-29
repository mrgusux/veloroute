"""
Attachment Storage Manager for Multimodal LLM queries.
Supports saving/uploading files to Local directory or AWS S3 bucket.
"""
from __future__ import annotations
import os
import base64
import uuid
import mimetypes
import logging
from pathlib import Path
from typing import Optional, Union, Dict, Any

logger = logging.getLogger(__name__)


class AttachmentManager:
    """
    Manages multi-modal attachments (documents, audio, video, images).
    Saves/uploads to local storage or an AWS S3 bucket, then translates
    files into standard API payloads (base64 data URLs or S3 links).
    """

    def __init__(
        self,
        storage_type: Optional[str] = None,
        local_dir: Optional[str] = None,
        s3_bucket: Optional[str] = None,
        s3_prefix: Optional[str] = None,
        s3_region: Optional[str] = None,
    ):
        # Resolve storage type: argument > environment variable > "local"
        self.storage_type = (
            storage_type
            or os.environ.get("LLMCYCLE_ATTACHMENT_STORAGE", "local")
        ).lower()

        if self.storage_type not in ("local", "s3"):
            raise ValueError(f"Invalid attachment storage type: '{self.storage_type}'. Choose 'local' or 's3'.")

        # Resolve local storage configs
        self.local_dir = Path(
            local_dir
            or os.environ.get("LLMCYCLE_ATTACHMENT_LOCAL_DIR", "./attachments")
        ).resolve()

        # Resolve S3 configs
        self.s3_bucket = s3_bucket or os.environ.get("LLMCYCLE_ATTACHMENT_S3_BUCKET")
        self.s3_prefix = s3_prefix or os.environ.get("LLMCYCLE_ATTACHMENT_S3_PREFIX", "attachments/")
        if not self.s3_prefix.endswith("/"):
            self.s3_prefix += "/"
        self.s3_region = s3_region or os.environ.get("LLMCYCLE_ATTACHMENT_S3_REGION", "us-east-1")

        if self.storage_type == "local":
            self.local_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Initialized Local Attachment Storage at: {self.local_dir}")
        elif self.storage_type == "s3":
            if not self.s3_bucket:
                raise ValueError("LLMCYCLE_ATTACHMENT_S3_BUCKET must be provided for S3 attachment storage.")
            logger.info(f"Initialized S3 Attachment Storage using bucket: {self.s3_bucket}")

    def _get_mime_type(self, filename: str) -> str:
        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or "application/octet-stream"

    def _read_file_data(self, file_source: Union[str, bytes]) -> tuple[bytes, str]:
        """
        Extract raw bytes and original filename from a file path or raw bytes.
        """
        if isinstance(file_source, bytes):
            return file_source, f"raw-{uuid.uuid4().hex[:8]}.bin"

        path = Path(file_source)
        if not path.exists() or not path.is_file():
            # If path doesn't exist but has a suffix, we might check if it's bytes encoded as string
            raise FileNotFoundError(f"File not found: {file_source}")

        return path.read_bytes(), path.name

    def upload_attachment(
        self,
        file_source: Union[str, bytes, Dict[str, Any]],
        filename: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Uploads or saves the attachment.
        
        Args:
            file_source: Local file path (str), raw file data (bytes), or dict config.
            filename: Target file name (optional).
            media_type: Mime/media type of the attachment (optional).
            
        Returns:
            Dict containing:
                - url: Path or HTTP URL to refer to.
                - storage_type: "local" or "s3"
                - media_type: Resolved MIME type
                - base64_url: Base64 data URL (useful for local files)
                - storage_path: File system path or S3 key
        """
        # Resolve dictionary source if passed
        if isinstance(file_source, dict):
            media_type = media_type or file_source.get("media_type")
            filename = filename or file_source.get("filename")
            if "file" in file_source:
                file_source = file_source["file"]
            elif "content" in file_source:
                file_source = file_source["content"]
            else:
                raise ValueError("Dict attachment must contain either 'file' (path) or 'content' (bytes).")

        raw_bytes, orig_filename = self._read_file_data(file_source)
        target_filename = filename or orig_filename

        # Generate unique storage filename to avoid overrides
        ext = Path(target_filename).suffix
        unique_filename = f"{uuid.uuid4()}{ext}"
        resolved_mime = media_type or self._get_mime_type(target_filename)

        # Generate base64 Data URL
        encoded_data = base64.b64encode(raw_bytes).decode("utf-8")
        base64_url = f"data:{resolved_mime};base64,{encoded_data}"

        if self.storage_type == "local":
            dest_path = self.local_dir / unique_filename
            dest_path.write_bytes(raw_bytes)
            logger.debug(f"Saved local attachment to {dest_path}")

            return {
                "url": str(dest_path),
                "storage_type": "local",
                "media_type": resolved_mime,
                "base64_url": base64_url,
                "storage_path": str(dest_path),
            }

        else:  # s3 storage
            try:
                import boto3
                from botocore.exceptions import NoCredentialsError
            except ImportError:
                raise ImportError(
                    "AWS S3 attachment storage requires boto3. "
                    "Install it using 'pip install boto3' or 'uv add boto3'."
                )

            s3_key = f"{self.s3_prefix}{unique_filename}"
            s3_client = boto3.client("s3", region_name=self.s3_region)

            try:
                s3_client.put_object(
                    Bucket=self.s3_bucket,
                    Key=s3_key,
                    Body=raw_bytes,
                    ContentType=resolved_mime,
                )
                logger.debug(f"Uploaded attachment to s3://{self.s3_bucket}/{s3_key}")
            except NoCredentialsError:
                raise ValueError("AWS Credentials not found or invalid. Please check your AWS setup.")

            # Generate pre-signed URL valid for 1 hour (3600 seconds)
            presigned_url = s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.s3_bucket, "Key": s3_key},
                ExpiresIn=3600,
            )

            return {
                "url": presigned_url,
                "storage_type": "s3",
                "media_type": resolved_mime,
                "base64_url": base64_url,
                "storage_path": f"s3://{self.s3_bucket}/{s3_key}",
            }

    def format_message_content(
        self,
        prompt: Optional[str],
        attachments: list[Union[str, bytes, Dict[str, Any]]],
    ) -> list[Dict[str, Any]]:
        """
        Translates a prompt and a list of attachments into standard multimodal message contents.
        
        Returns:
            List of dictionaries representing content blocks.
        """
        content_parts = []

        # Add primary prompt text if present
        if prompt:
            content_parts.append({"type": "text", "text": prompt})

        # Process each attachment
        for att in attachments:
            info = self.upload_attachment(att)
            mime = info["media_type"]
            
            if mime.startswith("image/"):
                # Use standard OpenAI image_url structure
                # For local attachments, use the embedded base64_url
                # For S3, we can pass either the pre-signed URL or base64_url (base64 is safer across networks)
                url_to_use = info["url"] if info["storage_type"] == "s3" else info["base64_url"]
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": url_to_use}
                })
            elif mime.startswith("audio/"):
                # Standard OpenAI compatibility for audio delta
                # Extract base64 without prefix data URI headers for input_audio payload
                base64_data = info["base64_url"].split(",")[-1]
                audio_format = mime.split("/")[-1]
                if audio_format not in ("wav", "mp3", "ogg", "flac"):
                    audio_format = "wav"
                content_parts.append({
                    "type": "input_audio",
                    "input_audio": {
                        "data": base64_data,
                        "format": audio_format
                    }
                })
            else:
                # Treat as document / application PDF or text
                # Format using standard inline base64 or S3 URI depending on capabilities
                if mime == "application/pdf":
                    base64_data = info["base64_url"].split(",")[-1]
                    content_parts.append({
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": base64_data
                        }
                    })
                else:
                    # Generic file reference
                    content_parts.append({
                        "type": "text",
                        "text": f"[Attachment ({mime}): {info['storage_path']}]"
                    })

        return content_parts
