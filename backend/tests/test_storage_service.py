import pytest

from services import storage
from services.auth import AuthenticatedUser


class FakePostgrest:
    def __init__(self):
        self.closed = False

    async def aclose(self):
        self.closed = True


class FakeBucketProxy:
    def __init__(self, bucket_name, files_store):
        self.bucket_name = bucket_name
        self.files_store = files_store
        self.uploads: list[tuple[str, bytes, dict]] = []
        self.signed_url_calls: list[tuple[str, int]] = []
        self.removed: list[list[str]] = []

    async def upload(self, path, file, file_options=None):
        self.uploads.append((path, file, file_options))
        self.files_store[path] = file

    async def create_signed_url(self, path, expires_in, options=None):
        self.signed_url_calls.append((path, expires_in))
        return {"signedURL": f"https://signed.example/{path}?expires={expires_in}"}

    async def list(self, path=None, options=None):
        prefix = f"{path}/" if path else ""
        return [
            {"name": stored_path[len(prefix) :]}
            for stored_path in self.files_store
            if stored_path.startswith(prefix)
        ]

    async def remove(self, paths):
        self.removed.append(paths)
        for path in paths:
            self.files_store.pop(path, None)
        return [{"name": p} for p in paths]


class FakeStorage:
    def __init__(self, files_store):
        self.files_store = files_store
        self.buckets: dict[str, FakeBucketProxy] = {}

    def from_(self, bucket_name):
        if bucket_name not in self.buckets:
            self.buckets[bucket_name] = FakeBucketProxy(bucket_name, self.files_store)
        return self.buckets[bucket_name]


class FakeClient:
    def __init__(self, files_store):
        self.postgrest = FakePostgrest()
        self.storage = FakeStorage(files_store)


def user(access_token="tok-a"):
    return AuthenticatedUser(id="user-1", email="a@example.com", access_token=access_token)


@pytest.fixture
def fake_storage(monkeypatch):
    files_store: dict[str, bytes] = {}
    clients: list[FakeClient] = []

    async def fake_client_for(access_token):
        client = FakeClient(files_store)
        clients.append(client)
        return client

    monkeypatch.setattr("services.storage.client_for", fake_client_for)

    class Handle:
        files = files_store
        created_clients = clients

    return Handle()


def test_audio_storage_path_is_owner_prefixed_and_flat_per_session():
    path = storage.audio_storage_path("owner-1", "session-1", "message-1", "fr")
    assert path == "owner-1/session-1/message-1.fr.mp3"


async def test_upload_audio_writes_to_the_message_audio_bucket(fake_storage):
    await storage.upload_audio(user(), "owner-1/session-1/message-1.fr.mp3", b"mp3-bytes")

    bucket = fake_storage.created_clients[0].storage.buckets[storage.AUDIO_BUCKET]
    assert bucket.uploads == [
        ("owner-1/session-1/message-1.fr.mp3", b"mp3-bytes", {"content-type": "audio/mpeg", "upsert": "true"})
    ]


async def test_upload_audio_closes_the_client(fake_storage):
    await storage.upload_audio(user(), "path.mp3", b"data")
    assert fake_storage.created_clients[0].postgrest.closed is True


async def test_get_signed_url_returns_the_signed_url(fake_storage):
    url = await storage.get_signed_url(user(), "owner-1/session-1/message-1.fr.mp3")
    assert url == "https://signed.example/owner-1/session-1/message-1.fr.mp3?expires=3600"


async def test_delete_session_audio_removes_every_object_under_the_session_prefix(fake_storage):
    fake_storage.files["owner-1/session-1/message-1.fr.mp3"] = b"a"
    fake_storage.files["owner-1/session-1/message-2.de.mp3"] = b"b"
    fake_storage.files["owner-1/session-2/message-3.fr.mp3"] = b"c"

    await storage.delete_session_audio(user(), "owner-1", "session-1")

    assert "owner-1/session-1/message-1.fr.mp3" not in fake_storage.files
    assert "owner-1/session-1/message-2.de.mp3" not in fake_storage.files
    assert "owner-1/session-2/message-3.fr.mp3" in fake_storage.files


async def test_delete_session_audio_with_nothing_to_delete_does_not_call_remove(fake_storage):
    await storage.delete_session_audio(user(), "owner-1", "session-empty")
    bucket = fake_storage.created_clients[0].storage.buckets[storage.AUDIO_BUCKET]
    assert bucket.removed == []
