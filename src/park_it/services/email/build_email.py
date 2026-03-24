from email.message import EmailMessage
from email.utils import formataddr

from jinja2 import Environment
from mistune import html

from park_it.models.app_config import AppConfig
from park_it.models.waitlist import WaitlistEntry


# TODO should from_name be account name or app name?
def _build_email_msg_md(
    to_email: str,
    from_email: str,
    subject: str,
    md_body: str,
    to_name: str | None = None,
    from_name: str | None = None,
) -> EmailMessage:
    """builds an EmailMessage, converting a markdown body to html"""
    msg = EmailMessage()
    msg["To"] = formataddr((to_name, to_email))
    msg["From"] = formataddr((from_name, from_email))
    msg["Subject"] = subject

    # Plain text fallback + HTML alternative
    msg.set_content(md_body)
    msg.add_alternative(html(md_body), subtype="html")
    return msg


def build_join_confirm_email(
    entry: WaitlistEntry, waitlist_place: int, config: AppConfig, jinja_env: Environment
) -> EmailMessage:
    tpl = jinja_env.get_template("email/join_confirm.md.j2")
    md_body = tpl.render(entry=entry, waitlist_place=waitlist_place, config=config)
    return _build_email_msg_md(
        to_email=entry.email,
        from_email=config.app_email,
        from_name=config.app_email_name,
        subject=f"You Joined the {entry.space_type.upper()} Space Waitlist",
        md_body=md_body,
    )


def build_leave_confirm_email(
    entry: WaitlistEntry, config: AppConfig, jinja_env: Environment
) -> EmailMessage:
    tpl = jinja_env.get_template("email/leave_confirm.md.j2")
    md_body = tpl.render(config=config)
    return _build_email_msg_md(
        to_email=entry.email,
        from_email=config.app_email,
        from_name=config.app_email_name,
        subject="You Left the Space Waitlist",
        md_body=md_body,
    )


# TODO possibly include the free SpaceModel to notify with the specific space
# The complication there is that occupied notifications aren't sent out til all spaces
# of a type are occupied again, so user could end up getting a different free space if
# there are multiple available
def build_space_free_email(
    entry: WaitlistEntry, config: AppConfig, jinja_env: Environment
) -> EmailMessage:
    tpl = jinja_env.get_template("email/space_free.md.j2")
    md_body = tpl.render(entry=entry, config=config)
    return _build_email_msg_md(
        to_email=entry.email,
        from_email=config.app_email,
        from_name=config.app_email_name,
        subject=f"{entry.space_type.upper()} Space is Available!",
        md_body=md_body,
    )


def build_space_occupied_email(
    entry: WaitlistEntry, config: AppConfig, jinja_env: Environment
) -> EmailMessage:
    tpl = jinja_env.get_template("email/space_occupied.md.j2")
    md_body = tpl.render(entry=entry, config=config)
    return _build_email_msg_md(
        to_email=entry.email,
        from_email=config.app_email,
        from_name=config.app_email_name,
        subject=f"{entry.space_type.upper()} Space No Longer Available",
        md_body=md_body,
    )
