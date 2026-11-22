from datetime import date
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bot import highway6_closure, ayalon_daily_events, build_report

HIGHWAY = """הודעות חשובות
חסימת כביש 6 ממחלף באקה למחלף ניצני עוז לכיוון דרום
בשל עבודות תשתית בכביש 6, בלילות שבין התאריכים 22/11 ועד 26/11 בין השעות 23:00 ועד 05:00 בבוקר למחרת, ייחסם כביש 6 לתנועה ממחלף באקה למחלף ניצני עוז לכיוון דרום.
הודעות כוזבות בשם כביש 6
דיווחי תנועה"""
AYALON = """שבוע : 22 נובמבר - 28 נובמבר 2026
יום ראשון 22/11/2026
חסימה לסירוגין רמפות כניסה ויציאה מחלף פולג לכביש 2 צפון
יום שני 23/11/2026
אין אירועים מתוכננים
יום שלישי 24/11/2026
אין אירועים מתוכננים"""

class ParserTests(unittest.TestCase):
    def test_6_closure_matching_day(self):
        b, s = highway6_closure(HIGHWAY, date(2026,11,22))
        self.assertTrue(b)
        self.assertIn('באקה',s)

    def test_6_not_stale(self):
        self.assertFalse(highway6_closure(HIGHWAY, date(2026,11,28))[0])

    def test_ayalon_calendar(self):
        ok, events=ayalon_daily_events(AYALON,date(2026,11,22))
        self.assertTrue(ok)
        self.assertIn('פולג',events[0])
        ok, events=ayalon_daily_events(AYALON,date(2026,11,23))
        self.assertTrue(ok)
        self.assertIn('אינו מציג אירועים',events[0])

    def test_no_claim_of_clear_road_when_sites_fail(self):
        report=build_report(date(2026,11,22), {'כביש 6':None,'נתיבי איילון':None,'חוצה ישראל':None})
        self.assertIn('אין מספיק מידע',report)

if __name__ == '__main__':
    unittest.main()
