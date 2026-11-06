"""Readable symbolic electrical sheets with actual pint dimensional evaluation."""
from functools import reduce
from html import escape
import json
import math
import operator
from pathlib import Path

import pint
import sympy as sp

ureg = pint.UnitRegistry()
Q = ureg.Quantity


def _evaluate(expression, values):
    if isinstance(expression, sp.Symbol):
        return values[str(expression)]
    if expression.is_Number:
        return float(expression)
    args = [_evaluate(arg, values) for arg in expression.args]
    if isinstance(expression, sp.Add):
        return reduce(operator.add, args)
    if isinstance(expression, sp.Mul):
        return reduce(operator.mul, args)
    if isinstance(expression, sp.Pow):
        return args[0] ** args[1]
    raise ValueError('supported sheet operations are addition, multiplication and powers')


def calculate(name, expression, inputs, result_unit):
    """Evaluate the symbolic expression twice: SI scalar substitution and units.

    Every variable must be a pint quantity. The symbolic scalar result must match
    the unit-evaluated result in SI base units before any report can be written.
    """
    symbols = {str(s): s for s in expression.free_symbols}
    if set(symbols) != set(inputs):
        raise ValueError('provide exactly one quantity for every expression variable')
    base = {}
    for key, value in inputs.items():
        if not isinstance(value, pint.Quantity):
            raise ValueError(f'{key} requires a quantity with units')
        value = value.to_base_units()
        if not math.isfinite(value.magnitude):
            raise ValueError('sheet inputs must be finite scalars')
        base[key] = value
    checked = _evaluate(expression, base)
    if not isinstance(checked, pint.Quantity):
        checked = Q(checked, '')
    result = checked.to(result_unit)  # Raises DimensionalityError before exporting.
    numeric = float(expression.subs({symbols[k]: v.magnitude for k, v in base.items()}))
    if not math.isfinite(numeric) or not math.isclose(numeric, checked.to_base_units().magnitude, rel_tol=1e-10, abs_tol=1e-10):
        raise ValueError('symbolic substitution and unit calculation disagree')
    substitution = expression.subs({symbols[k]: sp.UnevaluatedExpr(sp.Float(v.magnitude)) for k,v in base.items()})
    return {'name': name, 'expression': str(expression), 'equation_latex': sp.latex(expression),
            'equation_text': sp.pretty(expression, use_unicode=True),
            'substitution_latex': sp.latex(substitution),
            'substitution_text': sp.pretty(substitution, use_unicode=True),
            'inputs': {k: str(v) for k,v in inputs.items()},
            'si_inputs': {k: str(v) for k,v in base.items()},
            'result_magnitude': float(result.magnitude), 'result_unit': str(result.units),
            'dimensional_check': 'passed'}


def electrical_sheets(current=None):
    """One transparent worked case; quantities can also be used with calculate()."""
    current = Q('20 A') if current is None else current
    if not math.isfinite(current.to('A').magnitude) or current.to('A').magnitude <= 0:
        raise ValueError('current must be finite and positive')
    S, V, I, R, X, L, pf, z, load = sp.symbols('S V I R X L pf z load')
    return [
        calculate('Required conductor ampacity', sp.Rational(5,4)*I, {'I':current}, 'A'),
        calculate('Single-phase voltage drop', 2*I*L*(R*pf+X*sp.sqrt(1-pf**2)),
                  {'I':current,'L':Q('25 m'),'R':Q('1.26 ohm/km'),'X':Q('0.08 ohm/km'),'pf':Q('.9')}, 'V'),
        calculate('Transformer rated current', S/(sp.sqrt(3)*V), {'S':Q('75 kVA'),'V':Q('208 V')}, 'A'),
        calculate('Transformer loading', 100*load/S, {'load':Q('30 kVA'),'S':Q('75 kVA')}, ''),
        calculate('Transformer impedance', z*V**2/S, {'z':Q('.05'),'V':Q('208 V'),'S':Q('75 kVA')}, 'ohm'),
        calculate('Available three-phase fault current', V/(sp.sqrt(3)*z),
                  {'V':Q('208 V'),'z':Q(.05*208**2/75000,'ohm')}, 'A'),
    ]



def cable_selection(current, breaker):
    """Unit-check a continuous branch before using the published ampacity table."""
    from renovation.electrical import select_conductor
    amp = current.to('A').magnitude
    device = breaker.to('A').magnitude
    if not all(math.isfinite(v) and v > 0 for v in (amp, device)):
        raise ValueError('current and breaker must be finite positive amperes')
    i = sp.Symbol('I')
    sheet = calculate('Required conductor ampacity', sp.Rational(5,4)*i, {'I':current}, 'A')
    required = sheet['result_magnitude']
    return {'required_ampacity_a': required, 'selected': select_conductor(required, device),
            'warnings': ['device_overload'] if required > device else [], 'sheet':sheet}


def run(data, output_dir):
    """Export six auditable equations as standalone HTML and JSON."""
    sheets = electrical_sheets()
    selection = cable_selection(Q('20 A'), Q('30 A'))
    assumptions = [
        'Synthetic 208 V balanced three-phase 75 kVA transformer, 5% impedance; infinite upstream source; no motor contribution.',
        'Fault sheet is at transformer terminals; the panel study separately adds complex cable impedances.',
        'Continuous 20 A branch requires 1.25 times load current; final wire selection also checks the published bounded ampacity table and device rating in the panel study.',
        'Voltage-drop sheet: 25 m one-way single-phase cable, R=1.26 and X=0.08 ohm/km, power factor=.9; chosen cable impedance is an explicit study assumption.',
        'Loading result is percent; the dimensionless scalar is multiplied by 100 explicitly. SI substitutions use base units; input units appear beside them.',
        'Preliminary educational study. Ground faults, arc flash, selectivity, product approval and code compliance require separate engineering review.'
    ]
    refs = {
        'Panel calculation notes': 'https://github.com/jackaI1/Kitchen-Renovation-Modeling/blob/main/docs/electrical.md',
        'Published copper ampacity table (Southwire guide, PDF page 30)': 'https://www.southwire.com/medias/sys_master/installation-manuals/installation-manuals/hca/hff/8887676010526/MC-Installation-Guide-Southwire.pdf',
        'Schneider Electric radial three-phase fault equations': 'https://www.electrical-installation.org/enwiki/3-phase_short-circuit_current_(Isc)_at_any_point_within_a_LV_installation',
        'Schneider Electric voltage-drop equations': 'https://www.electrical-installation.org/enwiki/Calculation_of_voltage_drop_in_steady_load_conditions',
        'Pint quantity and conversion documentation': 'https://pint.readthedocs.io/en/stable/getting/tutorial.html',
        'SymPy substitution documentation': 'https://docs.sympy.org/latest/tutorials/intro-tutorial/basic_operations.html',
    }
    sections = []
    for sheet in sheets:
        inputs = ''.join(f'<tr><td>{escape(k)}</td><td>{escape(v)}</td><td>{escape(sheet["si_inputs"][k])}</td></tr>' for k,v in sheet['inputs'].items())
        sections.append(f'<section><h2>{escape(sheet["name"])}</h2><pre>{escape(sheet["equation_text"])}</pre><table><tr><th>Symbol</th><th>Input</th><th>SI substitution</th></tr>{inputs}</table><h3>Substitution</h3><pre>{escape(sheet["substitution_text"])}</pre><p><strong>Result: {sheet["result_magnitude"]:.6g} {escape(sheet["result_unit"])}</strong> (dimensions checked)</p></section>')
    html = ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Electrical calculation sheets</title>'
            '<style>body{max-width:850px;margin:2rem auto;padding:0 1rem;font:17px/1.6 system-ui;color:#172638;background:#faf9f5}section{border-top:2px solid #456;padding:1rem 0}pre{overflow:auto}td,th{text-align:left;padding:.3rem .8rem;border-bottom:1px solid #ccc}a{color:#165a81}</style>'
            '<h1>Electrical calculation sheets</h1><p>I use these equations to follow each number from its inputs to its result. The same expression is evaluated symbolically and with physical units.</p><h2>Assumptions</h2><ul>'
            + ''.join(f'<li>{escape(a)}</li>' for a in assumptions)+'</ul>'+''.join(sections)+f'<h2>Conductor table result</h2><p>Required {selection["required_ampacity_a"]:g} A; 30 A device; selected copper AWG {selection["selected"]["awg"]}, {selection["selected"]["ampacity_a"]:g} A table ampacity. See panel notes for temperature and installation limits.</p>'+'<h2>References</h2><ul>'
            + ''.join(f'<li><a href="{escape(url, quote=True)}">{escape(title)}</a></li>' for title,url in refs.items())+'</ul></html>')
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out/'electrical-sheets.html').write_text(html)
    report = {'sheets':sheets,'conductor_selection':selection,'assumptions':assumptions,'references':refs}
    (out/'electrical-sheets.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report
