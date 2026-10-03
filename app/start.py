"""Exec-form container entry point; PORT is the only environment value consumed."""

import os

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        server_header=False,
        proxy_headers=False,
    )
