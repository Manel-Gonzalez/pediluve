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
        self._in_filters = {}
        self._order_column = None
        self._order_desc = False
        self._range = None

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def select(self, columns="*"):
        if self._op is None:
            self._op = "select"
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, column, value):
        self._filters[column] = value
        return self

    def in_(self, column, values):
        self._in_filters[column] = set(values)
        return self

    def order(self, column, desc=False):
        self._order_column = column
        self._order_desc = desc
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def _matching_rows(self, rows):
        return [
            row
            for row in rows
            if all(row.get(k) == v for k, v in self._filters.items())
            and all(row.get(k) in v for k, v in self._in_filters.items())
        ]

    async def execute(self):
        rows = self.store.setdefault(self.table_name, [])
        if self._op == "insert":
            # Mirrors a `created_at timestamptz default now()` column: tests
            # that care about ordering overwrite this afterwards, tests that
            # don't just need *some* value present so an `.order()` call
            # doesn't KeyError.
            row = {
                "created_at": f"{len(rows):020d}",
                **self._payload,
                "id": f"{self.table_name}-{len(rows) + 1}",
            }
            rows.append(row)
            return FakeResult([row])
        if self._op == "update":
            matched = self._matching_rows(rows)
            for row in matched:
                row.update(self._payload)
            return FakeResult(matched)
        if self._op == "delete":
            matched = self._matching_rows(rows)
            for row in matched:
                rows.remove(row)
            return FakeResult(matched)
        if self._op == "select":
            matched = self._matching_rows(rows)
            if self._order_column is not None:
                matched = sorted(
                    matched, key=lambda row: row[self._order_column], reverse=self._order_desc
                )
            if self._range is not None:
                start, end = self._range
                matched = matched[start : end + 1]
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


async def create_session_id(user_obj, **kwargs):
    # Most tests only need an id to hang further calls off of, not the full
    # row create_session() now returns - this keeps those call sites terse.
    kwargs.setdefault("title", "Test session")
    row = await supabase.create_session(user_obj, **kwargs)
    return row["id"]


async def test_create_session_inserts_a_row_with_the_owner_title_and_returns_it(fake_client):
    row = await supabase.create_session(user(id="user-1"), title="Standup")
    stored = fake_client.store["sessions"][0]
    assert row == stored
    assert stored["user_id"] == "user-1"
    assert stored["title"] == "Standup"


async def test_create_session_defaults_target_language_to_none(fake_client):
    await supabase.create_session(user(), title="Standup")
    assert fake_client.store["sessions"][0]["target_language"] is None


async def test_create_session_accepts_an_explicit_target_language(fake_client):
    await supabase.create_session(user(), title="Standup", target_language="es")
    assert fake_client.store["sessions"][0]["target_language"] == "es"


async def test_create_session_defaults_source_language_to_none(fake_client):
    await supabase.create_session(user(), title="Standup")
    assert fake_client.store["sessions"][0]["source_language"] is None


async def test_create_session_accepts_an_explicit_source_language(fake_client):
    await supabase.create_session(user(), title="Standup", source_language="es")
    assert fake_client.store["sessions"][0]["source_language"] == "es"


async def test_create_session_closes_the_client_after_use(fake_client):
    await supabase.create_session(user(access_token="tok-a"), title="Standup")
    assert fake_client.by_token["tok-a"].postgrest.closed is True


async def test_save_message_inserts_session_id_sequence_and_text(fake_client):
    session_id = await create_session_id(user())
    await supabase.save_message(user(), session_id, 0, "hello")

    saved = fake_client.store["messages"][0]
    assert saved["session_id"] == session_id
    assert saved["sequence"] == 0
    assert saved["original_text"] == "hello"


async def test_save_message_defaults_translated_text_and_target_language_to_none(fake_client):
    session_id = await create_session_id(user())
    await supabase.save_message(user(), session_id, 0, "hello")

    saved = fake_client.store["messages"][0]
    assert saved["translated_text"] is None
    assert saved["target_language"] is None


async def test_save_message_accepts_translated_text_and_target_language(fake_client):
    session_id = await create_session_id(user())
    await supabase.save_message(user(), session_id, 0, "hello", translated_text="hola", target_language="es")

    saved = fake_client.store["messages"][0]
    assert saved["translated_text"] == "hola"
    assert saved["target_language"] == "es"


async def test_save_message_returns_the_inserted_row_with_its_id(fake_client):
    session_id = await create_session_id(user())
    row = await supabase.save_message(user(), session_id, 0, "hello")
    assert row["id"] is not None
    assert row["original_text"] == "hello"


async def test_create_message_audio_inserts_and_returns_the_row(fake_client):
    session_id = await create_session_id(user())
    message = await supabase.save_message(user(), session_id, 0, "hello")

    row = await supabase.create_message_audio(user(), message["id"], "fr", "owner/session/msg.fr.mp3")

    assert row["message_id"] == message["id"]
    assert row["language"] == "fr"
    assert row["storage_path"] == "owner/session/msg.fr.mp3"


async def test_get_message_audio_returns_none_when_not_cached(fake_client):
    session_id = await create_session_id(user())
    message = await supabase.save_message(user(), session_id, 0, "hello")

    assert await supabase.get_message_audio(user(), message["id"], "fr") is None


async def test_get_message_audio_returns_the_matching_row(fake_client):
    session_id = await create_session_id(user())
    message = await supabase.save_message(user(), session_id, 0, "hello")
    await supabase.create_message_audio(user(), message["id"], "fr", "owner/session/msg.fr.mp3")
    await supabase.create_message_audio(user(), message["id"], "de", "owner/session/msg.de.mp3")

    row = await supabase.get_message_audio(user(), message["id"], "fr")
    assert row["storage_path"] == "owner/session/msg.fr.mp3"


async def test_update_session_target_language_updates_the_matching_session(fake_client):
    session_id = await create_session_id(user())
    await supabase.update_session_target_language(user(), session_id, "de")

    row = fake_client.store["sessions"][0]
    assert row["id"] == session_id
    assert row["target_language"] == "de"


async def test_update_session_source_language_updates_the_matching_session(fake_client):
    session_id = await create_session_id(user())
    await supabase.update_session_source_language(user(), session_id, "fr")

    row = fake_client.store["sessions"][0]
    assert row["id"] == session_id
    assert row["source_language"] == "fr"


async def test_end_session_sets_ended_at_on_the_matching_session(fake_client):
    session_id = await create_session_id(user())
    await supabase.end_session(user(), session_id)

    row = fake_client.store["sessions"][0]
    assert row["id"] == session_id
    assert row["ended_at"] is not None


async def test_each_call_uses_the_token_from_the_user_it_was_given(fake_client):
    session_id = await create_session_id(user(access_token="tok-a"))
    await supabase.save_message(user(access_token="tok-b"), session_id, 0, "hello")
    await supabase.update_session_target_language(user(access_token="tok-c"), session_id, "de")
    await supabase.end_session(user(access_token="tok-d"), session_id)

    assert fake_client.tokens == ["tok-a", "tok-b", "tok-c", "tok-d"]


# ── KAN-21: list/get/rename/delete ───────────────────────────────────────


async def test_list_sessions_orders_newest_first(fake_client):
    older = await supabase.create_session(user(), title="Older")
    fake_client.store["sessions"][0]["created_at"] = "2026-01-01T00:00:00Z"
    newer = await supabase.create_session(user(), title="Newer")
    fake_client.store["sessions"][1]["created_at"] = "2026-01-02T00:00:00Z"

    rows, has_more = await supabase.list_sessions(user(), limit=20, offset=0)

    assert [row["id"] for row in rows] == [newer["id"], older["id"]]
    assert has_more is False


async def test_list_sessions_honors_limit_and_computes_has_more(fake_client):
    for i in range(3):
        await supabase.create_session(user(), title=f"Session {i}")
        fake_client.store["sessions"][i]["created_at"] = f"2026-01-0{i + 1}T00:00:00Z"

    rows, has_more = await supabase.list_sessions(user(), limit=2, offset=0)
    assert len(rows) == 2
    assert has_more is True

    rows, has_more = await supabase.list_sessions(user(), limit=2, offset=2)
    assert len(rows) == 1
    assert has_more is False


async def test_list_sessions_includes_message_count(fake_client):
    session = await supabase.create_session(user(), title="Standup")
    await supabase.save_message(user(), session["id"], 0, "hello")
    await supabase.save_message(user(), session["id"], 1, "world")
    other = await supabase.create_session(user(), title="Other")
    await supabase.save_message(user(), other["id"], 0, "solo")

    rows, _ = await supabase.list_sessions(user(), limit=20, offset=0)

    counts = {row["id"]: row["message_count"] for row in rows}
    assert counts[session["id"]] == 2
    assert counts[other["id"]] == 1


async def test_list_sessions_with_no_sessions_returns_an_empty_list(fake_client):
    rows, has_more = await supabase.list_sessions(user(), limit=20, offset=0)
    assert rows == []
    assert has_more is False


async def test_get_session_with_messages_returns_messages_sorted_by_sequence(fake_client):
    session = await supabase.create_session(user(), title="Standup")
    await supabase.save_message(user(), session["id"], 1, "second")
    await supabase.save_message(user(), session["id"], 0, "first")

    row = await supabase.get_session_with_messages(user(), session["id"])

    assert row["id"] == session["id"]
    assert [m["original_text"] for m in row["messages"]] == ["first", "second"]


async def test_get_session_with_messages_returns_none_for_an_unknown_id(fake_client):
    assert await supabase.get_session_with_messages(user(), "does-not-exist") is None


async def test_rename_session_updates_the_title_and_returns_the_row(fake_client):
    session = await supabase.create_session(user(), title="Old title")
    row = await supabase.rename_session(user(), session["id"], "New title")
    assert row["title"] == "New title"
    assert fake_client.store["sessions"][0]["title"] == "New title"


async def test_rename_session_returns_none_for_an_unknown_id(fake_client):
    assert await supabase.rename_session(user(), "does-not-exist", "New title") is None


async def test_delete_session_removes_the_row_and_returns_true(fake_client):
    session = await supabase.create_session(user(), title="Standup")
    result = await supabase.delete_session(user(), session["id"])
    assert result is True
    assert fake_client.store["sessions"] == []


async def test_delete_session_returns_false_for_an_unknown_id(fake_client):
    assert await supabase.delete_session(user(), "does-not-exist") is False
