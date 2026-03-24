from __future__ import annotations

import sys
from importlib import metadata
from importlib.resources import files


def main() -> None:
    """test run by publish-pypi workflow on both sdist and wheel"""
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
        "example/aerial-view-of-a-parking-lot-in-austin-in-need-of-repair.jpg"
        "example/app-config.yaml",
        "example/mkdocs.yml",
    ]
    for f in nonpy_files_to_check:
        assert (files("park_it") / f).is_file(), f"Missing file in package data: {f}"

    # 3) FastAPI templating can load it (catches wrong loader/search path)

    from park_it.app.dependencies import get_jinja_env

    env = get_jinja_env()
    # Will raise TemplateNotFound if broken
    env.get_template("space_states.html.j2")

    # 4) MkDocs plugin entry point resolves
    eps = metadata.entry_points(group="mkdocs.plugins")
    ep = next((e for e in eps if e.name == "park-it"), None)
    assert ep is not None, "mkdocs.plugins entry point 'park-it' not found"
    plugin_cls = ep.load()
    assert plugin_cls is not None, "entry point load returned None"

    # Optional: assert it’s the class you expect
    assert plugin_cls.__name__ == "ParkItPlugin"

    print("publish_test: ok", file=sys.stderr)


if __name__ == "__main__":
    main()
