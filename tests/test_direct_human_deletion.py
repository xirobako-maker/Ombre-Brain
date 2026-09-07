import json
from types import SimpleNamespace

import pytest
import yaml
from starlette.responses import JSONResponse

import utils
from deletion_requests import DeletionRequestStore
from tests.test_human_deletion_web_paths import _exercise_routes, Request
from tests.test_deletion_requests import BucketManager
from web import config_api


@pytest.mark.asyncio
async def test_direct_mode_covers_all_authenticated_human_paths(monkeypatch, tmp_path):
    records = {bid: {"id": bid, "metadata": {}} for bid in ("single", "archive", "batch", "review")}
    records["letter"] = {"id": "letter", "metadata": {"type": "letter"}}
    manager, store, bmcp, lmcp, imcp = await _exercise_routes(monkeypatch, tmp_path, records)
    store.config["human_deletion_requires_approval"] = False
    calls = [
        (bmcp, "DELETE", "/api/bucket/{bucket_id}", Request({}, path_params={"bucket_id": "single"}, confirm=True)),
        (bmcp, "POST", "/api/bucket/{bucket_id}/archive", Request({}, path_params={"bucket_id": "archive"})),
        (bmcp, "POST", "/api/buckets/batch", Request({"ids": ["batch", "batch"], "action": "archive"})),
        (lmcp, "DELETE", "/api/letter/{letter_id}", Request({}, path_params={"letter_id": "letter"}, confirm=True)),
        (imcp, "POST", "/api/import/review", Request({"decisions": [{"bucket_id": "review", "action": "delete"}]})),
    ]
    for mcp, method, path, request in calls:
        response = await mcp.routes[(method, path)](request)
        assert response.status_code == 200
    assert manager.deleted == ["single", "archive", "batch", "letter", "review"]
    assert store.pending_with_buckets() == []
    assert not store.path.exists()


@pytest.mark.asyncio
async def test_switch_does_not_execute_old_requests_or_allow_stale_ai_approval(tmp_path):
    manager = BucketManager({"id": "memory", "metadata": {}})
    config = {}
    store = DeletionRequestStore(str(tmp_path), manager, config=config)
    submitted = await store.submit("memory", "inaccurate")
    request_id = submitted["request"]["request_id"]
    config["human_deletion_requires_approval"] = False
    assert await store.render_pending_batch() == ""
    assert not (await store.decide(request_id, "approve"))["ok"]
    assert manager.deleted == []
    assert store.status("memory")["status"] == "pending"
    assert (await store.withdraw("memory"))["withdrawn"]
    assert manager.deleted == []
    config["human_deletion_requires_approval"] = True
    assert (await store.submit("memory", "incorrect"))["pending"]


@pytest.mark.asyncio
@pytest.mark.parametrize("batch", [False, True])
async def test_explicit_direct_delete_supersedes_only_that_request(tmp_path, batch):
    manager = BucketManager({"id": "memory", "metadata": {}})
    store = DeletionRequestStore(str(tmp_path), manager)
    await store.submit("memory", "inaccurate")
    store.config["human_deletion_requires_approval"] = False
    result = await store.submit_batch(["memory"], "") if batch else await store.submit("memory", "")
    assert result["ok"]
    assert manager.deleted == ["memory"]
    assert store.status("memory")["status"] == "superseded"


@pytest.mark.asyncio
async def test_direct_failure_preserves_pending_request(tmp_path):
    manager = BucketManager({"id": "memory", "metadata": {}})
    async def fail_delete(_bid):
        return False
    manager.delete = fail_delete
    store = DeletionRequestStore(str(tmp_path), manager)
    await store.submit("memory", "inaccurate")
    store.config["human_deletion_requires_approval"] = False
    assert not (await store.submit("memory", ""))["ok"]
    assert store.status("memory")["status"] == "pending"


class FakeMCP:
    def __init__(self):
        self.routes = {}

    def custom_route(self, path, methods):
        def register(fn):
            for method in methods:
                self.routes[(method, path)] = fn
            return fn
        return register


class JsonRequest:
    def __init__(self, body):
        self.body = body
        self.headers = {}

    async def json(self):
        return self.body


@pytest.fixture
def config_routes(monkeypatch, tmp_path):
    path = tmp_path / "config.yaml"
    original = {"human_deletion_requires_approval": True, "dehydration": {"model": "keep-model"}}
    path.write_text(yaml.safe_dump(original), encoding="utf-8")
    runtime = dict(original)
    monkeypatch.setattr(config_api.sh, "config", runtime)
    monkeypatch.setattr(config_api.sh, "_require_auth", lambda _r: None)
    monkeypatch.setattr(config_api.sh, "in_docker", lambda: False)
    monkeypatch.setattr(config_api.sh, "dehydrator", SimpleNamespace())
    monkeypatch.setattr(config_api.sh, "embedding_engine", None)
    monkeypatch.setattr(utils, "config_file_path", lambda: str(path))
    monkeypatch.setenv("OMBRE_BIND_HOST", "127.0.0.1")
    mcp = FakeMCP()
    config_api.register(mcp)
    return mcp.routes, runtime, path


@pytest.mark.asyncio
async def test_setting_is_partial_durable_hot_update(config_routes):
    routes, runtime, path = config_routes
    store = DeletionRequestStore(str(path.parent), None, config=runtime)
    response = await routes[("POST", "/api/config")](JsonRequest({"human_deletion_requires_approval": False, "persist": True}))
    assert response.status_code == 200
    assert not store.requires_approval
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert saved == {"human_deletion_requires_approval": False, "dehydration": {"model": "keep-model"}}
    assert DeletionRequestStore(str(path.parent), None, config=saved).requires_approval is False
    response = await routes[("GET", "/api/config")](JsonRequest({}))
    assert json.loads(response.body)["human_deletion_requires_approval"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, "false", 0, [], {}])
async def test_setting_rejects_non_boolean(config_routes, value):
    routes, runtime, path = config_routes
    before = path.read_bytes()
    response = await routes[("POST", "/api/config")](JsonRequest({"human_deletion_requires_approval": value, "persist": True}))
    assert response.status_code == 400
    assert runtime["human_deletion_requires_approval"] is True
    assert path.read_bytes() == before


@pytest.mark.asyncio
async def test_setting_persist_failure_rolls_back(config_routes, monkeypatch):
    routes, runtime, _ = config_routes
    def fail(_mutate):
        raise OSError("test failure")
    monkeypatch.setattr(config_api, "atomic_update_config_yaml", fail)
    response = await routes[("POST", "/api/config")](JsonRequest({"human_deletion_requires_approval": False, "persist": True}))
    assert response.status_code == 500
    assert runtime["human_deletion_requires_approval"] is True


@pytest.mark.asyncio
async def test_unauthenticated_setting_and_delete_cannot_mutate(config_routes, monkeypatch, tmp_path):
    routes, runtime, path = config_routes
    manager, store, bmcp, _, _ = await _exercise_routes(monkeypatch, tmp_path, {"memory": {"id": "memory", "metadata": {}}})
    store.config["human_deletion_requires_approval"] = False
    monkeypatch.setattr(config_api.sh, "_require_auth", lambda _r: JSONResponse({"error": "unauthorized"}, status_code=401))
    config_response = await routes[("POST", "/api/config")](JsonRequest({"human_deletion_requires_approval": False}))
    delete_response = await bmcp.routes[("DELETE", "/api/bucket/{bucket_id}")](Request({}, path_params={"bucket_id": "memory"}, confirm=True))
    assert config_response.status_code == delete_response.status_code == 401
    assert runtime["human_deletion_requires_approval"] is True
    assert manager.deleted == []
