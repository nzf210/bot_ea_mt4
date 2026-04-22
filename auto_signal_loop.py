"""Deprecated: AI signal loop is now embedded inside webhook_server.py via an internal queue worker.
Run: uvicorn webhook_server:app --host 127.0.0.1 --port 80
"""

from webhook_server import app
