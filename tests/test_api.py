from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_locations_seeded() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/locations?contenttypeid=39&limit=3")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) > 0
    assert {"contentid", "title", "mapx", "mapy"}.issubset(payload[0].keys())


def test_chat_contract() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"message": "대전 맛집 추천해줘", "history": []})
    assert response.status_code == 200
    payload = response.json()
    assert "answer" in payload
    assert "referenced_items" in payload
    assert "sources" in payload


def test_create_post_returns_id() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/posts",
            json={
                "title": "테스트 게시글",
                "place": "테스트 장소",
                "content": "게시글 작성 응답에 id가 포함되는지 확인합니다.",
                "category": "자유",
                "password": "1234",
            },
        )
    assert response.status_code == 201
    payload = response.json()
    assert isinstance(payload["id"], int)
    assert payload["message"]
