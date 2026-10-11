# Writes the API's OpenAPI schema to api/openapi.json, the file the React
# app's TypeScript types are generated from (ROADMAP 3.1). Rerun after
# changing any route or Pydantic model - tests/test_openapi.py fails until
# the file matches the code.
#
# Run with: uv run python -m api.export_openapi

import json
from pathlib import Path

from api.main import app

OPENAPI_PATH = Path(__file__).parent / "openapi.json"


def render_openapi() -> str:
    return json.dumps(app.openapi(), indent=2) + "\n"


if __name__ == "__main__":
    OPENAPI_PATH.write_text(render_openapi())
    print(f"wrote {OPENAPI_PATH}")
