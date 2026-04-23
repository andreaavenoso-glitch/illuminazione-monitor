"""Thin S3/MinIO upload helper used by the document fetcher task."""
from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import UUID

import boto3
from botocore.client import Config as BotoConfig


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT", "http://minio:9000"),
        aws_access_key_id=os.getenv("S3_ACCESS_KEY", "minio"),
        aws_secret_access_key=os.getenv("S3_SECRET_KEY", "minio123"),
        region_name=os.getenv("S3_REGION", "us-east-1"),
        config=BotoConfig(signature_version="s3v4"),
    )


def build_object_key(record_id: UUID, filename: str | None) -> str:
    today = datetime.now(tz=UTC).strftime("%Y/%m/%d")
    safe_name = (filename or "document").replace("/", "_").replace("\\", "_")
    return f"records/{record_id}/{today}/{safe_name}"


def upload_bytes(
    *,
    body: bytes,
    object_key: str,
    content_type: str | None = None,
) -> str:
    bucket = os.getenv("S3_BUCKET", "documents")
    public_endpoint = os.getenv("S3_PUBLIC_ENDPOINT", os.getenv("S3_ENDPOINT", "http://minio:9000"))
    extra: dict = {}
    if content_type:
        extra["ContentType"] = content_type
    client = get_s3_client()
    client.put_object(Bucket=bucket, Key=object_key, Body=body, **extra)
    return f"{public_endpoint.rstrip('/')}/{bucket}/{object_key}"
