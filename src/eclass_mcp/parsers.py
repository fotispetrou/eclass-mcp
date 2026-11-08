"""Turn the HTML, XML and DataTables JSON that Open eClass 3.x serves into
plain dicts. Nothing here does I/O, so it is all testable with fixtures."""

from __future__ import annotations

import html as htmllib
import re
import unicodedata
from datetime import date, datetime, timedelta
from urllib.parse import parse_qs, unquote, urljoin, urlparse
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup, NavigableString, Tag


def soup(markup: str | None) -> BeautifulSoup:
    return BeautifulSoup(markup or "", "html.parser")


def text(node) -> str:
    if node is None:
        return ""
    s = node if isinstance(node, str) else node.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", s).strip()


def html_to_text(node) -> str:
    """Plain text for rich content, keeping paragraph and line breaks."""
    if node is None:
        return ""
    if isinstance(node, str):
        node = soup(node)
    for br in node.find_all("br"):
        br.replace_with("\n")
    for block in node.find_all(["p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5"]):
        block.insert_before("\n")
        block.insert_after("\n")
    s = node.get_text()
    s = re.sub(r"[ \t\xa0]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def query_param(url: str | None, name: str) -> str | None:
    if not url:
        return None
    return parse_qs(urlparse(url).query).get(name, [None])[0]


def to_int(value) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def first_text(node: Tag) -> str:
    """Text of the node's own text children, ignoring nested tags. Brackets
    left empty by a skipped child, like the '(<small>3 days left</small>)'
    next to a deadline, are dropped."""
    own = " ".join(c for c in node.children if isinstance(c, NavigableString))
    return text(re.sub(r"\(\s*\)", "", own))


def cells(row) -> list[str]:
    """DataTables rows arrive as a list or as {"0": ..., "1": ..., "DT_RowId": ...}."""
    if isinstance(row, dict):
        return [row[k] for k in sorted((k for k in row if k.isdigit()), key=int)]
    return list(row)


def fold(s: str) -> str:
    """Lower-case without accents, for matching localized labels."""
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


# --- dates -----------------------------------------------------------------

GREEK_MONTHS = {
    "ιαν": 1, "φεβ": 2, "μαρ": 3, "απρ": 4, "μαι": 5, "ιουν": 6,
    "ιουλ": 7, "αυγ": 8, "σεπ": 9, "οκτ": 10, "νοε": 11, "δεκ": 12,
}
ENGLISH_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
RELATIVE_DAYS = {
    "προχθες": -2, "χθες": -1, "σημερα": 0, "αυριο": 1, "μεθαυριο": 2,
    "yesterday": -1, "today": 0, "tomorrow": 1,
}


def parse_date(value: str | None, today: date | None = None) -> str | None:
    """Best effort for the localized dates eClass prints (ICU el/en, short or
    full style). Returns 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DD', or None."""
    if not value:
        return None
    s = fold(value).replace("π.μ.", "am").replace("μ.μ.", "pm")
    today = today or date.today()

    hour = minute = None
    time_m = re.search(r"(\d{1,2}):(\d{2})\s*(am|pm)?", s)
    if time_m:
        hour, minute = int(time_m.group(1)), int(time_m.group(2))
        if time_m.group(3) == "pm" and hour < 12:
            hour += 12
        if time_m.group(3) == "am" and hour == 12:
            hour = 0
        s = s[: time_m.start()] + " " + s[time_m.end():]

    day = None
    for word, offset in RELATIVE_DAYS.items():
        if word in s:
            day = today + timedelta(days=offset)
            break
    if day is None:
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
        if m:
            day = _mkdate(m.group(1), m.group(2), m.group(3))
    if day is None:
        m = re.search(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", s)
        if m:
            day = _mkdate(m.group(3), m.group(2), m.group(1))
    if day is None:
        months = {**GREEK_MONTHS, **ENGLISH_MONTHS}
        month = next((n for k, n in months.items() if k in s), None)
        nums = [int(n) for n in re.findall(r"\b(\d{1,4})\b", s)]
        if month and nums:
            year = next((n for n in nums if n > 31), today.year)
            dom = next((n for n in nums if 1 <= n <= 31), None)
            if dom:
                day = _mkdate(year, month, dom)
    if day is None:
        return None
    if hour is None:
        return day.isoformat()
    return f"{day.isoformat()} {hour:02d}:{minute:02d}"


def _mkdate(year, month, day) -> date | None:
    year, month, day = int(year), int(month), int(day)
    if year < 100:
        year += 2000
    try:
        return date(year, month, day)
    except ValueError:
        return None


def ms_to_iso(ms) -> str | None:
    try:
        return datetime.fromtimestamp(int(ms) / 1000).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OSError):
        return None


# --- login / profile -------------------------------------------------------

def login_error(page: str) -> str | None:
    alert = soup(page).select_one(".alert-warning, .alert-danger")
    return text(alert) or None


def parse_profile(page: str) -> dict:
    """portfolio.php: the profile box has the full name; the same link also
    exists in the menu as 'My profile', so look inside the box first."""
    s = soup(page)
    box = s.select_one("#profile_box") or s
    name = box.select_one("a[href*='display_profile.php']")
    uname = box.select_one(".not_visible.text-center")
    return {"name": text(name), "username": text(uname)}


# --- courses ---------------------------------------------------------------

COURSE_RE = re.compile(r"/courses/([^/?#]+)/?")


def parse_courses_html(page: str, base_url: str) -> list[dict]:
    """my_courses.php: one table row per course."""
    out, seen = [], set()
    for a in soup(page).select("table a[href*='/courses/']"):
        m = COURSE_RE.search(a.get("href", ""))
        if not m or m.group(1) in seen:
            continue
        code = m.group(1)
        seen.add(code)
        td = a.find_parent("td")
        public_code = None
        strong = a.find_parent("strong")
        tail = strong.next_sibling if strong is not None else None
        if isinstance(tail, NavigableString):
            m2 = re.search(r"\(([^()]*)\)", tail)
            if m2:
                public_code = m2.group(1).strip() or None
        small = td.find("small") if td else None
        out.append({
            "code": code,
            "title": text(a),
            "public_code": public_code,
            "teachers": text(small) or None,
            "url": urljoin(base_url, f"/courses/{code}/"),
        })
    return out


def parse_courses_xml(xml: str) -> list[dict]:
    """mcourses.php from the mobile API."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError(f"bad courses xml: {exc}") from exc
    out = []
    for group in root.iter("coursegroup"):
        for c in group.findall("course"):
            out.append({
                "code": c.get("code"),
                "title": c.get("title"),
                "public_code": None,
                "teachers": None,
                "group": group.get("name"),
            })
    return out


def parse_tools_xml(xml: str) -> list[dict]:
    """mtools.php: which modules a course has switched on."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError(f"bad tools xml: {exc}") from exc
    out = []
    for group in root.iter("toolgroup"):
        for t in group.findall("tool"):
            out.append({
                "name": t.get("name"),
                "type": t.get("type"),
                "active": t.get("active") == "true",
                "url": t.get("redirect") or t.get("link"),
                "group": group.get("name"),
            })
    return out


# --- announcements ---------------------------------------------------------

def parse_announcement_rows(data: dict, base_url: str) -> list[dict]:
    """Rows from myannouncements.php or announcements/index.php (DataTables)."""
    out = []
    for row in data.get("aaData", []):
        c = cells(row)
        if not c:
            continue
        s = soup(c[0])
        link = s.select_one(".table_td_header a") or s.find("a")
        body = s.select_one(".table_td_body")
        url = urljoin(base_url, link.get("href", "")) if link else None
        course_label = s.select_one("small")
        when = text(c[1]) if len(c) > 1 else ""
        out.append({
            "id": to_int(body.get("data-id")) if body else to_int(query_param(url, "an_id")),
            "title": text(link),
            "course": query_param(url, "course"),
            "course_title": text(course_label) or None,
            "date": when,
            "date_iso": parse_date(when),
            "body": html_to_text(body),
            "url": url,
        })
    return out


def parse_announcement_page(page: str) -> dict:
    box = soup(page).select_one(".single_announcement")
    if box is None:
        raise ValueError("no announcement on this page")
    when = text(box.select_one(".announcement-date")).strip("- ").strip()
    return {
        "title": text(box.select_one(".announcement-title")),
        "date": when,
        "date_iso": parse_date(when),
        "body": html_to_text(box.select_one(".announcement-main")),
    }


# --- calendar --------------------------------------------------------------

def parse_calendar(data: dict) -> list[dict]:
    """calendar_data.php?from=&to= (milliseconds). Titles and content come
    htmlspecialchars-escaped."""
    out = []
    for ev in data.get("result") or []:
        out.append({
            "id": to_int(ev.get("id")),
            "type": ev.get("event_type"),
            "title": htmllib.unescape(ev.get("title") or ""),
            "course": ev.get("course"),
            "start": ms_to_iso(ev.get("start")),
            "end": ms_to_iso(ev.get("end")),
            "body": html_to_text(htmllib.unescape(ev.get("content") or "")),
            "url": ev.get("url"),
        })
    return out


# --- assignments -----------------------------------------------------------

def parse_assignments(page: str, base_url: str) -> list[dict]:
    """modules/work/index.php?course=X, student view (#assignment_table)."""
    out = []
    table = soup(page).select_one("#assignment_table")
    if table is None:
        return out
    for tr in table.select("tbody tr"):
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue
        link = tds[0].find("a")
        url = urljoin(base_url, link["href"]) if link and link.get("href") else None
        kind = text(tds[0].select_one("small.text-muted")) or None
        deadline = first_text(tds[1])
        note = text(tds[1].find("small")) or None
        grade = text(tds[3]) if len(tds) > 3 else ""
        out.append({
            "id": to_int(query_param(url, "id")),
            "title": text(link) if link else first_text(tds[0]),
            "type": kind,
            "deadline": deadline or None,
            "deadline_iso": parse_date(deadline),
            "status": note,
            "expired": tds[1].select_one(".text-danger") is not None,
            "not_started": "not_visible" in (tr.get("class") or []),
            "submitted": tds[2].select_one(".fa-check-square-o") is not None,
            "grade": grade if grade and grade != "-" else None,
            "url": url,
        })
    return out


# Labels are localized; match on the stem of the Greek or English word.
ASSIGNMENT_FIELDS = [
    ("title", ("τιτλος", "title")),
    ("description", ("περιγραφ", "description")),
    ("comments", ("σχολι", "comment")),
    ("file", ("ρχει", "file")),
    ("max_grade", ("μεγιστ", "max")),
    ("grade_type", ("τυπος βαθμ", "grad")),
    ("start", ("εναρξ", "start")),
    ("deadline", ("προθεσμ", "deadline", "submission")),
    ("submission_kind", ("τυπος εργασ", "assignment type")),
    ("assigned_to", ("αναθεσ", "assign")),
    ("tags", ("ετικετ", "tag")),
]
SUBMISSION_FIELDS = [
    ("status", ("κατασταση", "status")),
    ("grade_comments", ("σχολια βαθμ", "assessor", "grade comment")),
    ("grade", ("βαθμ", "grade")),
    ("submitted_at", ("ημ/νια", "ημερομηνια", "date")),
    ("files", ("ρχει", "file")),
    ("online_text", ("κειμεν", "text")),
    ("comments", ("σχολι", "comment")),
]


def labeled_rows(container: Tag) -> list[tuple[str, Tag]]:
    """Bootstrap rows of the form <div class=row><div class=col-sm-3><strong>Label:</strong></div><div class=col-sm-9>value</div></div>."""
    rows = []
    for row in container.select("div.row"):
        cols = row.find_all("div", recursive=False)
        if len(cols) >= 2 and cols[0].find("strong") is not None:
            rows.append((text(cols[0]).rstrip(":").strip(), cols[1]))
    return rows


def classify(label: str, table) -> str | None:
    f = fold(label)
    for key, stems in table:
        if any(stem in f for stem in stems):
            return key
    return None


def links_in(node: Tag, base_url: str) -> list[dict]:
    return [
        {"name": text(a), "url": urljoin(base_url, a["href"])}
        for a in node.find_all("a", href=True)
        if text(a) and not a["href"].startswith("#")
    ]


def parse_assignment(page: str, page_url: str) -> dict:
    """modules/work/index.php?course=X&id=N for a student: the assignment
    panel plus, if present, the panel describing the student's submission."""
    s = soup(page)
    title_el = s.select_one("#assignment_title")
    info_panel = title_el.find_parent(class_="panel") if title_el else s.select_one(".panel-action-btn-primary")
    if info_panel is None:
        raise ValueError("no assignment on this page")

    result = {
        "title": text(title_el), "description": None, "start": None, "start_iso": None,
        "deadline": None, "deadline_iso": None, "expired": False, "status": None,
        "fields": {}, "files": [], "submission": None, "notes": [],
    }
    for label, value in labeled_rows(info_panel):
        result["fields"][label] = html_to_text(value)
        key = classify(label, ASSIGNMENT_FIELDS)
        if key == "title" and not result["title"]:
            result["title"] = text(value)
        elif key == "description":
            result["description"] = html_to_text(value)
        elif key == "file":
            result["files"] = links_in(value, page_url)
        elif key in ("start", "deadline"):
            raw = first_text(value)
            result[key] = raw or None
            result[key + "_iso"] = parse_date(raw)
            if key == "deadline":
                result["expired"] = value.select_one(".text-danger") is not None
                result["status"] = text(value.find("span")) or None
        elif key in ("max_grade", "grade_type", "submission_kind", "assigned_to", "comments"):
            result[key] = html_to_text(value) or None

    for panel in s.select(".panel-default"):
        rows = labeled_rows(panel)
        if not rows or panel is info_panel:
            continue
        sub = {"fields": {}}
        for label, value in rows:
            sub["fields"][label] = html_to_text(value)
            key = classify(label, SUBMISSION_FIELDS)
            if key == "files":
                sub["files"] = links_in(value, page_url)
            elif key == "submitted_at":
                sub["submitted_at"] = text(value)
                sub["submitted_at_iso"] = parse_date(text(value))
            elif key:
                sub[key] = html_to_text(value) or None
        result["submission"] = sub
        break

    result["notes"] = [text(a) for a in s.select(".alert") if text(a)]
    return result


# --- exercises -------------------------------------------------------------

def parse_exercises(page: str, base_url: str) -> list[dict]:
    """modules/exercise/index.php?course=X, student view (table#ex)."""
    out = []
    table = soup(page).select_one("table#ex")
    if table is None:
        return out
    for tr in table.select("tbody tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        link = tds[0].find("a")
        url = urljoin(base_url, link["href"]) if link and link.get("href") else None
        participated = tds[0].select_one(".fa-check-square-o") is not None
        expired = tds[0].find(style=re.compile("red")) is not None
        # strip the status decorations so only title and description remain
        for junk in tds[0].find_all(["span", "font"]):
            junk.decompose()
        title = text(link) if link else first_text(tds[0])
        title = re.sub(r"\(\s*\)", "", title).strip()
        if link is not None:
            link.decompose()
        description = re.sub(r"\(\s*\)", "", html_to_text(tds[0])).strip()
        if description.startswith(title):
            description = description[len(title):].strip()
        info, start, end = {}, None, None
        for div in tds[1].find_all("div"):
            label, _, value = text(div).partition(":")
            if not value:
                continue
            info[label.strip()] = value.strip()
            stem = fold(label)
            if "εναρξ" in stem or "start" in stem:
                start = parse_date(value)
            elif "ληξ" in stem or "finish" in stem or "end" in stem:
                end = parse_date(value)
        results = tds[2].find("a") if len(tds) > 2 else None
        out.append({
            "id": to_int(query_param(url, "exerciseId")),
            "title": title,
            "description": description or None,
            "info": info,
            "start_iso": start,
            "end_iso": end,
            "expired": expired,
            "not_started": "not_visible" in (tds[0].get("class") or []),
            "participated": participated,
            "url": url,
            "results_url": urljoin(base_url, results["href"]) if results else None,
        })
    return out


# --- documents -------------------------------------------------------------

SIZE_RE = re.compile(r"^\d[\d.,]*\s*(bytes?|[KMG]B)$", re.I)


def parse_documents(page: str, page_url: str) -> list[dict]:
    """modules/document/index.php?course=X[&openDir=...]. Every entry row
    carries a hidden input with its download URL; folders link via openDir."""
    out = []
    for tr in soup(page).find_all("tr"):
        hidden = tr.select_one("input[type=hidden]")
        if hidden is None or not hidden.get("value"):
            continue
        download_url = urljoin(page_url, hidden["value"])
        path = query_param(download_url, "download")
        anchors = [a for a in tr.find_all("a", href=True) if text(a)]
        folder = next((a for a in anchors if "openDir=" in a["href"]), None)
        name_link = folder or (anchors[0] if anchors else None)
        name = text(name_link) if name_link else unquote(path or "").rsplit("/", 1)[-1]
        tds = tr.find_all("td")
        size = next((text(td) for td in tds if SIZE_RE.match(text(td))), None)
        modified = next((d for d in (parse_date(text(td)) for td in tds) if d), None)
        out.append({
            "name": name,
            "type": "folder" if folder else "file",
            "path": path,
            "size": size,
            "modified": modified,
            "url": urljoin(page_url, name_link["href"]) if name_link else download_url,
            "download_url": download_url,
        })
    return out


def filename_from_headers(content_disposition: str | None) -> str | None:
    if not content_disposition:
        return None
    m = re.search(r"filename\*=(?:utf-8|UTF-8)''([^;]+)", content_disposition)
    if m:
        return unquote(m.group(1)).strip()
    m = re.search(r'filename="?([^";]+)"?', content_disposition)
    return m.group(1).strip() if m else None


# --- messages --------------------------------------------------------------

def parse_messages(data: dict, module_url: str, mailbox: str = "inbox") -> list[dict]:
    """modules/message/ajax_handler.php?mbox_type=inbox|outbox."""
    out = []
    for row in data.get("aaData", []):
        c = cells(row)
        if not c:
            continue
        s = soup(c[0])
        link = s.find("a")
        url = urljoin(module_url, link["href"]) if link and link.get("href") else None
        course_link = soup(c[1]).find("a") if len(c) > 1 else None
        people = text(soup(c[2])) if len(c) > 2 else ""
        when = text(soup(c[3])) if len(c) > 3 else ""
        item = {
            "id": to_int(row.get("DT_RowId")) if isinstance(row, dict) else to_int(query_param(url, "mid")),
            "subject": text(link),
            "course": query_param(urljoin(module_url, course_link["href"]), "course") if course_link else None,
            "course_title": text(course_link) or None,
            "date": when,
            "date_iso": parse_date(when),
            "unread": s.find("strong") is not None,
            "attachment": s.select_one(".fa-paperclip") is not None,
            "url": url,
        }
        item["sender" if mailbox == "inbox" else "recipients"] = people
        out.append(item)
    return out


def parse_message(page: str, page_url: str) -> dict:
    s = soup(page)
    area = s.select_one("#msg_area")
    if area is None:
        raise ValueError("no message on this page")
    header = area.select_one(".panel-primary") or area
    values = [v for _, v in labeled_rows(header)]
    course_link = header.select_one("a[href*='course=']")
    # rows are: subject, [course], date, sender, recipients - labels are localized
    if course_link is not None and len(values) > 1:
        del values[1]
    body = area.select_one(".panel-default .panel-body .col-xs-12")
    attachment = area.select_one("a[href*='message_download.php']")
    when = text(values[1]) if len(values) > 1 else ""
    return {
        "subject": text(values[0]) if values else "",
        "course": query_param(urljoin(page_url, course_link["href"]), "course") if course_link else None,
        "course_title": text(course_link) or None,
        "date": when,
        "date_iso": parse_date(when),
        "from": text(values[2]) if len(values) > 2 else "",
        "to": [t for t in (text(x) for x in values[3].find_all(["a", "span"])) if t] if len(values) > 3 else [],
        "body": html_to_text(body),
        "attachment": {"name": text(attachment), "url": urljoin(page_url, attachment["href"])} if attachment else None,
    }
