import pytest

from services import supabase
from services.auth import AuthenticatedUser


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, table_name, store):
        self.table_name = table_name
        self.store = store
        self._op = None
        self._payload = None
        self._filters = {}

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, column, value):
        self._filters[column] = value
        return self

    async def execute(self):
        rows = self.store.setdefault(self.table_name, [])
        if self._op == "insert":
            row = {**self._payload, "id": f"{self.table_name}-{len(rows) + 1}"}
            rows.append(row)
            return FakeResult([row])
        if self._op == "update":
            matched = [
                row for row in rows if all(row.get(k) == v for k, v in self._filters.items())
            ]
            for row in matched:
                row.update(self._payload)
            return FakeResult(matched)
        raise AssertionError(f"unexpected operation: {self._op}")


class FakePostgrest:
    def __init__(self):
        self.closed = False

    async def aclose(self):
        self.closed = True


class FakeAsyncClientForToken:
    def __init__(self, store, access_token):
        self.store = store
        self.access_token = access_token
        self.postgrest = FakePostgrest()

    def table(self, name):
        return FakeQuery(name, self.store)


def user(access_token="tok-a", id="user-1", email="a@example.com"):
    return AuthenticatedUser(id=id, email=email, access_token=access_token)


@pytest.fixture
def fake_client(monkeypatch):
    # One shared store simulates the real remote DB: every client_for() call
    # in production talks to the same Postgres, even though it's a fresh
    # client object each time - this fixture mirrors that, while still
    # recording which access_token each call used and letting tests check
    # each client was closed after use.
    shared_store: dict[str, list[dict]] = {}
    tokens_used: list[str] = []
    clients_by_token: dict[str, FakeAsyncClientForToken] = {}

    async def fake_client_for(access_token):
        tokens_used.append(access_token)
        client = FakeAsyncClientForToken(shared_store, access_token)
        clients_by_token[access_token] = client
        return client

    monkeypatch.setattr(supabase, "client_for", fake_client_for)

    class Handle:
        store = shared_store
        tokens = tokens_used
        by_token = clients_by_token

    return Handle()


async def test_client_for_authenticates_the_postgrest_client_with_the_token(monkeypatch):
    class FakeRealPostgrest:
        def __init__(self):
            self.token = None

        def auth(self, token):
            self.token = token

    class FakeRealClient:
        def __init__(self):
            self.postgrest = FakeRealPostgrest()

    created = FakeRealClient()

    async def fake_create_async_client(url, key):
        return created

    monkeypatch.setattr(supabase, "create_async_client", fake_create_async_client)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "anon-key")

    client = await supabase.client_for("user-token")

    assert client is created
    assert created.postgrest.token == "user-token"


async def test_client_for_returns_a_distinct_client_per_call(monkeypatch):
    class FakeRealPostgrest:
        def auth(self, token):
            pass

    async def fake_create_async_client(url, key):
        class FakeRealClient:
            def __init__(self):
                self.postgrest = FakeRealPostgrest()

        return FakeRealClient()

    monkeypatch.setattr(supabase, "create_async_client", fake_create_async_client)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "anon-key")

    first = await supabase.client_for("token-a")
    second = await supabase.client_for("token-b")

    assert first is not second


async def test_create_session_inserts_a_row_with_the_owner_and_returns_its_id(fake_client):
    session_id = await supabase.create_session(user(id="user-1"))
    row = fake_client.store["sessions"][0]
    assert session_id == row["id"]
    assert row["user_id"] == "user-1"


async def test_create_session_uses_the_placeholder_target_language_by_default(fake_client):
    await supabase.create_session(user())
    assert fake_client.store["sessions"][0]["target_language"] == supabase.DEFAULT_TARGET_LANGUAGE


async def test_create_session_accepts_an_explicit_target_language(fake_client):
    await supabase.create_session(user(), target_language="es")
    assert fake_client.store["sessions"][0]["target_language"] == "es"


async def test_create_session_defaults_source_language_to_none(fake_client):
    await supabase.create_session(user())
    assert fake_client.store["sessions"][0]["source_language"] is None


async def test_create_session_accepts_an_explicit_source_language(fake_client):
    await supabase.create_session(user(), source_language="es")
    assert fake_client.store["sessions"][0]["source_language"] == "es"


async def test_create_session_closes_the_client_after_use(fake_client):
    await supabase.create_session(user(access_token="tok-a"))
    assert fake_client.by_token["tok-a"].postgrest.closed is True


async def test_save_message_inserts_session_id_sequence_and_text(fake_client):
    session_id = await supabase.create_session(user())
    await supabase.save_message(user(), session_id, 0, "hello")

    saved = fake_client.store["messages"][0]
    assert saved["session_id"] == session_id
    assert saved["sequence"] == 0
    assert saved["original_text"] == "hello"


async def test_save_message_defaults_translated_text_and_target_language_to_none(fake_client):
    session_id = await supabase.create_session(user())
    await supabase.save_message(user(), session_id, 0, "hello")

    saved = fake_client.store["messages"][0]
    assert saved["translated_text"] is None
    assert saved["target_language"] is None


async def test_save_message_accepts_translated_text_and_target_language(fake_client):
    session_id = await supabase.create_session(user())
    await supabase.save_message(user(), session_id, 0, "hello", translated_text="hola", target_language="es")

    saved = fake_client.store["messages"][0]
    assert saved["translated_text"] == "hola"
    assert saved["target_language"] == "es"


async def test_update_session_target_language_updates_the_matching_session(fake_client):
    session_id = await supabase.create_session(user())
    await supabase.update_session_target_language(user(), session_id, "de")

    row = fake_client.store["sessions"][0]
    assert row["id"] == session_id
    assert row["target_language"] == "de"


async def test_end_session_sets_ended_at_on_the_matching_session(fake_client):
    session_id = await supabase.create_session(user())
    await supabase.end_session(user(), session_id)

    row = fake_client.store["sessions"][0]
    assert row["id"] == session_id
    assert row["ended_at"] is not None


async def test_each_call_uses_the_token_from_the_user_it_was_given(fake_client):
    session_id = await supabase.create_session(user(access_token="tok-a"))
    await supabase.save_message(user(access_token="tok-b"), session_id, 0, "hello")
    await supabase.update_session_target_language(user(access_token="tok-c"), session_id, "de")
    await supabase.end_session(user(access_token="tok-d"), session_id)

    assert fake_client.tokens == ["tok-a", "tok-b", "tok-c", "tok-d"]
