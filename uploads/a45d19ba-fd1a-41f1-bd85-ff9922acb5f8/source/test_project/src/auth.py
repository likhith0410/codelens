import hashlib
import hmac

SECRET_KEY = "super-secret-key"

def verify_token(token: str) -> bool:
    """Verify a user auth token."""
    parts = token.split(".")
    if len(parts) != 2:
        return False
    payload, sig = parts
    expected = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)

def create_token(user_id: str) -> str:
    """Create an auth token for a user."""
    payload = f"user:{user_id}"
    sig = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"

def login(username: str, password: str) -> str:
    """Handle user login and return token."""
    if username == "admin" and password == "password":
        return create_token(username)
    raise ValueError("Invalid credentials")
