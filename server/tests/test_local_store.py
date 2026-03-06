# Tests for the local SQLite knowledge store.

import pytest
from craic_mcp.knowledge_unit import Context, Insight, create_knowledge_unit
from craic_mcp.local_store import LocalStore
from craic_mcp.scoring import apply_confirmation


def _make_insight(**kwargs) -> Insight:
    defaults = dict(
        summary="Use connection pooling",
        detail="Database connections are expensive to create.",
        action="Configure a connection pool with a max size of 10.",
    )
    defaults.update(kwargs)
    return Insight(**defaults)


def _make_unit(domain=None, **kwargs):
    return create_knowledge_unit(
        domain=domain or ["databases", "performance"],
        insight=_make_insight(),
        **kwargs,
    )


@pytest.fixture
def store(tmp_path):
    return LocalStore(db_path=tmp_path / "test.db")


class TestInsertAndGet:
    def test_inserted_unit_is_retrievable(self, store):
        unit = _make_unit()
        store.insert(unit)
        result = store.get(unit.id)
        assert result == unit

    def test_get_unknown_id_returns_none(self, store):
        assert store.get("ku_doesnotexist") is None

    def test_duplicate_insert_does_not_raise(self, store):
        unit = _make_unit()
        store.insert(unit)
        store.insert(unit)  # should silently ignore

    def test_duplicate_insert_does_not_overwrite(self, store):
        unit = _make_unit()
        store.insert(unit)
        confirmed = apply_confirmation(unit)
        # Insert same ID with different data — should be ignored
        store.insert(confirmed)
        retrieved = store.get(unit.id)
        assert retrieved.evidence.confidence == unit.evidence.confidence


class TestUpdate:
    def test_update_persists_new_confidence(self, store):
        unit = _make_unit()
        store.insert(unit)
        confirmed = apply_confirmation(unit)
        store.update(confirmed)
        retrieved = store.get(unit.id)
        assert retrieved.evidence.confidence == pytest.approx(confirmed.evidence.confidence)

    def test_update_persists_confirmations_count(self, store):
        unit = _make_unit()
        store.insert(unit)
        confirmed = apply_confirmation(unit)
        store.update(confirmed)
        retrieved = store.get(unit.id)
        assert retrieved.evidence.confirmations == confirmed.evidence.confirmations


class TestQuery:
    def test_empty_store_returns_empty_list(self, store):
        assert store.query(["databases"]) == []

    def test_returns_matching_unit(self, store):
        unit = _make_unit(domain=["databases"])
        store.insert(unit)
        results = store.query(["databases"])
        assert len(results) == 1
        assert results[0].id == unit.id

    def test_respects_limit(self, store):
        for _ in range(5):
            store.insert(_make_unit(domain=["databases"]))
        results = store.query(["databases"], limit=3)
        assert len(results) == 3

    def test_ranked_by_relevance_times_confidence(self, store):
        low = _make_unit(domain=["networking"])          # no overlap with query
        high = _make_unit(domain=["databases", "performance"])  # full overlap
        store.insert(low)
        store.insert(high)
        results = store.query(["databases", "performance"])
        assert results[0].id == high.id

    def test_higher_confidence_ranks_higher_for_equal_relevance(self, store):
        unit_a = _make_unit(domain=["databases"])
        unit_b = _make_unit(domain=["databases"])
        # Boost unit_b confidence
        unit_b = apply_confirmation(unit_b)
        store.insert(unit_a)
        store.insert(unit_b)
        results = store.query(["databases"])
        assert results[0].id == unit_b.id

    def test_language_filter_improves_rank(self, store):
        with_lang = create_knowledge_unit(
            domain=["api"],
            insight=_make_insight(),
            context=Context(languages=["python"]),
        )
        without_lang = _make_unit(domain=["api"])
        store.insert(with_lang)
        store.insert(without_lang)
        results = store.query(["api"], language="python")
        assert results[0].id == with_lang.id

    def test_framework_filter_improves_rank(self, store):
        with_fw = create_knowledge_unit(
            domain=["web"],
            insight=_make_insight(),
            context=Context(frameworks=["django"]),
        )
        without_fw = _make_unit(domain=["web"])
        store.insert(with_fw)
        store.insert(without_fw)
        results = store.query(["web"], framework="django")
        assert results[0].id == with_fw.id


class TestInitDb:
    def test_init_db_is_idempotent(self, store):
        store._init_db()
        store._init_db()
        # If this doesn't raise, the CREATE TABLE IF NOT EXISTS is idempotent.

    def test_db_directory_auto_created(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c"
        store = LocalStore(db_path=nested / "test.db")
        unit = _make_unit()
        store.insert(unit)
        assert store.get(unit.id) is not None
