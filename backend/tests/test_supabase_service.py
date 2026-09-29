import pytest

from services import supabase


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


class FakeAsyncClient:
    def __init__(self):
        self.store: dict[str, list[dict]] = {}

    def table(self, name):
        return FakeQuery(name, self.store)


@pytest.fixture
def fake_client(monkeypatch):
    client = FakeAsyncClient()

    async def fake_get_client():
        return client

    monkeypatch.setattr(supabase, "_get_client", fake_get_client)
    return client


async def test_create_session_inserts_a_row_and_returns_its_id(fake_client):
    session_id = await supabase.create_session()
    assert session_id == fake_client.store["sessions"][0]["id"]


async def test_create_session_uses_the_placeholder_target_language_by_default(fake_client):
    await supabase.create_session()
    assert fake_client.store["sessions"][0]["target_language"] == supabase.DEFAULT_TARGET_LANGUAGE


async def test_create_session_accepts_an_explicit_target_language(fake_client):
    await supabase.create_session(target_language="es")
    assert fake_client.store["sessions"][0]["target_language"] == "es"


async def test_create_session_defaults_source_language_to_none(fake_client):
    await supabase.create_session()
    assert fake_client.store["sessions"][0]["source_language"] is None


async def test_create_session_accepts_an_explicit_source_language(fake_client):
    await supabase.create_session(source_language="es")
    assert fake_client.store["sessions"][0]["source_language"] == "es"


async def test_save_message_inserts_session_id_sequence_and_text(fake_client):
    session_id = await supabase.create_session()
    await supabase.save_message(session_id, 0, "hello")

    saved = fake_client.store["messages"][0]
    assert saved["session_id"] == session_id
    assert saved["sequence"] == 0
    assert saved["original_text"] == "hello"


async def test_save_message_defaults_translated_text_and_target_language_to_none(fake_client):
    session_id = await supabase.create_session()
    await supabase.save_message(session_id, 0, "hello")

    saved = fake_client.store["messages"][0]
    assert saved["translated_text"] is None
    assert saved["target_language"] is None


async def test_save_message_accepts_translated_text_and_target_language(fake_client):
    session_id = await supabase.create_session()
    await supabase.save_message(session_id, 0, "hello", translated_text="hola", target_language="es")

    saved = fake_client.store["messages"][0]
    assert saved["translated_text"] == "hola"
    assert saved["target_language"] == "es"


async def test_update_session_target_language_updates_the_matching_session(fake_client):
    session_id = await supabase.create_session()
    await supabase.update_session_target_language(session_id, "de")

    row = fake_client.store["sessions"][0]
    assert row["id"] == session_id
    assert row["target_language"] == "de"


async def test_end_session_sets_ended_at_on_the_matching_session(fake_client):
    session_id = await supabase.create_session()
    await supabase.end_session(session_id)

    row = fake_client.store["sessions"][0]
    assert row["id"] == session_id
    assert row["ended_at"] is not None
