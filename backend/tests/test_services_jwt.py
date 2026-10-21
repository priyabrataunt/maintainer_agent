from backend.services.jwt import create_access_token, decode_access_token


def test_access_token_round_trips_user_id():
    token = create_access_token(user_id=42)

    payload = decode_access_token(token)

    assert payload["sub"] == "42"
