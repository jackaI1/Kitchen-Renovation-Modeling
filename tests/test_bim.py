"""IFC coordination regressions: actual reopened solids, voids and relationships."""
import copy
import csv
import json
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.shape
import pytest

from renovation import bim

ROOT = Path(__file__).resolve().parents[1]


def element(id, type, origin, size, discipline='mechanical', **kw):
    return dict(id=id, type=type, origin_m=origin, size_m=size,
                discipline=discipline, storey='L1', **kw)


def plan(elements):
    return dict(name='Synthetic test', storeys=[dict(id='L1', elevation_m=0)],
                elements=elements, connections=[], site=[])


def test_exact_void_and_distance_cases(tmp_path):
    data = plan([
        element('wall', 'wall', [2, 0, 0], [.2, 8, 3], 'architecture'),
        element('void', 'opening', [1.9, 1, 1], [.4, 1, 1], 'architecture', host='wall'),
        element('through', 'duct', [1, 1.2, 1.2], [2, .4, .4]),
        element('blocked', 'duct', [1, 3, 1.2], [2, .4, .4]),
        element('partly', 'duct', [1, 1.7, 1.2], [2, .6, .4]),
        element('touch', 'duct', [1, 5, 1], [1, .4, .4]),
        element('near', 'duct', [1.75, 6, 1], [.2, .4, .4], clearance_m=.1),
        element('boundary', 'duct', [1.7, 7, 1], [.2, .4, .4], clearance_m=.1),
        element('far', 'duct', [10, 0, 1], [2, .4, .4]),
    ])
    result = bim.run(data, tmp_path)
    pairs = {(x['kind'], frozenset((x['element_a'], x['element_b']))) for x in result['issues']}
    assert ('hard', frozenset(('wall', 'blocked'))) in pairs
    assert ('hard', frozenset(('wall', 'partly'))) in pairs
    assert ('clearance', frozenset(('wall', 'near'))) in pairs
    assert not any('through' in pair or 'touch' in pair or 'boundary' in pair or 'far' in pair
                   for kind, pair in pairs if kind in ('hard', 'clearance'))
    assert any(x['kind'] == 'unprovided_opening' and x['element_a'] == 'blocked' for x in result['issues'])
    assert not any(x['kind'] == 'unprovided_opening' and x['element_a'] == 'through' for x in result['issues'])
    model = ifcopenshell.open(str(tmp_path / 'architecture.ifc'))
    wall = model.by_type('IfcWall')[0]
    shape = ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(), wall)
    # Volume from tessellated IFC geometry must include the real 0.2 m³ opening.
    assert ifcopenshell.util.shape.get_volume(shape.geometry) == pytest.approx(4.6)


def test_example_reopens_with_geometry_schedules_ports_and_stable_ids(tmp_path):
    data = json.loads((ROOT / 'examples/building.json').read_text())
    result = bim.run(data, tmp_path)
    models = [ifcopenshell.open(str(tmp_path / name)) for name in ('architecture.ifc', 'services.ifc')]
    arch, services = models
    assert all(m.schema == 'IFC4' for m in models)
    assert len(arch.by_type('IfcBuildingStorey')) == 2
    for cls in ('IfcWall', 'IfcSlab', 'IfcSpace', 'IfcOpeningElement'):
        assert arch.by_type(cls), cls
    for cls in ('IfcColumn', 'IfcDuctSegment', 'IfcPipeSegment', 'IfcUnitaryEquipment'):
        assert services.by_type(cls), cls
    assert arch.by_type('IfcRelVoidsElement')
    assert services.by_type('IfcRelNests')
    assert services.by_type('IfcRelConnectsPorts')
    for port in services.by_type('IfcDistributionPort'):
        if port.Name.startswith('through-'):
            assert tuple(port.ObjectPlacement.RelativePlacement.Axis.DirectionRatios) == (1.,0.,0.)
    for model in models:
        for obj in model.by_type('IfcProduct'):
            if obj.Representation:
                assert len(ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(), obj).geometry.verts) >= 24
    rows = list(csv.DictReader((tmp_path / 'schedule.csv').open()))
    duct = next(row for row in rows if row['element_id'] == 'duct-through')
    assert float(duct['flow_m3_s']) == pytest.approx(.18)
    assert duct['tag'] == 'SA-01' and float(duct['size_x_m']) == 4
    assert all(row['guid'] for row in rows)
    assert any(i['kind'] == 'disconnected_port' for i in result['issues'])
    assert any(i['kind'] == 'crane_swing' for i in result['issues'])
    safe = {'duct-through','duct-touch','duct-clearance-boundary','duct-disjoint'}
    assert not any(i['kind'] in ('hard','clearance') and (i['element_a'] in safe or i['element_b'] in safe) for i in result['issues'])
    assert (tmp_path / 'plan-L1.dxf').exists()
    assert (tmp_path / 'coordination.obj').exists()
    assert (tmp_path / 'issues.html').exists()
    before = {row['element_id']: row['guid'] for row in rows}
    bim.run(data, tmp_path / 'again')
    after = {row['element_id']: row['guid'] for row in csv.DictReader((tmp_path / 'again/schedule.csv').open())}
    assert before == after
    json.dumps(result, allow_nan=False)


def test_schedules_read_reopened_properties(tmp_path):
    bim.run(plan([element('a', 'duct', [0, 0, 0], [1, .2, .2], flow_m3_s=.1)]), tmp_path)
    model = ifcopenshell.open(str(tmp_path / 'services.ifc'))
    obj = model.by_type('IfcDuctSegment')[0]
    prop = next(p for r in obj.IsDefinedBy for p in r.RelatingPropertyDefinition.HasProperties
                if p.Name == 'Flow_m3_s')
    prop.NominalValue = model.create_entity('IfcReal', .37)
    model.write(str(tmp_path / 'edited.ifc'))
    rows = bim.extract_schedule([tmp_path / 'edited.ifc'])
    assert rows[0]['flow_m3_s'] == pytest.approx(.37)


def test_input_and_html_escaping(tmp_path):
    data = plan([element('<unsafe>', 'duct', [0, 0, 0], [1, .2, .2],
                         ports=[dict(id='free', position_m=[1, .1, .1], direction='SOURCE')])])
    bim.run(data, tmp_path)
    html = (tmp_path / 'issues.html').read_text()
    assert '&lt;unsafe&gt;' in html and '<unsafe>' not in html
    for field, value in [('size_m', [1, 0, 1]), ('origin_m', [float('nan'), 0, 0]),
                         ('type', 'curved_duct'), ('discipline', 'unrecognized')]:
        bad = copy.deepcopy(data)
        bad['elements'][0][field] = value
        with pytest.raises(ValueError):
            bim.run(bad, tmp_path / 'bad')


def test_requested_clearance_includes_contact_but_uses_euclidean_gap(tmp_path):
    data = plan([
        element('wall', 'wall', [2, 0, 0], [.2, 8, 3], 'architecture'),
        element('contact', 'duct', [1, 4, 1], [1, .2, .2], clearance_m=.1),
        element('diagonal-safe', 'duct', [1.72, 8.08, 1], [.2, .2, .2], clearance_m=.1),
        element('diagonal-near', 'duct', [1.74, 8.06, 1], [.2, .2, .2], clearance_m=.1),
    ])
    issues = bim.run(data, tmp_path)['issues']
    assert any(i['kind'] == 'clearance' and i['element_b'] == 'contact' for i in issues)
    assert not any(i['element_b'] == 'diagonal-safe' for i in issues)
    near = next(i for i in issues if i['kind'] == 'clearance' and i['element_b'] == 'diagonal-near')
    assert near['distance_m'] == pytest.approx((2*.06**2)**.5)
    assert not any(i['kind'] == 'hard' for i in issues)


def test_reopened_connectivity_and_crane_boundary(tmp_path):
    data = json.loads((ROOT / 'examples/building.json').read_text())
    result = bim.run(data, tmp_path)
    free = [i['description'] for i in result['issues'] if i['kind']=='disconnected_port']
    assert len(free) == 3
    assert any('tail-free' in d for d in free)
    assert not any('through-in ' in d or 'through-out ' in d or 'ahu-out ' in d for d in free)
    assert any(i['element_b']=='man-material-hoist' for i in result['issues'] if i['kind']=='crane_swing')
    assert not any(i['element_b']=='hoist-outside-swing' for i in result['issues'])
    model = ifcopenshell.open(str(tmp_path/'services.ifc'))
    port = next(p for p in model.by_type('IfcDistributionPort') if p.Name=='tail-in')
    port.ObjectPlacement.RelativePlacement.Location.Coordinates = (1., .2, .2)
    model.write(str(tmp_path/'misaligned.ifc'))
    issues = bim.detect_issues([tmp_path/'architecture.ifc',tmp_path/'misaligned.ifc'])
    assert any(i['kind']=='misaligned_ports' for i in issues)
    import ezdxf
    drawing = ezdxf.readfile(tmp_path/'plan-L1.dxf')
    assert drawing.units == 6
    assert len(drawing.modelspace().query('CIRCLE')) == 1
    assert len(drawing.modelspace().query('LWPOLYLINE')) > 20


@pytest.mark.parametrize('bad', [None, [], {'storeys':[[]]},
    {'storeys':[dict(id='L1',elevation_m=0)],'elements':[None]},
    {'storeys':[dict(id='L1',elevation_m=0)],'site':'oops'},
    {'storeys':[dict(id='L1',elevation_m=0)],'connections':[None]}])
def test_malformed_input_rejected_with_value_error(bad,tmp_path):
    with pytest.raises(ValueError):
        bim.run(bad,tmp_path)


def test_numeric_extent_and_external_units_are_bounded(tmp_path):
    data=plan([element('a','duct',[1e100,0,0],[1,.2,.2])])
    with pytest.raises(ValueError):
        bim.run(data,tmp_path)
    data['elements'][0]['origin_m']=[0,0,0]
    bim.run(data,tmp_path)
    model=ifcopenshell.open(str(tmp_path/'services.ifc'))
    unit=next(u for u in model.by_type('IfcSIUnit') if u.UnitType=='LENGTHUNIT')
    unit.Prefix='MILLI'
    model.write(str(tmp_path/'millimetres.ifc'))
    for reader in (bim.extract_schedule,bim.detect_issues):
        with pytest.raises(ValueError,match='metre'):
            reader([tmp_path/'millimetres.ifc'])
