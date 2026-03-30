"""
Example Park-It server program.

- `DummySpaceUpdate` is a placeholder space update model class that will work with
  `tests/mock_updater_client.py` for testing purposes. You must create a model for
  your sensor's update payload.
- python-dotenv package with a .env file is convenient for setting the environment variable
  `PARK_IT_WAITLIST_PASSWORD` for development, but passing a text file path to
  waitlist_password_path is more secure for production.
- if PROJECT ROOT is your current working dir, the commented out Path args
  are the defaults (not including waitlist_password_path).
"""

from pathlib import Path

import uvicorn

from park_it.app.build_app import build_app
from park_it.models.space_update import DummySpaceUpdate

# from dotenv import load_dotenv
# load_dotenv()

PROJECT_ROOT = Path(__file__).parent

if __name__ == "__main__":
    app = build_app(
        space_update_model=DummySpaceUpdate,
        # app_config=PROJECT_ROOT / "app-config.yaml",
        # sqlite_dir=PROJECT_ROOT / "sqlite-dbs",
        # site_dir=PROJECT_ROOT / "site",
        # google_token_path=PROJECT_ROOT / "auth-token.json",
        # waitlist_password_path="waitlist-pw.txt"
    )
    uvicorn.run(app, host="127.0.0.1", port=8000)
