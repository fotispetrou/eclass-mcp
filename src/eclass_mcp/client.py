"""HTTP side: login, session upkeep and one method per thing we fetch."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx

from . import parsers
from .config import Settings

log = logging.getLogger(__name__)

LOGIN_FORM = "/main/login_form.php"
USER_AGENT = "eclass-mcp/0.1 (https://github.com/fotispetrou/eclass-mcp)"
# eClass blocks an IP after a handful of failed logins, so after a rejected
# password we stop trying for a while instead of failing on every tool call
LOGIN_RETRY_DELAY = 5 * 60


class EclassError(Exception):
    pass


class LoginError(EclassError):
    pass


class EclassClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.base_url
        self.http = httpx.Client(
            base_url=self.base_url,
            follow_redirects=True,
            timeout=settings.timeout,
            headers={"User-Agent": USER_AGENT},
        )
        self.logged_in = False
        self._retry_login_at = 0.0

    def close(self) -> None:
        self.http.close()

    # -- session ------------------------------------------------------------

    def login(self) -> None:
        if time.monotonic() < self._retry_login_at:
            raise LoginError("eClass rejected the last login; not retrying for a few minutes "
                             "so the IP does not get blocked. Check ECLASS_USERNAME/ECLASS_PASSWORD.")
        # the form page sets the session cookie that the POST then upgrades
        self.http.get(LOGIN_FORM)
        r = self.http.post(
            "/?login_page=1",
            data={"uname": self.settings.username, "pass": self.settings.password, "submit": "Είσοδος"},
            headers={"Referer": self.base_url + LOGIN_FORM},
        )
        if self._is_login_page(r):
            self._retry_login_at = time.monotonic() + LOGIN_RETRY_DELAY
            raise LoginError(parsers.login_error(r.text) or "eClass rejected the login")
        self.logged_in = True
        log.info("logged in to %s as %s", self.base_url, self.settings.username)

    @staticmethod
    def _is_login_page(r: httpx.Response) -> bool:
        # protected pages bounce to the login form instead of returning 401/403
        return "login_form.php" in str(r.url)

    def request(self, method: str, path: str, **kw) -> httpx.Response:
        if not self.logged_in:
            self.login()
        r = self.http.request(method, path, **kw)
        if self._is_login_page(r):
            # session expired server-side; log in again, once
            self.logged_in = False
            self.login()
            r = self.http.request(method, path, **kw)
            if self._is_login_page(r):
                raise LoginError("eClass keeps redirecting to the login page")
        r.raise_for_status()
        return r

    def get(self, path: str, **kw) -> httpx.Response:
        return self.request("GET", path, **kw)

    def ajax(self, path: str, params: dict) -> dict:
        """The DataTables endpoints only answer JSON to XMLHttpRequest."""
        r = self.request("GET", path, params=params, headers={"X-Requested-With": "XMLHttpRequest"})
        try:
            return r.json()
        except ValueError as exc:
            raise EclassError(f"{path} did not return JSON") from exc

    def mobile(self, script: str, **data) -> str:
        """modules/mobile/*.php take the session id as a POST 'token'."""
        if not self.logged_in:
            self.login()
        token = self.http.cookies.get("PHPSESSID")
        if not token:
            raise EclassError("no session cookie to use with the mobile API")
        r = self.http.post(f"/modules/mobile/{script}", data={"token": token, **data})
        body = r.text.strip()
        if body in ("FAILED", "EXPIRED", "NOTENABLED", "USERNOTACTIVE") or not body:
            raise EclassError(f"mobile API {script}: {body or 'empty response'}")
        return body

    # -- data ---------------------------------------------------------------

    def whoami(self) -> dict:
        r = self.get("/main/portfolio.php")
        info = parsers.parse_profile(r.text)
        info["eclass"] = self.base_url
        return info

    def courses(self) -> list[dict]:
        r = self.get("/main/my_courses.php")
        courses = parsers.parse_courses_html(r.text, self.base_url)
        if not courses:
            try:
                courses = parsers.parse_courses_xml(self.mobile("mcourses.php"))
            except (EclassError, ValueError) as exc:
                log.debug("mobile course list unavailable: %s", exc)
        for c in courses:
            c.setdefault("url", f"{self.base_url}/courses/{c['code']}/")
        return courses

    def course_tools(self, course: str) -> list[dict]:
        return parsers.parse_tools_xml(self.mobile("mtools.php", course=course))

    def announcements(self, course: str | None = None, limit: int = 30, search: str = "") -> list[dict]:
        params = {"iDisplayStart": 0, "iDisplayLength": limit, "sSearch": search, "sEcho": 1}
        if course:
            path = "/modules/announcements/index.php"
            params["course"] = course
        else:
            path = "/modules/announcements/myannouncements.php"
        return parsers.parse_announcement_rows(self.ajax(path, params), self.base_url)

    def announcement(self, course: str, announcement_id: int) -> dict:
        r = self.get("/modules/announcements/index.php", params={"course": course, "an_id": announcement_id})
        info = parsers.parse_announcement_page(r.text)
        info.update(id=announcement_id, course=course, url=str(r.url))
        return info

    def calendar(self, start: datetime, end: datetime) -> list[dict]:
        params = {"from": int(start.timestamp() * 1000), "to": int(end.timestamp() * 1000)}
        r = self.get("/main/calendar_data.php", params=params)
        try:
            data = r.json()
        except ValueError as exc:
            raise EclassError("calendar did not return JSON") from exc
        return parsers.parse_calendar(data)

    def assignments(self, course: str) -> list[dict]:
        r = self.get("/modules/work/index.php", params={"course": course})
        items = parsers.parse_assignments(r.text, self.base_url)
        self._add_calendar_deadlines(course, items)
        return items

    def assignment(self, course: str, assignment_id: int) -> dict:
        r = self.get("/modules/work/index.php", params={"course": course, "id": assignment_id})
        info = parsers.parse_assignment(r.text, str(r.url))
        info.update(id=assignment_id, course=course, url=str(r.url))
        self._add_calendar_deadlines(course, [info])
        return info

    def _add_calendar_deadlines(self, course: str, items: list[dict]) -> None:
        """The work pages print deadlines in the user's locale; the calendar
        feed has them as timestamps, so prefer those when they are there."""
        try:
            now = datetime.now()
            events = self.calendar(now - timedelta(days=365), now + timedelta(days=365))
        except (EclassError, httpx.HTTPError) as exc:
            log.debug("calendar lookup failed: %s", exc)
            return
        by_id = {e["id"]: e for e in events if e["type"] == "assignment" and e.get("course") == course}
        for item in items:
            ev = by_id.get(item.get("id"))
            if ev and (ev.get("end") or ev.get("start")):
                item["deadline_iso"] = ev.get("end") or ev.get("start")

    def exercises(self, course: str) -> list[dict]:
        r = self.get("/modules/exercise/index.php", params={"course": course})
        return parsers.parse_exercises(r.text, self.base_url)

    def documents(self, course: str, path: str = "/") -> list[dict]:
        params = {"course": course}
        if path and path != "/":
            params["openDir"] = path
        r = self.get("/modules/document/index.php", params=params)
        return parsers.parse_documents(r.text, str(r.url))

    def download(self, course: str, path: str, dest_dir: str | Path | None = None) -> dict:
        """Save one document (or a folder as zip) under dest_dir/<course>/."""
        if not self.logged_in:
            self.login()
        dest = Path(dest_dir or self.settings.download_dir).expanduser() / course
        dest.mkdir(parents=True, exist_ok=True)
        params = {"course": course, "download": path}
        with self.http.stream("GET", "/modules/document/index.php", params=params) as r:
            if self._is_login_page(r):
                raise LoginError("session expired while downloading, try again")
            r.raise_for_status()
            disposition = r.headers.get("content-disposition")
            if not disposition and r.headers.get("content-type", "").startswith("text/html"):
                raise EclassError(f"{path} is not a downloadable document")
            name = parsers.filename_from_headers(disposition) or path.rsplit("/", 1)[-1] or "download"
            target = dest / name
            with open(target, "wb") as fh:
                for chunk in r.iter_bytes():
                    fh.write(chunk)
        return {"path": str(target), "bytes": target.stat().st_size, "course": course}

    def messages(self, mailbox: str = "inbox", limit: int = 30, search: str = "") -> list[dict]:
        if mailbox not in ("inbox", "outbox"):
            raise ValueError("mailbox must be 'inbox' or 'outbox'")
        params = {"mbox_type": mailbox, "iDisplayStart": 0, "iDisplayLength": limit, "sSearch": search, "sEcho": 1}
        data = self.ajax("/modules/message/ajax_handler.php", params)
        return parsers.parse_messages(data, f"{self.base_url}/modules/message/", mailbox)

    def message(self, message_id: int, mailbox: str = "inbox") -> dict:
        if mailbox not in ("inbox", "outbox"):
            raise ValueError("mailbox must be 'inbox' or 'outbox'")
        r = self.get(f"/modules/message/{mailbox}.php", params={"mid": message_id})
        info = parsers.parse_message(r.text, str(r.url))
        info.update(id=message_id, url=str(r.url))
        return info
