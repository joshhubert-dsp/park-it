from dataclasses import dataclass
from typing import Protocol

from devtools import pformat
from jinja2 import Environment
from loguru import logger

from park_it.models.app_config import AppConfig
from park_it.models.waitlist import WaitlistEntry
from park_it.services.email.build_email import (
    build_join_confirm_email,
    build_leave_confirm_email,
    build_space_free_email,
    build_space_occupied_email,
)


class Emailer(Protocol):
    """Protocol defining the email sending operations the app relies on."""

    def send_join_confirmation(
        self,
        entry: WaitlistEntry,
        waitlist_place: int,
        config: AppConfig,
        jinja_env: Environment,
    ) -> bool: ...

    def send_leave_confirmation(
        self, entry: WaitlistEntry, config: AppConfig, jinja_env: Environment
    ) -> bool: ...

    def notify_free_space(
        self, entry: WaitlistEntry, config: AppConfig, jinja_env: Environment
    ) -> bool: ...

    def notify_space_now_occupied(
        self, entry: WaitlistEntry, config: AppConfig, jinja_env: Environment
    ) -> bool: ...


@dataclass
class PrintDebugEmailer(Emailer):
    """just log the email text to console."""

    # client: simplegmail.Gmail | None = None

    def send_join_confirmation(
        self,
        entry: WaitlistEntry,
        waitlist_place: int,
        config: AppConfig,
        jinja_env: Environment,
    ) -> bool:
        logger.debug(
            pformat(
                build_join_confirm_email(
                    entry, waitlist_place, config, jinja_env
                ).as_string()
            )
        )
        return True

    def send_leave_confirmation(
        self, entry: WaitlistEntry, config: AppConfig, jinja_env: Environment
    ) -> bool:
        logger.debug(
            pformat(build_leave_confirm_email(entry, config, jinja_env).as_string())
        )
        return True

    def notify_free_space(
        self, entry: WaitlistEntry, config: AppConfig, jinja_env: Environment
    ) -> bool:
        logger.debug(
            pformat(build_space_free_email(entry, config, jinja_env).as_string())
        )
        return True

    def notify_space_now_occupied(
        self, entry: WaitlistEntry, config: AppConfig, jinja_env: Environment
    ) -> bool:
        logger.debug(
            pformat(build_space_occupied_email(entry, config, jinja_env).as_string())
        )
        return True
