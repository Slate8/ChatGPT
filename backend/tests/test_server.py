import http.client
import json
import threading
import time

import pytest

from logsanitizer.project import Workspace
from logsanitizer.server import make_server

TOKEN = "test-token"


@pytest.fixture
def server(tmp_path):
    srv, _app = make_server(Workspace(tmp_path / "ws"), port=0, token=TOKEN)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()


def call(server, method, path, body=None, token=TOKEN, host=None):
    port = server.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Host": host or f"127.0.0.1:{port}"}
    if token:
        headers["X-Session-Token"] = token
    payload = None
    if body is not None:
        payload = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=payload, headers=headers)
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response.status, json.loads(data) if data else None


def test_binds_to_loopback_only(server):
    assert server.server_address[0] == "127.0.0.1"


def test_api_requires_token(server):
    assert call(server, "GET", "/api/health", token=None)[0] == 401
    assert call(server, "GET", "/api/health", token="wrong")[0] == 401
    status, body = call(server, "GET", "/api/health")
    assert status == 200 and body["status"] == "ok"


def test_foreign_host_header_is_rejected(server):
    assert call(server, "GET", "/api/health", host="evil.example:80")[0] == 421


def test_full_workflow(server, tmp_path):
    src = tmp_path / "in" / "app.log"
    src.parent.mkdir()
    src.write_text("user CORP\\jdoe from 10.0.0.1 on dc01\n", encoding="utf-8")

    status, project = call(server, "POST", "/api/projects", {"name": "Kunde A"})
    assert status == 200
    slug = project["slug"]
    assert call(server, "PUT", f"/api/projects/{slug}/names", {"Server": ["dc01"]})[0] == 200
    status, result = call(server, "POST", f"/api/projects/{slug}/sources",
                          {"paths": [str(src.parent)], "recursive": True})
    assert status == 200 and result["added"] == 1

    status, preview = call(server, "POST", f"/api/projects/{slug}/preview",
                           {"text": "dc01 at 10.0.0.9"})
    assert preview["output"] == "[Server_neu] at [IP_neu]"

    status, started = call(server, "POST", f"/api/projects/{slug}/runs")
    assert status == 200
    run_id = started["run_id"]
    for _ in range(100):
        status, report = call(server, "GET", f"/api/projects/{slug}/runs/{run_id}")
        if status == 200 and report["status"] != "running":
            break
        time.sleep(0.05)
    assert report["status"] == "ready", report

    status, mapping = call(server, "GET", f"/api/projects/{slug}/mapping")
    assert {row["placeholder"] for row in mapping} >= {"[Server_1]", "[IP_1]", "[User_1]"}
    status, preview = call(server, "POST", f"/api/projects/{slug}/preview",
                           {"text": "dc01 at 10.0.0.1"})
    assert preview["output"] == "[Server_1] at [IP_1]"


def test_rule_validation_errors_are_reported(server):
    _, project = call(server, "POST", "/api/projects", {"name": "Regeln"})
    slug = project["slug"]
    _, rules = call(server, "GET", f"/api/projects/{slug}/rules")
    rules["rules"].append({"id": "x", "name": "x", "pattern": "(", "category": "X"})
    status, body = call(server, "PUT", f"/api/projects/{slug}/rules", rules)
    assert status == 400 and "ungültig" in body["error"]
    rules["rules"][-1] = {"id": "slow", "name": "x", "pattern": "(a+)+$", "category": "X"}
    status, body = call(server, "PUT", f"/api/projects/{slug}/rules", rules)
    assert status == 400 and "zu langsam" in body["error"]


def test_browse_lists_directories(server, tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "f.log").write_text("x", encoding="utf-8")
    status, listing = call(server, "GET", f"/api/fs?path={tmp_path}")
    assert status == 200
    names = [e["name"] for e in listing["entries"]]
    assert names.index("sub") < names.index("f.log")


def test_unknown_project_is_404(server):
    assert call(server, "GET", "/api/projects/nope")[0] == 404
    assert call(server, "GET", "/api/projects/..%2F..")[0] in (400, 404)
