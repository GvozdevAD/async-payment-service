"""FastAPI dependencies."""

from app.db.session import get_session

get_db = get_session
