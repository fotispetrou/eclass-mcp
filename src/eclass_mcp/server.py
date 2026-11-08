"""MCP tool definitions. Every tool is a thin wrapper over EclassClient so
the server stays easy to read; the parsing lives in parsers.py."""

from __future__ import annotations

import functools
from datetime import datetime, timedelta

import httpx
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .client import EclassClient, EclassError
from .config import ConfigError, Settings

INSTRUCTIONS = """Read access to a student's Open eClass account (courses, announcements,
deadlines, assignments, exercises, documents, messages).

Course codes are the segment after /courses/ in eClass URLs (for example DS101);
call list_courses first to find them. Dates are returned both as eClass prints
them and normalized in *_iso fields (local time, YYYY-MM-DD HH:MM)."""

server = MCPServer("eclass", instructions=INSTRUCTIONS)

_client: EclassClient | None = None


def client() -> EclassClient:
    global _client
    if _client is None:
        _client = EclassClient(Settings.from_env())
    return _client


def tool(fn):
    """Register fn as a tool and turn the failures we expect (bad login,
    network, missing page) into ToolError so the model sees the message
    instead of a generic 'error executing tool'."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (EclassError, ConfigError, ValueError, httpx.HTTPError) as exc:
            raise ToolError(f"{type(exc).__name__}: {exc}") from exc

    return server.tool()(wrapper)


@tool
def whoami() -> dict:
    """Check that the login works and see which account and eClass site are in use."""
    return client().whoami()


@tool
def list_courses() -> list[dict]:
    """List the courses the student is enrolled in, with code, title and teachers."""
    return client().courses()


@tool
def get_course_tools(course: str) -> list[dict]:
    """Which modules (documents, assignments, exercises, forum...) a course has enabled."""
    return client().course_tools(course)


@tool
def get_announcements(course: str | None = None, limit: int = 30, search: str = "") -> list[dict]:
    """Latest announcements across all courses, or for one course if a code is given.
    Bodies are plain text; use get_announcement for the full text of one."""
    return client().announcements(course, limit, search)


@tool
def get_announcement(course: str, announcement_id: int) -> dict:
    """Full text of one announcement."""
    return client().announcement(course, announcement_id)


@tool
def get_deadlines(days: int = 30, past_days: int = 0, course: str | None = None) -> list[dict]:
    """Upcoming calendar events for all courses: assignment and exercise deadlines,
    agenda entries, teleconferences and personal events. Looks `days` ahead and
    `past_days` back from now."""
    now = datetime.now()
    events = client().calendar(now - timedelta(days=past_days), now + timedelta(days=days))
    if course:
        events = [e for e in events if e.get("course") == course]
    return events


@tool
def get_assignments(course: str) -> list[dict]:
    """Assignments of a course with deadline, submission status and grade."""
    return client().assignments(course)


@tool
def get_assignment(course: str, assignment_id: int) -> dict:
    """Details of one assignment: description, attached files, deadline, and the
    student's own submission if there is one."""
    return client().assignment(course, assignment_id)


@tool
def get_exercises(course: str) -> list[dict]:
    """Exercises (quizzes) of a course with their availability window and whether
    the student has attempted them."""
    return client().exercises(course)


@tool
def list_documents(course: str, path: str = "/") -> list[dict]:
    """Files and folders in a course's Documents area. Pass a folder's `path` to
    list inside it."""
    return client().documents(course, path)


@tool
def download_document(course: str, path: str, destination: str | None = None) -> dict:
    """Download a document (or a whole folder as a zip) by its `path` from
    list_documents. Saves under ~/Downloads/eclass/<course>/ unless a destination
    directory is given, and returns the local file path."""
    return client().download(course, path, destination)


@tool
def get_messages(mailbox: str = "inbox", limit: int = 30, search: str = "") -> list[dict]:
    """Personal and course messages. `mailbox` is 'inbox' or 'outbox'."""
    return client().messages(mailbox, limit, search)


@tool
def get_message(message_id: int, mailbox: str = "inbox") -> dict:
    """Full text of one message, with sender, recipients and attachment if any."""
    return client().message(message_id, mailbox)


def run() -> None:
    server.run()
