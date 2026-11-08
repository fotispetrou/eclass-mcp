"""Fixtures below mirror the markup Open eClass 3.16 emits (see the PHP
templates under modules/ and main/ in gunet/openeclass)."""

from datetime import date

from eclass_mcp import parsers

BASE = "https://eclass.example.gr"


def test_parse_date_formats():
    today = date(2026, 11, 8)
    assert parsers.parse_date("8/11/26, 10:15 π.μ.", today) == "2026-11-08 10:15"
    assert parsers.parse_date("8/11/26, 10:15 μ.μ.", today) == "2026-11-08 22:15"
    assert parsers.parse_date("Κυριακή 8 Νοεμβρίου 2026 - 10:15 π.μ.", today) == "2026-11-08 10:15"
    assert parsers.parse_date("Sunday, November 8, 2026 at 10:15 PM", today) == "2026-11-08 22:15"
    assert parsers.parse_date("αύριο - 11:59 μ.μ.", today) == "2026-11-09 23:59"
    assert parsers.parse_date("yesterday, 9:00 AM", today) == "2026-11-07 09:00"
    assert parsers.parse_date("15-12-2026 23:59", today) == "2026-12-15 23:59"
    assert parsers.parse_date("2026-12-15", today) == "2026-12-15"
    assert parsers.parse_date("Χωρίς προθεσμία", today) is None
    assert parsers.parse_date("", today) is None


COURSES_HTML = """
<table class='table-default'><tbody>
<tr class=''>
  <td><strong><a href='https://eclass.example.gr/courses/DS101/'>Δίκτυα Υπολογιστών</a></strong> (ΨΣ-101)
      <div><small>Α. Παπαδόπουλος</small></div></td>
  <td class='text-center'><a href='course_favorite.php?course=DS101&amp;fav=1'>fav</a></td>
</tr>
<tr class='not_visible'>
  <td><strong><a href='https://eclass.example.gr/courses/DS205/'>Βάσεις Δεδομένων</a></strong> (DS205)
      <div><small></small></div></td>
  <td></td>
</tr>
</tbody></table>
"""


def test_parse_courses_html():
    courses = parsers.parse_courses_html(COURSES_HTML, BASE)
    assert [c["code"] for c in courses] == ["DS101", "DS205"]
    assert courses[0]["title"] == "Δίκτυα Υπολογιστών"
    assert courses[0]["public_code"] == "ΨΣ-101"
    assert courses[0]["teachers"] == "Α. Παπαδόπουλος"
    assert courses[0]["url"] == f"{BASE}/courses/DS101/"
    assert courses[1]["teachers"] is None


def test_parse_courses_xml():
    xml = """<?xml version="1.0" encoding="utf-8"?>
<courses><coursegroup name="Μαθήματα που παρακολουθώ">
<course code="DS101" title="Δίκτυα Υπολογιστών - ΨΣ-101" description=""/>
</coursegroup></courses>"""
    courses = parsers.parse_courses_xml(xml)
    assert courses == [{"code": "DS101", "title": "Δίκτυα Υπολογιστών - ΨΣ-101", "public_code": None,
                        "teachers": None, "group": "Μαθήματα που παρακολουθώ"}]


def test_parse_tools_xml():
    xml = """<tools><toolgroup name="Ενεργά εργαλεία">
<tool name="Έγγραφα" link="https://x/modules/mobile/mlogin.php?redirect=..." redirect="https://x/modules/document/?course=DS101" type="docs" active="true"/>
<tool name="Εργασίες" link="" redirect="https://x/modules/work/?course=DS101" type="assignment" active="false"/>
</toolgroup></tools>"""
    tools = parsers.parse_tools_xml(xml)
    assert tools[0]["name"] == "Έγγραφα" and tools[0]["active"] is True
    assert tools[1]["active"] is False
    assert tools[0]["url"].endswith("/modules/document/?course=DS101")


ANNOUNCEMENT_ROW = """<div class='table_td'>
    <div class='table_td_header clearfix'>
        <a href='/modules/announcements/?course=DS101&an_id=4821'>Αναβολή εργαστηρίου</a>
    </div>
    <small class='text-grey'>Δίκτυα Υπολογιστών</small>
    <div class='table_td_body' data-id='4821'><p>Το εργαστήριο της Τρίτης <b>αναβάλλεται</b>.</p><p>Νέα ημερομηνία θα ανακοινωθεί.</p></div>
    </div>"""


def test_parse_announcement_rows_list_and_dict_rows():
    data = {"aaData": [[ANNOUNCEMENT_ROW, "Δευτέρα 3 Νοεμβρίου 2026 - 9:05 π.μ."],
                       {"0": ANNOUNCEMENT_ROW, "1": "3/11/26, 9:05 π.μ."}]}
    items = parsers.parse_announcement_rows(data, BASE)
    assert len(items) == 2
    first = items[0]
    assert first["id"] == 4821
    assert first["title"] == "Αναβολή εργαστηρίου"
    assert first["course"] == "DS101"
    assert first["course_title"] == "Δίκτυα Υπολογιστών"
    assert first["date_iso"] == "2026-11-03 09:05"
    assert first["body"] == "Το εργαστήριο της Τρίτης αναβάλλεται.\n\nΝέα ημερομηνία θα ανακοινωθεί."
    assert first["url"] == f"{BASE}/modules/announcements/?course=DS101&an_id=4821"
    assert items[1]["date_iso"] == "2026-11-03 09:05"


def test_parse_announcement_page():
    page = """<div class='single_announcement'>
        <div class='announcement-title'> Αναβολή εργαστηρίου </div>
        <span class='announcement-date'> - Δευτέρα 3 Νοεμβρίου 2026 - 9:05 π.μ. - </span>
        <div class='announcement-main'><p>Κείμενο<br>δεύτερη γραμμή</p></div></div>"""
    info = parsers.parse_announcement_page(page)
    assert info["title"] == "Αναβολή εργαστηρίου"
    assert info["date_iso"] == "2026-11-03 09:05"
    assert info["body"] == "Κείμενο\nδεύτερη γραμμή"


def test_parse_calendar():
    data = {"success": 1, "result": [{
        "id": "77", "title": "Δίκτυα Υπολογιστών: Εργασία 2", "start": 1765836000000, "end": 1765836000000,
        "content": "Παραδοτέο σε &lt;b&gt;pdf&lt;/b&gt;\n(deadline: 2026-12-15 23:59:00)",
        "event_type": "assignment", "event_group": "deadline", "course": "DS101",
        "url": "https://x/modules/work/index.php?id=77&course=DS101"}], "cid": None}
    events = parsers.parse_calendar(data)
    assert events[0]["id"] == 77
    assert events[0]["type"] == "assignment"
    assert events[0]["course"] == "DS101"
    assert events[0]["start"] == parsers.ms_to_iso(1765836000000)
    assert events[0]["body"].startswith("Παραδοτέο σε pdf")


ASSIGNMENTS_HTML = """
<table id='assignment_table' class='table-default'><thead><tr class='list-header'><th>Τίτλος</th><th>Προθεσμία</th><th>Υποβλήθηκε</th><th>Βαθμός</th></tr></thead>
<tbody>
<tr class=''>
  <td><a href='/modules/work/index.php?course=DS101&amp;id=77'>Εργασία 2</a>
      <br><small class='text-muted'>Ατομική εργασία</small></td>
  <td class='text-center' data-sort='1'>Τρίτη 15 Δεκεμβρίου 2026 - 11:59 μ.μ.<br>(<small>Απομένουν 5 ημέρες 3 ώρες</small>)</td>
  <td class='text-center'><i class='fa fa-square-o'></i><br></td>
  <td class='text-center'></td>
</tr>
<tr class=''>
  <td><a href='/modules/work/index.php?course=DS101&amp;id=70'>Εργασία 1</a>
      <br><small class='text-muted'>Ατομική εργασία</small></td>
  <td class='text-center' data-sort='2'>Παρασκευή 10 Οκτωβρίου 2026 - 11:59 μ.μ.<br>(<small><span class='text-danger'>έχει λήξει</span></small>)</td>
  <td class='text-center'><i class='fa fa-check-square-o'></i><br></td>
  <td class='text-center'><div>8.5</div></td>
</tr>
<tr class='not_visible'>
  <td>Εργασία 3</td>
  <td class='text-center' data-sort='3'><small><span class='text-warning'>Θα ξεκινήσει: 1/2/27, 8:00 π.μ.</span></small></td>
  <td class='text-center'><i class='fa fa-square-o'></i><br></td>
  <td class='text-center'></td>
</tr>
</tbody></table>"""


def test_parse_assignments():
    items = parsers.parse_assignments(ASSIGNMENTS_HTML, BASE)
    assert [a["id"] for a in items] == [77, 70, None]
    a2, a1, a3 = items
    assert a2["title"] == "Εργασία 2"
    assert a2["type"] == "Ατομική εργασία"
    assert a2["deadline_iso"] == "2026-12-15 23:59"
    assert a2["status"] == "Απομένουν 5 ημέρες 3 ώρες"
    assert a2["submitted"] is False and a2["expired"] is False
    assert a2["url"] == f"{BASE}/modules/work/index.php?course=DS101&id=77"
    assert a1["expired"] is True and a1["submitted"] is True and a1["grade"] == "8.5"
    assert a3["title"] == "Εργασία 3" and a3["not_started"] is True and a3["deadline"] is None


def row(label, value):
    return (f"<div class='row margin-bottom-fat'><div class='col-sm-3'><strong>{label}:</strong></div>"
            f"<div class='col-sm-9'>{value}</div></div>")


ASSIGNMENT_HTML = (
    "<div class='alert alert-warning'>Η προθεσμία έχει παρέλθει, επιτρέπεται εκπρόθεσμη υποβολή.</div>"
    "<div class='panel panel-action-btn-primary'><div class='panel-heading'>Στοιχεία εργασίας</div><div class='panel-body'>"
    "<div class='row margin-bottom-fat'><div class='col-sm-3'><strong>Τίτλος:</strong></div><div class='col-sm-9' id='assignment_title'>Εργασία 2</div></div>"
    + row("Περιγραφή", "<p>Υλοποιήστε τον αλγόριθμο.</p><p>Παράδοση σε <b>pdf</b>.</p>")
    + row("Αρχείο", "<a href='/modules/work/index.php?course=DS101&amp;get=12'>ekfonisi.pdf</a>")
    + row("Μέγιστη βαθμολογία", "10")
    + row("Τύπος Βαθμολογίας", "Αριθμός")
    + row("Ημερομηνία έναρξης", "Δευτέρα 1 Δεκεμβρίου 2026 - 8:00 π.μ.")
    + row("Προθεσμία υποβολής", "Τρίτη 15 Δεκεμβρίου 2026 - 11:59 μ.μ.<br><span class='text-danger'>(η προθεσμία έχει λήξει)</span>")
    + row("Τύπος εργασίας", "Ατομική εργασία")
    + row("Ανάθεση σε", "Σε όλους τους φοιτητές")
    + "</div></div>"
    "<div class='panel panel-default'><div class='panel-heading list-header'><h3 class='panel-title'>Στοιχεία υποβολής εργασίας</h3></div><div class='panel-body'>"
    + row("Κατάσταση υποβολής εργασίας", "Η εργασία αυτή έχει ήδη υποβληθεί και βαθμολογηθεί.")
    + row("Βαθμός", "8.5")
    + row("Σχόλια βαθμολογητή", "Καλή δουλειά")
    + row("Ημ/νία αποστολής", "14/12/26, 10:00 μ.μ.")
    + row("Όνομα αρχείου", "<a href='/modules/work/index.php?course=DS101&amp;get=99'>ergasia2.pdf</a>")
    + row("Σχόλια", "Συνημμένα και ο κώδικας")
    + "</div></div>"
)


def test_parse_assignment():
    info = parsers.parse_assignment(ASSIGNMENT_HTML, f"{BASE}/modules/work/index.php?course=DS101&id=77")
    assert info["title"] == "Εργασία 2"
    assert info["description"] == "Υλοποιήστε τον αλγόριθμο.\n\nΠαράδοση σε pdf."
    assert info["files"] == [{"name": "ekfonisi.pdf", "url": f"{BASE}/modules/work/index.php?course=DS101&get=12"}]
    assert info["max_grade"] == "10"
    assert info["grade_type"] == "Αριθμός"
    assert info["start_iso"] == "2026-12-01 08:00"
    assert info["deadline_iso"] == "2026-12-15 23:59"
    assert info["expired"] is True
    assert info["submission_kind"] == "Ατομική εργασία"
    assert info["assigned_to"] == "Σε όλους τους φοιτητές"
    assert info["notes"] == ["Η προθεσμία έχει παρέλθει, επιτρέπεται εκπρόθεσμη υποβολή."]
    sub = info["submission"]
    assert sub["status"].startswith("Η εργασία αυτή έχει ήδη υποβληθεί")
    assert sub["grade"] == "8.5"
    assert sub["grade_comments"] == "Καλή δουλειά"
    assert sub["submitted_at_iso"] == "2026-12-14 22:00"
    assert sub["files"] == [{"name": "ergasia2.pdf", "url": f"{BASE}/modules/work/index.php?course=DS101&get=99"}]
    assert sub["comments"] == "Συνημμένα και ο κώδικας"
    # the raw labels survive for anything the keyword matching misses
    assert info["fields"]["Τύπος Βαθμολογίας"] == "Αριθμός"


def test_parse_assignment_english_labels():
    page = ("<div class='panel panel-action-btn-primary'><div class='panel-body'>"
            "<div class='row margin-bottom-fat'><div class='col-sm-3'><strong>Title:</strong></div><div class='col-sm-9' id='assignment_title'>Essay</div></div>"
            + row("Description", "Write 2000 words")
            + row("Max grade", "100")
            + row("Grade Type", "Number")
            + row("Start date", "Monday, December 1, 2026 at 8:00 AM")
            + row("Submission deadline", "Tuesday, December 15, 2026 at 11:59 PM<br><span>(5 days left)</span>")
            + row("Assignment type", "Individual submissions")
            + row("Assign to", "To All students")
            + "</div></div>")
    info = parsers.parse_assignment(page, BASE)
    assert info["description"] == "Write 2000 words"
    assert info["max_grade"] == "100" and info["grade_type"] == "Number"
    assert info["start_iso"] == "2026-12-01 08:00" and info["deadline_iso"] == "2026-12-15 23:59"
    assert info["expired"] is False and info["status"] == "(5 days left)"
    assert info["submission_kind"] == "Individual submissions"
    assert info["assigned_to"] == "To All students"
    assert info["submission"] is None


EXERCISES_HTML = """
<table id='ex' class='table-default'><thead><tr class='list-header'><th>Όνομα</th><th>Πληροφορίες</th><th>Αποτελέσματα</th></tr></thead><tbody>
<tr>
  <td><a class='ex_settings ' href='exercise_submit.php?course=DS101&amp;exerciseId=12'>Quiz 1</a>&nbsp; <span class='fa fa-check-square-o'></span><p>Ερωτήσεις πολλαπλής επιλογής</p></td>
  <td data-sort='2026-11-01 08:00'><small><div style='color:green;'>Έναρξη: 1/11/26, 8:00 π.μ.</div><div style='color:red;'>Λήξη: 30/11/26, 11:59 μ.μ.</div><div>Διάρκεια: 30 λεπτά</div><div>Επιτρεπόμενες προσπάθειες: 2</div></small></td>
  <td class='text-center'><a href='results.php?course=DS101&amp;exerciseId=abc'>Προβολή</a></td>
</tr>
<tr>
  <td>Quiz 0&nbsp;&nbsp;(<span style='color:red;'>έχει λήξει</span>)</td>
  <td data-sort=''><small></small></td>
  <td class='text-center''>&dash;</td>
</tr>
</tbody></table>"""


def test_parse_exercises():
    items = parsers.parse_exercises(EXERCISES_HTML, BASE)
    assert items[0]["id"] == 12
    assert items[0]["title"] == "Quiz 1"
    assert items[0]["participated"] is True
    assert items[0]["description"] == "Ερωτήσεις πολλαπλής επιλογής"
    assert items[0]["info"]["Λήξη"] == "30/11/26, 11:59 μ.μ."
    assert items[0]["info"]["Επιτρεπόμενες προσπάθειες"] == "2"
    assert items[0]["results_url"] == f"{BASE}/results.php?course=DS101&exerciseId=abc"
    assert items[1]["title"] == "Quiz 0" and items[1]["expired"] is True and items[1]["url"] is None


DOCUMENTS_HTML = """
<table class='table-default'><tbody>
<tr class='visible'>
  <td class='text-center checkbox_td hide'><input type='checkbox'></td>
  <td class='text-center'><span class='fa fa-folder'></span></td>
  <td><input type='hidden' value='index.php?course=DS101&amp;download=/5f8938d7bhfV'><a href='index.php?course=DS101&amp;openDir=/5f8938d7bhfV'>Διαλέξεις</a> </td>
  <td class='text-center'>&nbsp;</td>
  <td class='text-center'>12-10-2026</td>
</tr>
<tr class='visible'>
  <td class='text-center checkbox_td hide'><input type='checkbox'></td>
  <td class='text-center'><span class='fa fa-file-pdf-o'></span></td>
  <td><input type='hidden' value='index.php?course=DS101&amp;download=/5f8938d7bhfV/a1b2c3'><a href='file.php?course=DS101&amp;file=/5f8938d7bhfV/a1b2c3' target='_blank'>Lecture 01.pdf</a> <span class='label label-success pull-right'>Νέο</span></td>
  <td class='text-center'>1.2 MB</td>
  <td class='text-center'>13-10-2026</td>
</tr>
</tbody></table>"""


def test_parse_documents():
    page_url = f"{BASE}/modules/document/index.php?course=DS101"
    items = parsers.parse_documents(DOCUMENTS_HTML, page_url)
    assert len(items) == 2
    folder, pdf = items
    assert folder["type"] == "folder" and folder["name"] == "Διαλέξεις"
    assert folder["path"] == "/5f8938d7bhfV"
    assert folder["url"] == f"{BASE}/modules/document/index.php?course=DS101&openDir=/5f8938d7bhfV"
    assert pdf["type"] == "file" and pdf["name"] == "Lecture 01.pdf"
    assert pdf["path"] == "/5f8938d7bhfV/a1b2c3"
    assert pdf["size"] == "1.2 MB"
    assert pdf["modified"] == "2026-10-13"
    assert pdf["download_url"] == f"{BASE}/modules/document/index.php?course=DS101&download=/5f8938d7bhfV/a1b2c3"


def test_filename_from_headers():
    assert parsers.filename_from_headers('attachment; filename="notes.pdf"') == "notes.pdf"
    assert parsers.filename_from_headers("attachment; filename*=UTF-8''%CE%A3%CE%B7%CE%BC.pdf") == "Σημ.pdf"
    assert parsers.filename_from_headers(None) is None


MESSAGE_ROW = {
    "DT_RowId": 311,
    "0": "<i class='fa fa-envelope' title='Βαθμολογία'></i>&nbsp;&nbsp;<strong><a href='inbox.php?mid=311'>Βαθμολογία</a></strong>&nbsp;&nbsp;&#124;&nbsp;&nbsp;<a class='outtabs' href='message_download.php?course=DS101&amp;id=311'><span class='fa fa-paperclip'></span></a>",
    "1": "<strong><a class=\"outtabs\" href=\"index.php?course=DS101\">Δίκτυα Υπολογιστών</a></strong>",
    "2": "<a href='../../main/profile/display_profile.php?id=5' class='outtabs'>Α. Παπαδόπουλος</a>",
    "3": "7/11/26, 2:30 μ.μ.",
    "4": "<a href='javascript:void(0)' class='delete_in' data-id='311'>x</a>",
}


def test_parse_messages():
    items = parsers.parse_messages({"aaData": [MESSAGE_ROW]}, f"{BASE}/modules/message/", "inbox")
    m = items[0]
    assert m["id"] == 311
    assert m["subject"] == "Βαθμολογία"
    assert m["course"] == "DS101" and m["course_title"] == "Δίκτυα Υπολογιστών"
    assert m["sender"] == "Α. Παπαδόπουλος"
    assert m["date_iso"] == "2026-11-07 14:30"
    assert m["unread"] is True and m["attachment"] is True
    assert m["url"] == f"{BASE}/modules/message/inbox.php?mid=311"


MESSAGE_PAGE = """<div id='msg_area'>
  <div class='panel panel-primary'><div class='panel-body'>
    <div class='row margin-bottom-thin'><div class='col-sm-2'><strong>Θέμα:</strong></div><div class='col-sm-10'>Βαθμολογία</div></div>
    <div class='row margin-bottom-thin'><div class='col-sm-2'><strong>Μάθημα:</strong></div><div class='col-sm-10'><a class="outtabs" href="index.php?course=DS101">Δίκτυα Υπολογιστών</a></div></div>
    <div class='row margin-bottom-thin'><div class='col-sm-2'><strong>Ημερομηνία:</strong></div><div class='col-sm-10'>7/11/26, 2:30 μ.μ.</div></div>
    <div class='row margin-bottom-thin'><div class='col-sm-2'><strong>Αποστολέας:</strong></div><div class='col-sm-10'><a href='x' class='outtabs'>Α. Παπαδόπουλος</a></div></div>
    <div class='row margin-bottom-thin'><div class='col-sm-2'><strong>Παραλήπτες:</strong></div><div class='col-sm-10'><a href='y' class='outtabs'>Γ. Παπαδόπουλος</a><br/></div></div>
  </div></div>
  <div class='panel panel-default'><div class='panel-heading'>Μήνυμα</div><div class='panel-body'>
    <div class='row margin-bottom-thin'><div class='col-xs-12'><p>Η βαθμολογία αναρτήθηκε.</p></div></div>
    <hr><div class='row margin-top-thin'><div class='col-sm-2'>Συνημμένο</div><div class='col-sm-10'><a href='message_download.php?course=DS101&amp;id=311' class='outtabs'>grades.pdf</a></div></div>
  </div></div>
</div>"""


def test_parse_message():
    info = parsers.parse_message(MESSAGE_PAGE, f"{BASE}/modules/message/inbox.php?mid=311")
    assert info["subject"] == "Βαθμολογία"
    assert info["course"] == "DS101"
    assert info["date_iso"] == "2026-11-07 14:30"
    assert info["from"] == "Α. Παπαδόπουλος"
    assert info["to"] == ["Γ. Παπαδόπουλος"]
    assert info["body"] == "Η βαθμολογία αναρτήθηκε."
    assert info["attachment"] == {"name": "grades.pdf", "url": f"{BASE}/modules/message/message_download.php?course=DS101&id=311"}


def test_login_error_and_profile():
    assert parsers.login_error("<div class='alert alert-warning' role='alert'>Λάθος όνομα χρήστη</div>") == "Λάθος όνομα χρήστη"
    assert parsers.login_error("<p>ok</p>") is None
    page = "<div class='not_visible text-center'>student</div><a href='/main/profile/display_profile.php'>Γιώργος Παπαδόπουλος</a>"
    assert parsers.parse_profile(page) == {"name": "Γιώργος Παπαδόπουλος", "username": "student"}
