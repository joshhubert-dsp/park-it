"""
Example Park-It server program.

- `DummySpaceUpdate` is a placeholder space update model class that will work with
`tests/mock_updater_client.py` for testing purposes. You must create a model for
your sensor's update payload.
- if PROJECT ROOT is your current working dir, the commented out Path args
are the defaults.
"""

from pathlib import Path

import uvicorn

from park_it.app.build_app import build_app
from park_it.models.space_update import DummySpaceUpdate

# python-dotenv package recommended for setting env var `PARK_IT_WAITLIST_PASSWORD` in dev mode
# from dotenv import load_dotenv
# load_dotenv()

PROJECT_ROOT = Path(__file__).parent

if __name__ == "__main__":
    app = build_app(
        space_update_model=DummySpaceUpdate,
        # app_config=PROJECT_ROOT / "app-config.yaml",
        # sqlite_dir=PROJECT_ROOT / "sqlite-dbs",
        # google_token_path=PROJECT_ROOT / "auth-token.json",
        # site_dir=PROJECT_ROOT / "site",
    )
    uvicorn.run(app, host="127.0.0.1", port=8000)
