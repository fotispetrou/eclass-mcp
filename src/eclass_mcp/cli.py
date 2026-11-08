"""Command line entry point: run the server, store credentials, or do a quick
end-to-end check against the real site."""

from __future__ import annotations

import argparse
import getpass
import logging
import sys
import traceback

from .config import KEYRING_SERVICE, ConfigError, Settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eclass-mcp", description="MCP server for Open eClass")
    parser.add_argument("-v", "--verbose", action="store_true", help="log requests to stderr")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", help="run the MCP server on stdio (default)")
    sub.add_parser("check", help="log in and try every endpoint once")
    sub.add_parser("login", help="store username and password in the system keyring")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    if args.command == "login":
        return store_credentials()
    if args.command == "check":
        return check()
    from .server import run
    run()
    return 0


def store_credentials() -> int:
    try:
        import keyring
    except ImportError:
        print("keyring is not installed; install with: pip install 'eclass-mcp[keyring]'", file=sys.stderr)
        return 1
    username = input("eClass username: ").strip()
    password = getpass.getpass("eClass password: ")
    if not username or not password:
        print("nothing stored", file=sys.stderr)
        return 1
    keyring.set_password(KEYRING_SERVICE, "username", username)
    keyring.set_password(KEYRING_SERVICE, username, password)
    print(f"stored credentials for {username} in the system keyring")
    return 0


def check() -> int:
    """Hit each endpoint once and print what came back, so a user on another
    eClass instance can see what works without reading any code."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1

    from .client import EclassClient

    client = EclassClient(settings)
    failures = 0

    def step(label, fn):
        nonlocal failures
        try:
            result = fn()
        except Exception as exc:
            failures += 1
            print(f"FAIL  {label}: {type(exc).__name__}: {exc}")
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                traceback.print_exc()
            return None
        if isinstance(result, list):
            sample = result[0] if result else None
            summary = f"{len(result)} items"
            if sample:
                summary += ", first: " + str(sample.get("title") or sample.get("subject") or sample.get("name") or sample)[:70]
        elif isinstance(result, dict):
            summary = ", ".join(f"{k}={str(v)[:40]}" for k, v in list(result.items())[:4])
        else:
            summary = str(result)[:80]
        print(f"ok    {label}: {summary}")
        return result

    print(f"eClass: {settings.base_url}  user: {settings.username}")
    if step("login", lambda: client.login() or "session established") is None:
        print("stopping here: repeated failed logins get the IP blocked for a few minutes")
        return 1
    step("whoami", client.whoami)
    courses = step("courses", client.courses) or []
    step("announcements (all courses)", lambda: client.announcements(limit=5))
    from datetime import datetime, timedelta
    now = datetime.now()
    step("calendar (next 60 days)", lambda: client.calendar(now, now + timedelta(days=60)))
    step("messages (inbox)", lambda: client.messages(limit=5))
    if courses:
        code = courses[0]["code"]
        print(f"--- course {code}: {courses[0].get('title')}")
        step("course tools (mobile api)", lambda: client.course_tools(code))
        step("announcements", lambda: client.announcements(code, limit=5))
        step("assignments", lambda: client.assignments(code))
        step("exercises", lambda: client.exercises(code))
        step("documents", lambda: client.documents(code))
    client.close()
    print("all good" if not failures else f"{failures} step(s) failed; run with -v for details")
    return 1 if failures else 0
