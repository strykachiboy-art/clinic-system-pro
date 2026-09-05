def test_register_route_creates_user(client):
    response = client.post(
        "/api/auth/register",
        json={
            "email": "newuser@test.com",
            "password": "strongpass123",
            "role": "admin",
        },
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["email"] == "newuser@test.com"
    assert payload["data"]["role"] == "admin"


def test_login_route_returns_tokens(client, make_user, clinic):
    user = make_user(clinic, email="loginuser@test.com", password="supersecret")

    response = client.post(
        "/api/auth/login",
        json={
            "email": "loginuser@test.com",
            "password": "supersecret",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["access_token"]
    assert payload["data"]["refresh_token"]
    assert payload["data"]["user_id"] == user.id
