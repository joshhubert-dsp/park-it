from __future__ import annotations

import os
import ssl
from base64 import urlsafe_b64encode
from dataclasses import dataclass
from email.message import EmailMessage
from typing import TYPE_CHECKING

from devtools import pformat
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from jinja2 import Environment
from loguru import logger
from pydantic import FilePath

from park_it.models.app_config import AppConfig
from park_it.models.waitlist import WaitlistEntry
from park_it.services.email.build_email import (
    build_join_confirm_email,
    build_leave_confirm_email,
    build_space_free_email,
    build_space_occupied_email,
)
from park_it.services.email.emailer import Emailer

if TYPE_CHECKING:
    from googleapiclient._apis.gmail.v1 import (  # pyright: ignore[reportMissingModuleSource]
        GmailResource,
        Message,
    )

# --- Configuration ---
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
REDIRECT_PORT = int(os.getenv("OAUTH_CALLBACK_PORT", 8080))
# REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/oauth2callback"
# Note: REDIRECT_URI must be registered in your Google Cloud Console OAuth Client settings!


# NOTE: unused since GmailResource auth layer handles this automatically
def ensure_refreshed(credentials: Credentials) -> Credentials:
    if not credentials.valid and credentials.expired:
        credentials.refresh(Request())
    return credentials


def get_credentials(token_path: FilePath) -> Credentials:
    assert token_path.exists()
    creds = Credentials.from_authorized_user_file(token_path)
    logger.trace("Loaded credentials from token file.")

    if not creds.valid:
        assert creds.refresh_token
        logger.trace("Credentials expired. Refreshing...")

        try:
            creds.refresh(Request())
        except RefreshError as e:
            raise RefreshError(
                "Stored Google app refresh token is invalid or revoked. You must "
                "run the Oauth flow to get a new one, using the CLI command "
                "`park-it oauth`."
            ) from e

    assert creds is not None
    return creds


def init_gmail(token_path: FilePath) -> GmailResource:
    logger.debug("initializing GmailResource")
    creds = get_credentials(token_path)
    return build("gmail", "v1", credentials=creds)


def send_gmail_msg(gmail: GmailResource, email_msg: EmailMessage) -> Message:
    raw = urlsafe_b64encode(email_msg.as_bytes()).decode("utf-8")
    return gmail.users().messages().send(userId="me", body={"raw": raw}).execute()


@dataclass
class Gmailer(Emailer):
    """Email sender that builds a fresh Gmail client for each send."""

    token_path: FilePath

    def _send(self, msg: EmailMessage) -> Message:
        try:
            return send_gmail_msg(init_gmail(self.token_path), msg)
        except ssl.SSLError as e:
            # The Gmail API client and underlying httplib2 transport can go stale after
            # long idle periods. Rebuild the client and retry once on the observed EOF
            # failure that occurs during token refresh / first post-idle send.
            if "UNEXPECTED_EOF_WHILE_READING" not in str(e):
                raise
            logger.warning(
                "Gmail send hit SSL EOF during refresh/send; rebuilding client and retrying once."
            )
            return send_gmail_msg(init_gmail(self.token_path), msg)

    def send_join_confirmation(
        self,
        entry: WaitlistEntry,
        waitlist_place: int,
        config: AppConfig,
        jinja_env: Environment,
    ) -> bool:
        msg = build_join_confirm_email(entry, waitlist_place, config, jinja_env)
        logger.debug(pformat(msg))
        self._send(msg)
        return True

    def send_leave_confirmation(
        self, entry: WaitlistEntry, config: AppConfig, jinja_env: Environment
    ) -> bool:
        msg = build_leave_confirm_email(entry, config, jinja_env)
        logger.debug(pformat(msg))
        self._send(msg)
        return True

    def notify_free_space(
        self, entry: WaitlistEntry, config: AppConfig, jinja_env: Environment
    ) -> bool:
        msg = build_space_free_email(entry, config, jinja_env)
        logger.debug(pformat(msg))
        self._send(msg)
        return True

    def notify_space_now_occupied(
        self, entry: WaitlistEntry, config: AppConfig, jinja_env: Environment
    ) -> bool:
        msg = build_space_occupied_email(entry, config, jinja_env)
        logger.debug(pformat(msg))
        self._send(msg)
        return True


"""
Hard-earned details that prevent dumb pain later
1) Protect the endpoint like it’s holding your SSN
If your form can be hit anonymously, bots will use it as an email cannon and your burner will die.
Do these bare minimums:
CAPTCHA (or at least “honey pot” hidden field)
Rate limiting by IP + by recipient email
Require email confirmation (“click to verify”) before sending anything beyond a single confirmation email

2) Keep volume low and content boring
Gmail is more tolerant of:
confirmation links
“Your request was received”
transactional-ish messages
Less tolerant of:
anything promotional
repeated similar emails to many domains
lots of links, URL shorteners, aggressive HTML

3) Don’t use “External app in Testing mode” in a way that blocks you
The OAuth consent screen “testing” user cap mostly matters when lots of different users
authenticate your app. Here only your burner account authenticates, so you’re fine.
You’re not onboarding senders, you’re using one mailbox as a robot.

"""
