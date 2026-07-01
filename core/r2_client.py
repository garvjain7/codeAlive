import os
from typing import Tuple

import boto3


def _require_env(name: str) -> str:
    value = os.getenv(name, "")
    if not value or not value.strip():
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value.strip()


def get_r2_client() -> Tuple[object, str]:
    endpoint_url = _require_env("R2_ENDPOINT_URL")
    access_key_id = _require_env("R2_ACCESS_KEY_ID")
    secret_access_key = _require_env("R2_SECRET_ACCESS_KEY")
    bucket_name = _require_env("R2_BUCKET_NAME")
    region_name = os.getenv("R2_REGION", "auto")

    client = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name=region_name,
    )
    return client, bucket_name
