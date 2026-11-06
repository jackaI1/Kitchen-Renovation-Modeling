import json
from pathlib import Path
import subprocess
import sys


def test_full_study_command_produces_reviewable_reports(tmp_path):
    completed = subprocess.run([sys.executable, '-m', 'renovation', '--output', str(tmp_path)], capture_output=True, text=True, timeout=120)
    assert completed.returncode == 0, completed.stderr
    summary = json.loads((tmp_path/'summary.json').read_text())
    assert set(summary['studies']) == {'electrical', 'mechanical', 'envelope', 'bim', 'sheets'}
    assert (tmp_path/'index.html').is_file()
    assert list(tmp_path.rglob('*.ifc'))
    assert len(list(tmp_path.rglob('*.dxf'))) >= 2
    assert (tmp_path/'sheets/electrical-sheets.html').is_file()


def test_invalid_input_reports_useful_error(tmp_path):
    bad = tmp_path/'bad'
    bad.mkdir()
    (bad/'walls.json').write_text('{}')
    completed = subprocess.run([sys.executable, '-m', 'renovation', '--input', str(bad), '--output', str(tmp_path/'out')], capture_output=True,text=True)
    assert completed.returncode != 0
    assert 'error:' in completed.stderr.lower()
