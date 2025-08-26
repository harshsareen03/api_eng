import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-secret")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "users.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "change-jwt-secret")
    JWT_ACCESS_TOKEN_EXPIRES = 3600  # seconds (1 hour)
    JWT_REFRESH_TOKEN_EXPIRES = 604800  # seconds (7 days)
