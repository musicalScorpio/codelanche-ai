from app.service import get_profile


def profile_route(user_id: int) -> dict[str, object]:
    return get_profile(user_id)

