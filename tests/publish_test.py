from __future__ import annotations

import argparse
import sys
from importlib import metadata
from importlib.resources import files


def main() -> None:
    """test run by publish-pypi workflow on both sdist and wheel"""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check-site-build",
        action="store_true",
        help="Assert optional MkDocs plugin support is installed and loadable.",
    )
    args = parser.parse_args()

    # 1) Import
    import park_it  # noqa: F401

    # 2) Package data is present in installed artifact
    nonpy_files_to_check = [
        "mkdocs_abuse/assets/theme-tweaks.css",
        "mkdocs_abuse/assets/park-it.css",
        "mkdocs_abuse/templates/_waitlist_form.html.j2",
        "mkdocs_abuse/templates/app.md.j2",
        "mkdocs_abuse/templates/pi_app.html.j2",
        "mkdocs_abuse/templates/pi_base.html.j2",
        "example/docs/readme.md",
        "example/.gitignore",
        "example/aerial-view-of-a-parking-lot-in-austin-in-need-of-repair.jpg",
        "example/app-config.yaml",
        "example/mkdocs.yml",
        "templates/site/space_states.html.j2",
        "templates/site/waitlist_response.html.j2",
        "templates/email/join_confirm.md.j2",
        "templates/email/leave_confirm.md.j2",
        "templates/email/space_occupied.md.j2",
        "templates/email/_salutation.md.j2",
        "templates/email/space_free.md.j2",
    ]
    for f in nonpy_files_to_check:
        assert (files("park_it") / f).is_file(), f"Missing file in package data: {f}"

    # 3) FastAPI templating can load it (catches wrong loader/search path)

    from park_it.app.dependencies import get_jinja_env

    env = get_jinja_env()
    # Will raise TemplateNotFound if broken
    env.get_template("site/space_states.html.j2")
    env.get_template("site/waitlist_response.html.j2")
    env.get_template("email/join_confirm.md.j2")
    env.get_template("email/leave_confirm.md.j2")
    env.get_template("email/space_occupied.md.j2")
    env.get_template("email/_salutation.md.j2")
    env.get_template("email/space_free.md.j2")

    if args.check_site_build:
        # 4) MkDocs plugin entry point resolves when the optional site-build extra is installed
        eps = metadata.entry_points(group="mkdocs.plugins")
        ep = next((e for e in eps if e.name == "park-it"), None)
        assert ep is not None, "mkdocs.plugins entry point 'park-it' not found"
        plugin_cls = ep.load()
        assert plugin_cls is not None, "entry point load returned None"
        assert plugin_cls.__name__ == "ParkItPlugin"

    print("publish_test: ok", file=sys.stderr)


if __name__ == "__main__":
    main()
