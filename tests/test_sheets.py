import math
import pytest
import sympy as sp
from pint.errors import DimensionalityError


def test_voltage_drop_sheet_equation_substitution_and_units():
    from renovation.sheets import calculate, Q
    i, r, l = sp.symbols('I R L')
    result = calculate('loop drop', 2*i*r*l, {'I': Q('10 A'), 'R': Q('2 ohm/km'), 'L': Q('30 m')}, 'V')
    assert result['result_magnitude'] == pytest.approx(1.2)
    assert result['expression'] == '2*I*L*R'
    assert result['substitution_latex']
    assert result['inputs']['L'] == '30 meter'


def test_wrong_dimensions_fail_before_export():
    from renovation.sheets import calculate, Q
    i,r = sp.symbols('I R')
    with pytest.raises(DimensionalityError):
        calculate('bad', i*r, {'I': Q('10 m'), 'R': Q('2 ohm')}, 'V')


@pytest.mark.parametrize('bad', ['nan A', '-10 A', 'inf A'])
def test_electrical_sheet_rejects_nonphysical_values(bad):
    from renovation.sheets import electrical_sheets, Q
    with pytest.raises(ValueError):
        electrical_sheets(current=Q(bad))


def test_expected_transformer_and_fault_hand_values():
    from renovation.sheets import electrical_sheets
    sheets = {s['name']: s for s in electrical_sheets()}
    assert sheets['Transformer rated current']['result_magnitude'] == pytest.approx(75000/(math.sqrt(3)*208))
    assert sheets['Transformer loading']['result_magnitude'] == pytest.approx(40)
    assert sheets['Transformer impedance']['result_magnitude'] == pytest.approx(.05*208**2/75000)
    assert sheets['Available three-phase fault current']['result_magnitude'] == pytest.approx(208/(math.sqrt(3)*(.05*208**2/75000)))
    assert sheets['Required conductor ampacity']['result_magnitude'] == pytest.approx(25)


def test_html_report_and_notebooks_are_real(tmp_path):
    from renovation.sheets import run
    result = run({}, tmp_path)
    assert len(result['sheets']) >= 6
    html = (tmp_path/'electrical-sheets.html').read_text()
    assert 'Assumptions' in html and 'References' in html and 'Substitution' in html
    import nbformat
    from pathlib import Path
    notebooks = list(Path('notebooks').glob('*.ipynb'))
    assert len(notebooks) >= 2
    for path in notebooks:
        nbformat.validate(nbformat.read(path, as_version=4))


def test_unit_checked_cable_selection_uses_real_table():
    from renovation.sheets import cable_selection, Q
    result = cable_selection(Q('20 A'), Q('30 A'))
    assert result['required_ampacity_a'] == pytest.approx(25)
    assert result['selected']['awg'] == '10'
    with pytest.raises(DimensionalityError):
        cable_selection(Q('20 m'), Q('30 A'))
