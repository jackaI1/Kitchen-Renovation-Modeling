import tempfile
import unittest
from pathlib import Path
from datetime import date
from xml.etree import ElementTree as ET
from openpyxl import load_workbook
from tracker.core import Task, schedule
from tracker.export import workbook, project_xml, gantt

class ExportTests(unittest.TestCase):
    def test_files_contain_formulas_and_dependencies(self):
        tasks = [Task('A','Design & plan',2,[],100,50,.5), Task('B','Build',1,['A'],200,0,0)]
        timing = schedule(tasks)
        with tempfile.TemporaryDirectory() as d:
            d = Path(d); workbook(tasks,timing,d/'report.xlsx'); project_xml(tasks,timing,date(2026,11,9),d/'schedule.xml'); gantt(tasks,timing,d/'gantt.svg')
            ws = load_workbook(d/'report.xlsx', data_only=False).active
            self.assertEqual(ws['G2'].value, '=F2-D2')
            self.assertEqual(ws['H2'].value, '=IF(F2=0,"",C2*D2/F2)')
            root = ET.parse(d/'schedule.xml').getroot(); ns = {'p':'http://schemas.microsoft.com/project'}
            self.assertEqual(root.find('.//p:PredecessorUID',ns).text, '1')
            self.assertIn('Design &amp; plan', (d/'gantt.svg').read_text())
