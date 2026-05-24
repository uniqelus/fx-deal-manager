from jwt import InvalidTokenError, PyJWKClient
import jwt

from fx_deal_manager.core.config import settings
from fx_deal_manager.domain.schemas import UserClaims

_jwks_client: PyJWKClient | None = None


def get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(settings.jwks_url)
    return _jwks_client


class AuthenticationError(Exception):
    pass


def validate_user_token(token: str) -> UserClaims:
    try:
        signing_key = get_jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "iss", "exp", "iat", "jti", "token_type"]},
        )
    except InvalidTokenError as exc:
        raise AuthenticationError("invalid or expired token") from exc

    if claims.get("token_type") != "user":
        raise AuthenticationError("user token required")

    return UserClaims(
        user_id=claims["user_id"],
        email=claims["email"],
        first_name=claims["first_name"],
        last_name=claims["last_name"],
        role=claims["role"],
        expires_at=claims["exp"],
    )
