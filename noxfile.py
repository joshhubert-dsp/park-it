import nox

PYTHONS = ["3.11", "3.12", "3.13"]


@nox.session(python=PYTHONS)
def tests(session: nox.Session) -> None:
    session.run("uv", "sync", "--group", "dev", "--active", external=True)
    session.run("pytest", *session.posargs, external=True)
