import pytest
from fastapi.testclient import TestClient

from nttl.server.app import create_app
from tests.server.conftest import wait_for


@pytest.fixture
def client(state):
    with TestClient(create_app(state)) as client:
        yield client


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "version" in response.json()


def test_state_snapshot(client):
    body = client.get("/api/state").json()
    assert body["camera"]["connected"] is True
    assert "session" in body and "config" in body


def test_camera_endpoint_lists_controls(client):
    body = client.get("/api/camera").json()
    assert "exposure" in body["controls"]
    assert body["info"]["is_color"] is True


def test_backends_are_listed(client):
    assert "simulated" in client.get("/api/camera/backends").json()["backends"]


def test_set_control(client):
    response = client.post("/api/camera/control", json={"name": "gain", "value": 240})
    assert response.status_code == 200
    assert response.json()["value"] == pytest.approx(240, abs=1)


def test_set_unknown_control_is_a_client_error(client):
    response = client.post("/api/camera/control", json={"name": "nope", "value": 1})
    assert response.status_code == 400


def test_cooler_without_hardware_is_a_client_error(client):
    response = client.post("/api/camera/cooler", json={"enabled": True, "target_c": -10})
    assert response.status_code == 400


def test_get_and_patch_config(client):
    assert client.get("/api/config").json()["video"]["fps"] == 24
    response = client.patch("/api/config", json={"video": {"fps": 30}})
    assert response.status_code == 200
    assert response.json()["video"]["fps"] == 30


def test_patch_invalid_config_is_rejected(client):
    assert client.patch("/api/config", json={"video": {"fps": 0}}).status_code == 400


def test_session_lifecycle(client, state):
    start = client.post("/api/session/start", json={"overrides": {"frame_count": 2}})
    assert start.status_code == 200
    assert wait_for(lambda: client.get("/api/session").json()["state"] == "finished")
    body = client.get("/api/session").json()
    assert body["frames_captured"] == 2


def test_starting_twice_conflicts(client, state):
    client.post("/api/session/start", json={"overrides": {"frame_count": 500}})
    assert wait_for(lambda: client.get("/api/session").json()["frames_captured"] >= 1)
    assert client.post("/api/session/start", json={}).status_code == 409
    assert client.post("/api/session/stop").status_code == 200
    assert wait_for(lambda: client.get("/api/session").json()["state"] == "finished")


def test_sessions_listing(client):
    client.post("/api/session/start", json={"overrides": {"frame_count": 1}})
    assert wait_for(lambda: client.get("/api/session").json()["state"] == "finished")
    sessions = client.get("/api/sessions").json()["sessions"]
    assert sessions[0]["name"] == "test"


def test_preview_returns_jpeg(client):
    client.post("/api/session/start", json={"overrides": {"frame_count": 1}})
    assert wait_for(lambda: client.get("/api/session").json()["state"] == "finished")
    response = client.get("/api/preview.jpg")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content[:2] == b"\xff\xd8"


def test_preview_is_not_found_before_any_frame(client):
    assert client.get("/api/preview.jpg").status_code == 404


def test_compile_endpoint_creates_job(client, state):
    client.post("/api/session/start", json={"overrides": {"frame_count": 1}})
    assert wait_for(lambda: client.get("/api/session").json()["state"] == "finished")
    state.compile_fn = lambda manifest, output, config, **kwargs: output
    response = client.post("/api/compile", json={"session": "test"})
    assert response.status_code == 200
    job_id = response.json()["id"]
    assert wait_for(lambda: client.get(f"/api/jobs/{job_id}").json()["state"] == "finished")
    assert client.get("/api/jobs").json()["jobs"][0]["id"] == job_id


def test_compile_unknown_session_is_not_found(client):
    assert client.post("/api/compile", json={"session": "ghost"}).status_code == 404


def test_unknown_job_is_not_found(client):
    assert client.get("/api/jobs/does-not-exist").status_code == 404


def test_darks_endpoints(client):
    response = client.post("/api/darks", json={"exposure_s": 0.01, "gain": 0.0, "frames": 2})
    assert response.status_code == 200
    job_id = response.json()["id"]
    assert wait_for(lambda: client.get(f"/api/jobs/{job_id}").json()["state"] == "finished")
    darks = client.get("/api/darks").json()["darks"]
    assert len(darks) == 1
    assert client.delete(f"/api/darks/{darks[0]['name']}").status_code == 200
    assert client.get("/api/darks").json()["darks"] == []


def test_delete_missing_dark_is_not_found(client):
    assert client.delete("/api/darks/nope.fits").status_code == 404


def test_schedule_endpoints(client):
    assert client.get("/api/schedule").json()["config"]["enabled"] is False
    response = client.put(
        "/api/schedule",
        json={"enabled": True, "mode": "fixed", "fixed_start": "22:00", "fixed_end": "05:00"},
    )
    assert response.status_code == 200
    assert response.json()["config"]["enabled"] is True
    assert client.put("/api/schedule", json={"enabled": False}).json()["config"]["enabled"] is False


def test_websocket_pushes_status(client):
    with client.websocket_connect("/api/ws") as websocket:
        message = websocket.receive_json()
        assert "session" in message
        assert "camera" in message


def test_index_is_served_when_frontend_is_missing(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "NTTL" in response.text
