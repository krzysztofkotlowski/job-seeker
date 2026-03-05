"""User sync from Keycloak token."""

from sqlalchemy.orm import Session

from app.models.tables import UserRow


def get_or_create_user(db: Session, keycloak_id: str, email: str | None = None, username: str | None = None) -> UserRow:
    """Get existing user by keycloak_id or create one."""
    user = db.query(UserRow).filter(UserRow.keycloak_id == keycloak_id).first()
    if user:
        if email is not None and user.email != email:
            user.email = email
        if username is not None and user.username != username:
            user.username = username
        db.commit()
        db.refresh(user)
        return user
    user = UserRow(
        keycloak_id=keycloak_id,
        email=email,
        username=username,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
