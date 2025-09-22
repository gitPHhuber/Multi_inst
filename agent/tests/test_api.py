from fastapi.testclient import TestClient

from multi_inst_agent.api.app import app


def test_start_stop_snapshot():
    client = TestClient(app)
    resp = client.post("/v1/start", json={"ports": ["SIM1"], "simulate": True})
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    snapshot = client.get("/v1/snapshot", params={"session_id": session_id})
    assert snapshot.status_code == 200
    data = snapshot.json()
    assert data["devices"]
    stop = client.post("/v1/stop", json={"session_id": session_id})
    assert stop.status_code == 200


def test_websocket_stream():
    client = TestClient(app)
    resp = client.post("/v1/start", json={"ports": ["SIM2"], "simulate": True})
    session_id = resp.json()["session_id"]
    with client.websocket_connect(f"/v1/stream?session_id={session_id}") as ws:
        message = ws.receive_json()
        assert message["type"] in {"snapshot", "ping"}
    client.post("/v1/stop", json={"session_id": session_id})
