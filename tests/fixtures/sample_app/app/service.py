from app.repository import load_user


def get_profile(user_id: int) -> dict[str, object]:
    return load_user(user_id)

