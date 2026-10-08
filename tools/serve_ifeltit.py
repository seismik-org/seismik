"""Development only: serve the browser form and API on one local origin.

Run with SEISMIK_REDIS_URL pointing at a development Redis instance:
    python tools/serve_ifeltit.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import uvicorn  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from api.app import create_app  # noqa: E402
from api.config import AppSettings  # noqa: E402

settings = AppSettings()
if settings.environment.lower() != "development":
    raise RuntimeError("This server is for development only")
app = create_app(settings)


@app.get("/", include_in_schema=False)
async def felt_page() -> FileResponse:
    return FileResponse(ROOT / "web" / "ifeltit.html")


app.mount("/", StaticFiles(directory=ROOT / "web"), name="web")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8080)
