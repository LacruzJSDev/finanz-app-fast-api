from app.shared.dependencies import DbSession
from app.users.repository import UserRepository


def get_user_repository(db: DbSession) -> UserRepository:
    return UserRepository(db)
