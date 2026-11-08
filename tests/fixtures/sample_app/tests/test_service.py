from app.service import get_profile


def test_get_profile() -> None:
    assert get_profile(1)["id"] == 1

