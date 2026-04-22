"""Deprecated: snapshot receiving is now handled by webhook_server.py.
Run: uvicorn webhook_server:app --host 127.0.0.1 --port 80
"""

from webhook_server import app
