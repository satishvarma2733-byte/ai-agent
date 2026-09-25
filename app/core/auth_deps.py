from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User
from app.core.permissions import at_least, rank

# OAuth2 bearer token helper. Configured with a default token endpoint.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

_READ_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    token: str | None = Depends(oauth2_scheme)
) -> User:
    """FastAPI Dependency retrieving the currently authenticated user from token payload."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception

    payload = decode_token(token)
    # Refresh tokens are long-lived and must only be accepted by /api/auth/refresh.
    if payload is None or payload.get("refresh"):
        raise credentials_exception

    email: str | None = payload.get("sub")
    session_id: str | None = payload.get("sid")
    if email is None or session_id is None:
        raise credentials_exception

    # Logged-out or revoked sessions stop working immediately, not when the JWT expires.
    from app.services.auth_service import session_is_active
    if not session_is_active(db, session_id):
        raise credentials_exception

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception

    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user profile"
        )

    from app.core.tenancy import bind_session_to_tenant
    bind_session_to_tenant(db, user.tenant_id)

    # Viewers are read-only everywhere, including routes without their own role check.
    if user.role == "Viewer" and request.method not in _READ_METHODS and not request.url.path.startswith("/api/auth/"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Viewers have read-only access.")
    return user

class RoleChecker:
    """Allows users whose role is at least the lowest role listed (Owner > Admin > Manager > Agent > Viewer).
    `RoleChecker(["Admin", "Manager"])` therefore admits Managers, Admins, and Owners."""
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles
        self.minimum = min(allowed_roles, key=rank)

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        if not at_least(current_user.role, self.minimum):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires the {self.minimum} role or higher."
            )
        return current_user
