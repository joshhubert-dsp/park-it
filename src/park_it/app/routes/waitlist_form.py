from devtools import pformat
from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from loguru import logger
from markupsafe import Markup
from pydantic import ValidationError
from starlette.templating import _TemplateResponse

from park_it.app.dependencies import WaitlistDependencies
from park_it.app.utils import get_dep, get_place_int_suffix, get_wait_deps
from park_it.models.app_config import AppConfig
from park_it.models.waitlist import WaitlistRequest
from park_it.services.db.waitlist_db import JoinedListAlready

WAITLIST_RESPONSE_TEMPLATE = "site/waitlist_response.html.j2"

# --- RESOURCE ENDPOINT FUNCTIONS ---
waitlist_form_router = APIRouter(prefix="/waitlist")


# TODO is it kosher to join the waitlist pre-emptively even if the space of your desired
# type is currently free? Thinking could make sense in contexts such as someone wanting
# to reserve for the evening during the day while they're at work.


def validate_request(form) -> WaitlistRequest:
    form_dict = dict(form)
    logger.debug(pformat(form_dict))
    return WaitlistRequest.model_validate(form_dict)


@waitlist_form_router.post("/join", response_class=_TemplateResponse)
async def join_waitlist(
    request: Request,
    config: AppConfig = Depends(get_dep("config")),
    templates: Jinja2Templates = Depends(get_dep("templates")),
    wait_deps: WaitlistDependencies = Depends(get_wait_deps),
) -> _TemplateResponse:
    try:
        entry = validate_request(await request.form()).to_entry()
    except ValidationError as e:
        return invalid_input_response(request, e, templates)

    try:
        wait_deps.to_notify_db.insert(entry)
        place_num = wait_deps.to_notify_db.count(entry.space_type)
        logger.debug(f"WAITLIST JOIN:\n{pformat(entry)}")
        logger.debug(f"{entry.space_type.upper()} TO NOTIFY COUNT: {place_num}")
    except JoinedListAlready:
        logger.debug("email joined waitlist already")
        fail_msg = Markup(
            "This email has already joined the waitlist. Check for a prior email "
            f"from <b><u>{config.app_email}</u></b> with the details."
        )
        return denial_response(request, fail_msg, templates)

    wait_deps.emailer.send_join_confirmation(
        entry=entry, waitlist_place=place_num, config=config, jinja_env=templates.env
    )

    success_msg = Markup(
        f"<b><u>{entry.email}</u></b> joined the <b>{entry.space_type.upper()}</b> space waitlist: "
        f"<b>{place_num}{get_place_int_suffix(place_num)}</b> in line. "
        f"You've been sent a confirmation email with more details."
    )
    return success_response(request, success_msg, templates)


@waitlist_form_router.post("/leave", response_class=_TemplateResponse)
async def leave_waitlist(
    request: Request,
    config: AppConfig = Depends(get_dep("config")),
    templates: Jinja2Templates = Depends(get_dep("templates")),
    wait_deps: WaitlistDependencies = Depends(get_wait_deps),
) -> _TemplateResponse:
    try:
        entry = validate_request(await request.form()).to_entry()
    except ValidationError as e:
        return invalid_input_response(request, e, templates)

    # try:
    if wait_deps.to_notify_db.delete(entry.email):
        place_num = wait_deps.to_notify_db.count(entry.space_type)
        logger.debug(f"WAITLIST LEAVE:\n{pformat(entry)}")
        logger.debug(f"{entry.space_type.upper()} TO NOTIFY COUNT: {place_num}")
    else:
        logger.debug("email not in waitlist")
        return denial_response(
            request, "This email is not present in the waitlist.", templates
        )

    wait_deps.emailer.send_leave_confirmation(
        entry=entry, config=config, jinja_env=templates.env
    )

    success_msg = Markup(f"<b><u>{entry.email}</u></b> left the waitlist.")
    return success_response(request, success_msg, templates)


# --- RESPONSE TEMPLATES ---


def success_response(
    request: Request, success_msg: str, templates: Jinja2Templates
) -> _TemplateResponse:
    """send response to render success message"""

    return templates.TemplateResponse(
        request,
        name=WAITLIST_RESPONSE_TEMPLATE,
        context={"error": False, "message": success_msg},
    )


def invalid_input_response(
    request: Request, exc: ValidationError, templates: Jinja2Templates
) -> _TemplateResponse:
    """
    prepare a template with more palatable validation error messages, to display to user
    at top of web form
    """
    errors = exc.errors()
    error_msgs = []
    for e in errors:
        if e["loc"]:
            error_msgs.append(f"{e['loc'][0]}: " + e["msg"].split(",")[0])
        else:
            error_msgs.append(e["msg"])
        if error_msgs[-1][-1] != ".":
            error_msgs[-1] = error_msgs[-1] + "."

    return templates.TemplateResponse(
        request,
        name=WAITLIST_RESPONSE_TEMPLATE,
        context={
            "error": True,
            "message": " ".join(error_msgs).replace("Value error, ", ""),
        },
        status_code=200,
    )


def denial_response(
    request: Request, message: str, templates: Jinja2Templates
) -> _TemplateResponse:
    """
    Jinja template response for denial of the user's request, with explanatory message.
    """
    return templates.TemplateResponse(
        request,
        name=WAITLIST_RESPONSE_TEMPLATE,
        context={"error": True, "message": message},
        status_code=200,
    )
