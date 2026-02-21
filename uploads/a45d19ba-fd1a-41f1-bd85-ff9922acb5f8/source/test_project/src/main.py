from src.auth import login, verify_token
from src.database import get_user, save_user

def main():
    """Application entry point."""
    token = login("admin", "password")
    print(f"Logged in. Token: {token}")

    user = get_user("admin")
    print(f"User: {user}")

if __name__ == "__main__":
    main()
