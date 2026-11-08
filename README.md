# eclass-mcp

An [MCP](https://modelcontextprotocol.io) server for the [Open eClass](https://www.openeclass.org/)
platform used by Greek universities. It logs in with your student account and
gives an MCP client (Claude Desktop, Claude Code, Cursor, ...) read access to:

- your courses and which tools each one has enabled
- announcements, across all courses or per course
- deadlines: assignments, exercises, agenda entries and personal calendar events
- assignments, with submission status, grade and the details page
- exercises (quizzes) and their availability window
- documents, including downloading files or whole folders
- personal and course messages

It is read-only: nothing is submitted, sent or changed on eClass.

Written against the University of Thessaly instance (`eclass.uth.gr`, Open eClass
3.16). Other 3.x instances should work by setting `ECLASS_URL`; see
[other universities](#other-universities).

## Install

You need Python 3.10 or newer. With [uv](https://docs.astral.sh/uv/):

```
git clone https://github.com/fotispetrou/eclass-mcp
cd eclass-mcp
uv sync
```

or with pip, into a virtualenv:

```
pip install git+https://github.com/fotispetrou/eclass-mcp
```

## Credentials

The server needs your eClass username and password. Either put them in the
environment (`ECLASS_USERNAME`, `ECLASS_PASSWORD`), or store them once in the
system keyring (Windows Credential Manager, macOS Keychain, GNOME Keyring):

```
uv run --extra keyring eclass-mcp login
```

Variables:

| variable             | default                  |                                        |
| -------------------- | ------------------------ | -------------------------------------- |
| `ECLASS_URL`         | `https://eclass.uth.gr`  | your university's eClass               |
| `ECLASS_USERNAME`    |                          |                                        |
| `ECLASS_PASSWORD`    |                          | falls back to the keyring              |
| `ECLASS_DOWNLOAD_DIR`| `~/Downloads/eclass`     | where `download_document` saves files  |

Check that everything works before wiring it into a client:

```
uv run eclass-mcp check
```

This logs in and calls every endpoint once, printing a line per step.

## Client configuration

Claude Desktop (`claude_desktop_config.json`) and Cursor (`mcp.json`) take the
same shape:

```json
{
  "mcpServers": {
    "eclass": {
      "command": "uv",
      "args": ["--directory", "C:/path/to/eclass-mcp", "run", "eclass-mcp"],
      "env": {
        "ECLASS_URL": "https://eclass.uth.gr",
        "ECLASS_USERNAME": "your_username",
        "ECLASS_PASSWORD": "your_password"
      }
    }
  }
}
```

Leave `ECLASS_PASSWORD` out if you stored it in the keyring. Claude Code:

```
claude mcp add eclass -e ECLASS_USERNAME=your_username -- uv --directory C:/path/to/eclass-mcp run eclass-mcp
```

If you installed with pip, use `eclass-mcp` as the command and drop the `uv` arguments.

## Tools

| tool                | arguments                                 |
| ------------------- | ----------------------------------------- |
| `whoami`            |                                           |
| `list_courses`      |                                           |
| `get_course_tools`  | `course`                                  |
| `get_announcements` | `course?`, `limit=30`, `search=""`        |
| `get_announcement`  | `course`, `announcement_id`               |
| `get_deadlines`     | `days=30`, `past_days=0`, `course?`       |
| `get_assignments`   | `course`                                  |
| `get_assignment`    | `course`, `assignment_id`                 |
| `get_exercises`     | `course`                                  |
| `list_documents`    | `course`, `path="/"`                      |
| `download_document` | `course`, `path`, `destination?`          |
| `get_messages`      | `mailbox="inbox"`, `limit=30`, `search=""`|
| `get_message`       | `message_id`, `mailbox="inbox"`           |

`course` is the code in the course URL (`.../courses/DS101/` -> `DS101`).

## How it works

Open eClass has no public REST API for students, so the server uses the same
HTTP endpoints the web interface does: a form login, the DataTables JSON
endpoints behind "my announcements" and the message inbox, the calendar feed
that drives the personal calendar page, the mobile-app XML endpoints for course
tools, and plain HTML parsing for assignments, exercises and documents.

The session cookie is kept in memory; if eClass expires it, the server logs in
again once. A rejected password is reported and not retried for five minutes,
since eClass temporarily blocks an IP after a few failed logins.

## Other universities

Set `ECLASS_URL` to your institution's eClass and run `eclass-mcp check`. The
parsing targets the 3.x template markup; sites behind a CAS/SSO login page
(for example eclass.uoa.gr) are not supported by the form login used here. If
`check` reports failures on your instance, open an issue with its output.

## Development

```
uv sync
uv run pytest
```

Tests run against HTML fixtures copied from the Open eClass templates, so they
do not need an account. `eclass-mcp check -v` is the live test.

## License

MIT
