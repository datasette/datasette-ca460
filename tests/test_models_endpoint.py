"""Tests for the /api/models endpoint shape and purpose filtering."""

import pytest
import pytest_asyncio
from datasette.app import Datasette


@pytest_asyncio.fixture
async def ds():
    datasette = Datasette(
        memory=True,
        config={"permissions": {"datasette-ca460-access": {"id": "*"}}},
    )
    await datasette.invoke_startup()
    return datasette


@pytest.fixture
def auth_cookies(ds):
    return {"ds_actor": ds.sign({"a": {"id": "root"}}, "actor")}


@pytest.mark.asyncio
async def test_models_endpoint_returns_classify_and_parse_lists(ds, auth_cookies):
    response = await ds.client.get("/_memory/-/ca460/api/models", cookies=auth_cookies)
    assert response.status_code == 200
    body = response.json()
    assert "classify" in body
    assert "parse" in body
    assert isinstance(body["classify"], list)
    assert isinstance(body["parse"], list)


@pytest.mark.asyncio
async def test_models_endpoint_filters_by_purpose(ds, auth_cookies, monkeypatch):
    """Verify each purpose gets its own filtered call to ds_llm.models()."""
    from datasette_ca460 import routes

    calls = []

    class FakeModel:
        def __init__(self, model_id):
            self.model_id = model_id

    class FakeLLM:
        def __init__(self, datasette):
            pass

        async def models(self, purpose=None, actor=None):
            calls.append({"purpose": purpose, "actor_id": actor.get("id") if actor else None})
            if purpose == "ca460-classify":
                return [FakeModel("fast-model")]
            if purpose == "ca460-parse":
                return [FakeModel("smart-model")]
            return []

    monkeypatch.setattr(routes, "LLM", FakeLLM)

    response = await ds.client.get("/_memory/-/ca460/api/models", cookies=auth_cookies)
    assert response.status_code == 200
    body = response.json()
    assert body["classify"] == ["fast-model"]
    assert body["parse"] == ["smart-model"]

    # Two calls, one per purpose, each with the actor
    assert len(calls) == 2
    purposes_called = {c["purpose"] for c in calls}
    assert purposes_called == {"ca460-classify", "ca460-parse"}
    assert all(c["actor_id"] == "root" for c in calls)
