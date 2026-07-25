import os

from services.file_service import validate_upload_file, save_uploaded_file, load_uploaded_file


def test_rejects_unsupported_binary_file_type():
    result = validate_upload_file("archive.zip", 10, "application/zip")
    assert result["ok"] is False
    assert "Unsupported file type" in result["error"]


def test_accepts_supported_image_file_within_limit():
    result = validate_upload_file("photo.png", 200_000, "image/png")
    assert result["ok"] is True
    assert result["category"] == "image"


def test_rejects_large_video_file():
    result = validate_upload_file("clip.mp4", 6 * 1024 * 1024, "video/mp4")
    assert result["ok"] is False
    assert "too large" in result["error"].lower()


def test_save_and_load_uploaded_file_round_trip(monkeypatch):
    class FakeBody:
        def __init__(self, data: bytes):
            self.data = data

        def read(self):
            return self.data

    class FakeClient:
        def __init__(self):
            self.objects = {}

        def put_object(self, **kwargs):
            self.objects[kwargs["Key"]] = {
                "Body": kwargs["Body"],
                "ContentType": kwargs["ContentType"],
                "Metadata": kwargs.get("Metadata", {}),
            }

        def get_object(self, **kwargs):
            obj = self.objects[kwargs["Key"]]
            return {
                "Body": FakeBody(obj["Body"]),
                "ContentType": obj["ContentType"],
                "Metadata": obj["Metadata"],
                "ContentLength": len(obj["Body"]),
            }

    fake_client = FakeClient()
    monkeypatch.setattr("services.file_service.get_r2_client", lambda: (fake_client, "codealive-files"))

    file_id = "abc123"
    payload = b"hello file preview"
    metadata = save_uploaded_file(
        file_id=file_id,
        filename="demo.txt",
        content_type="text/plain",
        content=payload,
    )

    assert metadata["file_id"] == file_id
    assert metadata["filename"] == "demo.txt"

    loaded = load_uploaded_file(file_id)
    assert loaded is not None
    assert loaded["content"] == payload
    assert loaded["content_type"] == "text/plain"
