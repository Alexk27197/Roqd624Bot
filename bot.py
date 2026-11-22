"""RoadWatch Israel: one-way daily Telegram report about *planned* overnight roadworks.

Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to send. No LLM/API key.
If a source cannot be verified, the bot reports that it is unknown, never 'clear'.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

TZ = ZoneInfo("Asia/Jerusalem")
SOURCES = {
    "כביש 6": "https://www.kvish6.co.il/info.aspx",
    "נתיבי איילון": "https://www.ayalonhw.co.il/company-activity/events/",
    "חוצה ישראל": "https://www.transisrael.co.il/ContentPage?id=332",
}
USER_AGENT = "RoadWatch personal roadworks checker/0.1 (source links in every message)"


def fetch_text(url: str) -> str:
    response = requests.get(url, timeout=25, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for element in soup(["script", "style", "noscript"]):
        element.decompose()
    return soup.get_text(separator="\n", strip=True)


def date_in_range(day: date, first_day: int, first_month: int,
                  last_day: int, last_month: int) -> bool:
    # Dates in announcements generally refer to the current calendar year.
    # Handle an end-of-year interval that rolls into January.
    first_year = day.year if first_month <= last_month else (day.year if day.month >= first_month else day.year-1)
    last_year = first_year + int(last_month < first_month)
    try:
        return date(first_year, first_month, first_day) <= day <= date(last_year, last_month, last_day)
    except ValueError:
        return False


def highway6_closure(page: str, day: date) -> tuple[bool, str]:
    # Isolate the current 'important announcements' section; page also has pricing/other notices.
    at = page.rfind("הודעות חשובות")
    section = page[at:] if at >= 0 else page
    end = section.find("דיווחי תנועה")
    if end > 0:
        section = section[:end]
    # Restrict match to closure notice to avoid matching another date elsewhere.
    for m in re.finditer(r"חסימת כביש 6|ייחסם כביש 6", section):
        block = section[max(0, m.start()-100):m.start()+900]
        # Example: בלילות שבין התאריכים 22/11 ועד 26/11
        ranges = re.findall(
            r"(\d{1,2})\s*/\s*(\d{1,2})\s*ועד\s*(?:ל\s*)?(\d{1,2})\s*/\s*(\d{1,2})",
            block,
        )
        # Also support 22-26/11/26
        for a, b, c in re.findall(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*\d{2,4}", block):
            ranges.append((a, c, b, c))
        south = "דרום" in block
        relevant = "באקה" in block and "ניצני עוז" in block
        if south and relevant and any(date_in_range(day, *(int(x) for x in r)) for r in ranges):
            hours = re.search(r"(\d\d:\d\d).{0,35}?(\d\d:\d\d)", block, re.S)
            times = f" ({hours.group(1)}–{hours.group(2)})" if hours else ""
            return True, f"כביש 6 דרום: באקה → ניצני עוז, חסימה מתוכננת{times}."
    return False, "לא זוהתה חסימה מאומתת להלילה בקטע באקה–ניצני עוז; אין בכך אישור שהכביש פתוח."


DAY_NAMES = "ראשון|שני|שלישי|רביעי|חמישי|שישי|שבת"
DAY_HEADING = re.compile(rf"^יום\s+(?:{DAY_NAMES})\s+(\d{{1,2}})/(\d{{1,2}})/(\d{{4}})$")


def ayalon_daily_events(page: str, day: date) -> tuple[bool, list[str]]:
    lines = [x.strip() for x in page.splitlines() if x.strip()]
    start = None
    end = len(lines)
    for i, line in enumerate(lines):
        m = DAY_HEADING.match(line)
        if m:
            item_date = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            if start is not None and i > start:
                end = i
                break
            if item_date == day:
                start = i + 1
    if start is None:
        return False, ["לא אותר יום הבדיקה בלוח האירועים; סטטוס לא מאומת."]
    today_lines = lines[start:end]
    if any("אין אירועים מתוכננים" in x for x in today_lines):
        return True, ["לוח נתיבי איילון אינו מציג אירועים מתוכננים להיום (לא אישור לכביש פתוח)."]
    # Event headlines, as exposed in the site's calendar: 'חסימת רמפת...', etc.
    candidates = []
    for item in today_lines:
        if (re.search(r"חסימ|סגיר|ייחסמ", item) and
                any(key in item for key in ("כביש 2", "איילון", "כביש 20", "מחלף", "רמפת"))):
            if item not in candidates:
                candidates.append(item)
    return True, [f"• {x[:220]}" for x in candidates[:5]] or ["דף האירועים נטען אך לא הצלחתי לחלץ ממנו חסימות בצורה אמינה."]


def transisrael_notes(page: str, day: date) -> list[str]:
    # Extra signal only. Avoid extrapolating that other unmentioned roads are clear.
    notes = []
    if "מטרונית טירת כרמל חיפה מערב" in page:
        section = page.split("מטרונית טירת כרמל חיפה מערב", 1)[1][:700]
        m = re.search(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\.(\d{1,2})\.(\d{4})", section)
        if (m and int(m.group(4)) == day.year and date_in_range(day, int(m.group(1)),int(m.group(3)),int(m.group(2)),int(m.group(3))) and "כביש 4" in section):
            notes.append("כביש 4 באזור סמי עופר–טירת כרמל: צמצום נתיבים; זה אינו ציר כביש 2 המומלץ מחיפה.")
    return notes


def build_report(day: date, pages: dict[str, str | None]) -> str:
    verified6 = pages.get("כביש 6") is not None
    verified_a = pages.get("נתיבי איילון") is not None
    blocked6 = False
    if verified6:
        blocked6, summary6 = highway6_closure(pages["כביש 6"] or "", day)
    else:
        summary6 = "לא ניתן לקרוא את פרסומי כביש 6 — הסטטוס לא ידוע."

    if verified_a:
        parsed_ayalon, ayalon_lines = ayalon_daily_events(pages["נתיבי איילון"] or "", day)
    else:
        parsed_ayalon, ayalon_lines = False, ["לא ניתן לקרוא את לוח נתיבי איילון — הסטטוס לא ידוע."]

    # Flag whole-carriageway closures in the southbound coastal route.
    severe = any(("דרום" in x and any(k in x for k in ("כביש 2", "איילון", "כביש 20")) and
                  any(k in x for k in ("הכביש ייחסם", "חסימה מלאה", "ייסגר כביש")))
                 for x in ayalon_lines)

    if blocked6 and parsed_ayalon and not severe:
        decision = "✅ עדיפות לבחון כביש 2 → איילון → 4: אושרה חסימה בכביש 6 דרום."
    elif blocked6:
        decision = "⚠️ כביש 6 דרום בעייתי; חסר אימות למסלול החלופי."
    else:
        decision = "⚠️ אין מספיק מידע מאומת להמלצה על כביש מסוים."

    notes = transisrael_notes(pages["חוצה ישראל"] or "", day) if pages.get("חוצה ישראל") else []
    info = "\n".join(ayalon_lines[:5])
    extra = "\n".join("• " + x for x in notes)
    return (
        f"🚛 RoadWatch | {day.strftime('%d/%m/%Y')}\n"
        f"קריית אתא → עוטף עזה | עבודות וחסימות לילה בלבד\n\n"
        f"{decision}\n\n"
        f"כביש 6:\n{summary6}\n\n"
        f"כביש 2 / איילון:\n{info}\n"
        + (f"\nהערה מכביש 4:\n{extra}\n" if extra else "")
        + "\nמקורות:\n"
        + "\n".join(SOURCES.values())
        + "\n\n⚠️ דו״ח פרסומים בלבד: לא נבדקו עומסים, תאונות, סגירות פתע או התאמה למידות המשאית. "
          "מקור שלא נמצא בו דיווח אינו אישור לדרך פתוחה. לפני יציאה יש לוודא בשילוט/מוקד הכביש."
    )


def send_message(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID secrets")
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        timeout=25,
    )
    response.raise_for_status()
    if not response.json().get("ok"):
        raise RuntimeError("Telegram rejected message")


def main() -> None:
    today = datetime.now(TZ).date()
    pages = {}
    for label, url in SOURCES.items():
        try:
            pages[label] = fetch_text(url)
            print(f"Fetched {label}: {len(pages[label])} chars", file=sys.stderr)
        except (requests.RequestException, ValueError) as exc:
            pages[label] = None
            print(f"FAILED {label}: {type(exc).__name__}", file=sys.stderr)
    report = build_report(today, pages)
    if "--dry-run" in sys.argv:
        print(report)
    else:
        send_message(report)
        print("Daily notification sent", file=sys.stderr)


if __name__ == "__main__":
    main()
