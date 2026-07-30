from __future__ import annotations

import os
from uuid import uuid4

import pytest

from rath.artifacts import ArtifactNotFound, S3ArtifactStore

pytestmark = pytest.mark.skipif(
    not os.getenv("OPENRATH_TEST_S3_ENDPOINT"),
    reason="OPENRATH_TEST_S3_ENDPOINT is not configured",
)


def test_s3_artifact_real_lifecycle() -> None:
    import boto3

    endpoint = os.environ["OPENRATH_TEST_S3_ENDPOINT"]
    bucket = f"openrath-{uuid4().hex}"
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name="us-east-1",
        aws_access_key_id=os.environ["OPENRATH_TEST_S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["OPENRATH_TEST_S3_SECRET_KEY"],
    )
    client.create_bucket(Bucket=bucket)
    try:
        store = S3ArtifactStore(bucket, client=client)
        artifact = store.put(
            "tenant-a",
            b"object-store-result",
            media_type="text/plain",
            metadata={"source": "integration"},
        )

        assert store.stat("tenant-a", artifact.digest) == artifact
        assert store.get("tenant-a", artifact.digest) == b"object-store-result"
        with pytest.raises(ArtifactNotFound):
            store.get("tenant-b", artifact.digest)
        assert store.delete("tenant-a", artifact.digest)
        assert not store.delete("tenant-a", artifact.digest)
    finally:
        objects = client.list_objects_v2(Bucket=bucket).get("Contents", [])
        if objects:
            client.delete_objects(
                Bucket=bucket,
                Delete={"Objects": [{"Key": item["Key"]} for item in objects]},
            )
        client.delete_bucket(Bucket=bucket)
