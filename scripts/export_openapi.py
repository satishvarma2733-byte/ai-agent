"""Write the app/ API schema to openapi.json (consumed by web/ `npm run gen:api`).

    python -m scripts.export_openapi          # write openapi.json
    python -m scripts.export_openapi --check  # exit 1 if openapi.json is out of date (CI)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

OUTPUT = Path(__file__).resolve().parents[1] / "openapi.json"


def build_schema() -> str:
    # Importing the app runs migrations; use a throwaway database so no real data is touched.
    tmp = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{Path(tmp, 'openapi.db').as_posix()}"
    os.environ.setdefault("APP_ENV", "local")
    from app.main import app

    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main() -> None:
    schema = build_schema()
    if "--check" in sys.argv:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != schema:
            sys.exit("openapi.json is out of date: run `python -m scripts.export_openapi` and commit it.")
        print("openapi.json is up to date")
        return
    OUTPUT.write_text(schema, encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
