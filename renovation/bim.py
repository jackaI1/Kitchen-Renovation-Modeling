"""Small, deterministic IFC4 coordination study for axis-aligned rectangular solids.

All dimensions are metres and flow is m³/s. This is an educational geometry
subset, not a general IFC importer, construction coordination or lift approval.
"""
from __future__ import annotations

import csv
import html
import itertools
import math
from pathlib import Path
import uuid

import ezdxf
import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.guid
import ifcopenshell.util.element
import ifcopenshell.util.placement
import ifcopenshell.util.shape
import ifcopenshell.util.unit

EPS = 1e-8
NAMESPACE = uuid.UUID('3c7ce85f-bffc-4e6c-87ae-b9e8eb20bf79')
TYPES = {'wall': 'IfcWall', 'slab': 'IfcSlab', 'column': 'IfcColumn',
         'opening': 'IfcOpeningElement', 'space': 'IfcSpace',
         'duct': 'IfcDuctSegment', 'pipe': 'IfcPipeSegment',
         'equipment': 'IfcUnitaryEquipment', 'crane': 'IfcBuildingElementProxy',
         'hoist': 'IfcBuildingElementProxy'}
DISCIPLINES = {'architecture', 'structure', 'mechanical', 'plumbing', 'site'}
SCHEDULE_FIELDS = ['element_id', 'guid', 'ifc_class', 'discipline', 'storey', 'tag',
                   'size_x_m', 'size_y_m', 'size_z_m', 'flow_m3_s', 'volume_m3']
ISSUE_FIELDS = ['issue_id', 'kind', 'element_a', 'element_b', 'guid_a', 'guid_b',
                'x_m', 'y_m', 'z_m', 'distance_m', 'description']


def guid(key):
    """Stable IFC compressed UUID, independent of creation order/output location."""
    return ifcopenshell.guid.compress(uuid.uuid5(NAMESPACE, str(key)).hex)


def _number(value, name, minimum=None, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    if abs(value) > 1e6 or (positive and value < 1e-6) or (minimum is not None and value < minimum):
        raise ValueError(f'{name} outside supported range')
    return float(value)


def _vector(value, name, positive=False):
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        raise ValueError(f'{name} must contain three SI values')
    return [_number(v, name, positive=positive) for v in value]


def validate(data):
    """Reject unsupported shapes, unknown references and ambiguous identities."""
    if not isinstance(data, dict) or not data.get('storeys'):
        raise ValueError('at least one storey is required')
    for field in ('storeys','elements','site','connections'):
        if not isinstance(data.get(field,[]),list):
            raise ValueError(f'{field} must be a list')
    if not isinstance(data.get('name','Synthetic building'),str):
        raise ValueError('name must be a string')
    storeys = set()
    for s in data['storeys']:
        if not isinstance(s,dict):
            raise ValueError('storeys must be objects')
        if not isinstance(s.get('id'), str) or not s['id'] or s['id'] in storeys:
            raise ValueError('storey ids must be unique nonempty strings')
        storeys.add(s['id'])
        _number(s.get('elevation_m'), 'elevation_m')
    elements = data.get('elements', []) + data.get('site', [])
    ids, ports = {}, {}
    for e in elements:
        if not isinstance(e,dict):
            raise ValueError('elements must be objects')
        key = e.get('id')
        if not isinstance(key, str) or not key or key in ids:
            raise ValueError('element ids must be unique nonempty strings')
        ids[key] = e
        if not isinstance(e.get('type'),str) or not isinstance(e.get('discipline'),str) or e['type'] not in TYPES or e['discipline'] not in DISCIPLINES:
            raise ValueError('unsupported type or discipline')
        if e['type'] in ('wall', 'slab', 'opening', 'space') and e['discipline'] != 'architecture':
            raise ValueError('walls, slabs, spaces and openings belong to architecture')
        if e['type'] in ('duct', 'pipe', 'equipment') and e['discipline'] not in ('mechanical', 'plumbing'):
            raise ValueError('services require mechanical/plumbing discipline')
        if e['type'] in ('crane', 'hoist') and e['discipline'] != 'site':
            raise ValueError('site objects require site discipline')
        if not isinstance(e.get('storey'),str) or e['storey'] not in storeys:
            raise ValueError('unknown storey')
        _vector(e.get('origin_m'), 'origin_m')
        _vector(e.get('size_m'), 'size_m', positive=True)
        _number(e.get('clearance_m', 0), 'clearance_m', minimum=0)
        if 'flow_m3_s' in e:
            _number(e['flow_m3_s'], 'flow_m3_s', minimum=0)
        if e['type'] == 'crane':
            _number(e.get('swing_radius_m'), 'swing_radius_m', positive=True)
        if e.get('ports') and e['type'] not in ('duct', 'pipe', 'equipment'):
            raise ValueError('ports supported on distribution elements only')
        if not isinstance(e.get('ports',[]),list):
            raise ValueError('ports must be a list')
        for p in e.get('ports', []):
            if not isinstance(p,dict):
                raise ValueError('ports must be objects')
            if not isinstance(p.get('id'), str) or not p['id'] or p['id'] in ports:
                raise ValueError('port ids must be unique nonempty strings')
            ports[p['id']] = (e, p)
            _vector(p.get('position_m'), 'port position_m')
            if p.get('direction') not in ('SOURCE', 'SINK', 'SOURCEANDSINK'):
                raise ValueError('unsupported port direction')
    for e in elements:
        if e['type'] == 'opening':
            if not isinstance(e.get('host'),str) or e['host'] not in ids or ids[e['host']]['type'] != 'wall':
                raise ValueError('opening host must be a wall')
            if ids[e['host']]['storey'] != e['storey']:
                raise ValueError('opening and host storeys must agree')
            if _intersection(_input_box(e), _input_box(ids[e['host']])) is None:
                raise ValueError('opening must intersect its host')
    used = set()
    for connection in data.get('connections', []):
        if not isinstance(connection,list) or len(connection) != 2 or any(not isinstance(p,str) or p not in ports for p in connection):
            raise ValueError('connection must reference two ports')
        if connection[0] == connection[1] or any(p in used for p in connection):
            raise ValueError('each port may connect once to a different port')
        used.update(connection)
        a, b = [ports[p] for p in connection]
        if a[0]['id'] == b[0]['id']:
            raise ValueError('connection must join different elements')
        if _system(a[0]) != _system(b[0]):
            raise ValueError('connected ports must share system type')
        directions = {a[1]['direction'], b[1]['direction']}
        if directions != {'SOURCE', 'SINK'} and directions != {'SOURCEANDSINK'}:
            raise ValueError('connected ports must have compatible flow directions')
        if math.dist(a[1]['position_m'], b[1]['position_m']) > EPS:
            raise ValueError('connected port positions must coincide')
    return elements


def _input_box(e):
    return (tuple(e['origin_m']), tuple(x + s for x, s in zip(e['origin_m'], e['size_m'])))


def _system(e):
    return 'DOMESTICCOLDWATER' if e['type'] == 'pipe' or e['discipline'] == 'plumbing' else 'AIRCONDITIONING'


def _root(f, cls, key, **kw):
    return f.create_entity(cls, GlobalId=guid(key), **kw)


def _axis(f, xyz):
    return f.create_entity('IfcAxis2Placement3D', Location=f.create_entity('IfcCartesianPoint', Coordinates=tuple(map(float, xyz))))


def _placement(f, xyz, relative=None):
    return f.create_entity('IfcLocalPlacement', PlacementRelTo=relative, RelativePlacement=_axis(f, xyz))


def _properties(f, obj, values):
    props = []
    for name, value in values.items():
        if value is None:
            continue
        kind = 'IfcReal' if isinstance(value, (int, float)) else 'IfcLabel'
        props.append(f.create_entity('IfcPropertySingleValue', Name=name,
                                    NominalValue=f.create_entity(kind, value)))
    pset = _root(f, 'IfcPropertySet', obj.GlobalId + '/properties', Name='StudyCoordination', HasProperties=props)
    _root(f, 'IfcRelDefinesByProperties', obj.GlobalId + '/pset', RelatedObjects=[obj], RelatingPropertyDefinition=pset)


def _new_model(data, scope):
    f = ifcopenshell.file(schema='IFC4')
    context = f.create_entity('IfcGeometricRepresentationContext', ContextIdentifier='Model', ContextType='Model',
                              CoordinateSpaceDimension=3, Precision=1e-7, WorldCoordinateSystem=_axis(f, [0, 0, 0]))
    units = f.create_entity('IfcUnitAssignment', Units=[f.create_entity('IfcSIUnit', UnitType='LENGTHUNIT', Name='METRE'),
        f.create_entity('IfcSIUnit', UnitType='AREAUNIT', Name='SQUARE_METRE'),
        f.create_entity('IfcSIUnit', UnitType='VOLUMEUNIT', Name='CUBIC_METRE')])
    project = _root(f, 'IfcProject', scope+'/project', Name=data.get('name', 'Synthetic building'),
                    RepresentationContexts=[context], UnitsInContext=units)
    site = _root(f, 'IfcSite', scope+'/site', Name='Synthetic site', CompositionType='ELEMENT', ObjectPlacement=_placement(f,[0,0,0]))
    building = _root(f, 'IfcBuilding', scope+'/building', Name='Study building', CompositionType='ELEMENT', ObjectPlacement=_placement(f,[0,0,0]))
    _root(f, 'IfcRelAggregates', scope+'/project-site', RelatingObject=project, RelatedObjects=[site])
    _root(f, 'IfcRelAggregates', scope+'/site-building', RelatingObject=site, RelatedObjects=[building])
    storeys = {}
    for s in data['storeys']:
        storey = _root(f, 'IfcBuildingStorey', scope+'/storey/'+s['id'], Name=s['id'],
                       CompositionType='ELEMENT', Elevation=float(s['elevation_m']),
                       ObjectPlacement=_placement(f, [0,0,s['elevation_m']]))
        storeys[s['id']] = storey
    _root(f, 'IfcRelAggregates', scope+'/building-storeys', RelatingObject=building, RelatedObjects=list(storeys.values()))
    return f, context, storeys


def _make_element(f, context, e):
    kind = e['type']
    obj = _root(f, TYPES[kind], 'element/'+e['id'], Name=e['id'], ObjectPlacement=_placement(f, e['origin_m']))
    if kind != 'space':
        obj.Tag = str(e.get('tag', e['id']))
    if kind == 'space':
        obj.CompositionType = 'ELEMENT'
    predefined = {'wall':'NOTDEFINED', 'slab':'FLOOR', 'column':'COLUMN', 'opening':'OPENING',
                  'duct':'RIGIDSEGMENT', 'pipe':'RIGIDSEGMENT', 'equipment':'AIRHANDLER',
                  'crane':'USERDEFINED', 'hoist':'USERDEFINED'}
    if kind in predefined:
        obj.PredefinedType = predefined[kind]
    if kind in ('crane', 'hoist'):
        obj.ObjectType = kind
    x, y, z = map(float, e['size_m'])
    profile = f.create_entity('IfcRectangleProfileDef', ProfileType='AREA', XDim=x, YDim=y)
    solid = f.create_entity('IfcExtrudedAreaSolid', SweptArea=profile, Position=_axis(f, [x/2,y/2,0]),
                             ExtrudedDirection=f.create_entity('IfcDirection', DirectionRatios=(0.,0.,1.)), Depth=z)
    rep = f.create_entity('IfcShapeRepresentation', ContextOfItems=context, RepresentationIdentifier='Body',
                          RepresentationType='SweptSolid', Items=[solid])
    obj.Representation = f.create_entity('IfcProductDefinitionShape', Representations=[rep])
    _properties(f, obj, {'ElementId':e['id'], 'Discipline':e['discipline'], 'Kind':kind,
                         'Clearance_m':float(e.get('clearance_m',0)), 'Flow_m3_s':e.get('flow_m3_s'),
                         'SwingRadius_m':e.get('swing_radius_m')})
    return obj


def _write_models(data, out):
    all_elements = validate(data)
    paths = []
    for scope in ('architecture', 'services'):
        f, context, storeys = _new_model(data, scope)
        specs = [e for e in all_elements if (e['discipline'] == 'architecture') == (scope == 'architecture')]
        objects = {e['id']: _make_element(f, context, e) for e in specs}
        ports = {}
        for e in specs:
            obj = objects[e['id']]
            if e['type'] == 'opening':
                _root(f, 'IfcRelVoidsElement', 'void/'+e['id'], RelatingBuildingElement=objects[e['host']], RelatedOpeningElement=obj)
            elif e['type'] == 'space':
                _root(f, 'IfcRelAggregates', 'space/'+e['id'], RelatingObject=storeys[e['storey']], RelatedObjects=[obj])
            else:
                _root(f, 'IfcRelContainedInSpatialStructure', 'contain/'+e['id'], RelatedElements=[obj], RelatingStructure=storeys[e['storey']])
            nested = []
            for p in e.get('ports', []):
                local = [a-b for a,b in zip(p['position_m'], e['origin_m'])]
                port = _root(f, 'IfcDistributionPort', 'port/'+p['id'], Name=p['id'], FlowDirection=p['direction'],
                             PredefinedType='PIPE' if _system(e) == 'DOMESTICCOLDWATER' else 'DUCT',
                             SystemType=_system(e), ObjectPlacement=_placement(f,local,obj.ObjectPlacement))
                # IFC port Axis follows flow for a SINK and points outward for a SOURCE.
                # The supported straight run direction is its longest box dimension.
                axis_index = max(range(3), key=lambda i:e['size_m'][i])
                outward = 1. if local[axis_index] >= e['size_m'][axis_index]/2 else -1.
                axis = [0.,0.,0.]
                axis[axis_index] = -outward if p['direction']=='SINK' else outward
                port.ObjectPlacement.RelativePlacement.Axis = f.create_entity('IfcDirection',DirectionRatios=tuple(axis))
                ref = (0.,1.,0.) if axis_index==0 else (1.,0.,0.)
                port.ObjectPlacement.RelativePlacement.RefDirection = f.create_entity('IfcDirection',DirectionRatios=ref)
                ports[p['id']] = port
                nested.append(port)
            if nested:
                _root(f, 'IfcRelNests', 'ports/'+e['id'], RelatingObject=obj, RelatedObjects=nested)
        for a,b in data.get('connections', []):
            if a in ports and b in ports:
                if ports[a].FlowDirection == 'SINK':
                    a,b = b,a
                _root(f, 'IfcRelConnectsPorts', 'connection/'+a+'/'+b, RelatingPort=ports[a], RelatedPort=ports[b])
        path = out / (scope+'.ifc')
        f.write(str(path))
        paths.append(path)
    return paths


def _pset(obj):
    return ifcopenshell.util.element.get_psets(obj).get('StudyCoordination', {})


def _base_box(obj):
    """Read dimensions/placements from IFC geometry, never from plan metadata."""
    rep = next(r for r in obj.Representation.Representations if r.RepresentationIdentifier == 'Body')
    if len(rep.Items) != 1 or not rep.Items[0].is_a('IfcExtrudedAreaSolid'):
        raise ValueError('only single rectangular extrusions are supported')
    solid = rep.Items[0]
    if not solid.SweptArea.is_a('IfcRectangleProfileDef') or tuple(solid.ExtrudedDirection.DirectionRatios) != (0.,0.,1.):
        raise ValueError('only axis-aligned rectangular extrusions are supported')
    import numpy as np
    matrix = ifcopenshell.util.placement.get_local_placement(obj.ObjectPlacement) @ ifcopenshell.util.placement.get_axis2placement(solid.Position)
    if not np.allclose(matrix[:3,:3], np.eye(3), atol=EPS, rtol=0):
        raise ValueError('rotated placements are outside supported subset')
    profile = solid.SweptArea
    if profile.Position is not None:
        raise ValueError('offset/rotated profile placement is outside supported subset')
    center = matrix[:3,3]
    lo = (float(center[0]-profile.XDim/2), float(center[1]-profile.YDim/2), float(center[2]))
    hi = (lo[0]+profile.XDim, lo[1]+profile.YDim, lo[2]+solid.Depth)
    return lo, hi


def _intersection(a,b):
    lo = tuple(max(x,y) for x,y in zip(a[0],b[0]))
    hi = tuple(min(x,y) for x,y in zip(a[1],b[1]))
    return (lo,hi) if all(y-x > EPS for x,y in zip(lo,hi)) else None


def _subtract(box, void):
    overlap = _intersection(box, void)
    if overlap is None:
        return [box]
    lo, hi = map(list, box)
    cut_lo, cut_hi = overlap
    pieces = []
    for axis in range(3):
        if cut_lo[axis]-lo[axis] > EPS:
            upper = hi.copy(); upper[axis] = cut_lo[axis]
            pieces.append((tuple(lo),tuple(upper)))
            lo[axis] = cut_lo[axis]
        if hi[axis]-cut_hi[axis] > EPS:
            lower = lo.copy(); lower[axis] = cut_hi[axis]
            pieces.append((tuple(lower),tuple(hi)))
            hi[axis] = cut_hi[axis]
    return pieces


def _boxes(obj):
    boxes = [_base_box(obj)]
    for relation in getattr(obj, 'HasOpenings', ()):
        void = _base_box(relation.RelatedOpeningElement)
        boxes = [piece for box in boxes for piece in _subtract(box,void)]
    return boxes


def _distance(a,b):
    return math.sqrt(sum(max(0.,a[0][i]-b[1][i], b[0][i]-a[1][i])**2 for i in range(3)))


def _location(box):
    return [(a+b)/2 for a,b in zip(*box)]


def _open_model(path):
    model = ifcopenshell.open(str(path))
    if model.schema != 'IFC4' or abs(ifcopenshell.util.unit.calculate_unit_scale(model)-1.) > EPS:
        raise ValueError('supported subset requires IFC4 metre length units')
    return model


def extract_schedule(paths):
    """Reopen IFC files and extract tags, properties and physical solid sizes/volume."""
    rows = []
    settings = ifcopenshell.geom.settings()
    for path in paths:
        model = _open_model(path)
        for obj in model.by_type('IfcProduct'):
            pset = _pset(obj)
            if not obj.Representation or not pset:
                continue
            lo, hi = _base_box(obj)
            shape = ifcopenshell.geom.create_shape(settings, obj)
            storey = ifcopenshell.util.element.get_container(obj)
            if obj.is_a('IfcSpace'):
                storey = ifcopenshell.util.element.get_aggregate(obj)
            row = dict(element_id=pset['ElementId'], guid=obj.GlobalId, ifc_class=obj.is_a(),
                       discipline=pset['Discipline'], storey=storey.Name if storey else '',
                       tag=getattr(obj,'Tag','') or '', flow_m3_s=pset.get('Flow_m3_s',''),
                       volume_m3=ifcopenshell.util.shape.get_volume(shape.geometry))
            row.update(dict(zip(('size_x_m','size_y_m','size_z_m'), (b-a for a,b in zip(lo,hi)))))
            rows.append(row)
    return sorted(rows, key=lambda r:r['element_id'])


def _issue(kind, a, b=None, *, location=None, distance=0., description=''):
    pset = _pset(a)
    other = _pset(b) if b is not None else {}
    key = kind+'/'+pset.get('ElementId', a.Name or '')+'/'+other.get('ElementId','')
    xyz = location if location is not None else _location(_base_box(a))
    return dict(issue_id=guid(key), kind=kind, element_a=pset.get('ElementId',a.Name),
                element_b=other.get('ElementId',''), guid_a=a.GlobalId,
                guid_b=b.GlobalId if b is not None else '', x_m=xyz[0],y_m=xyz[1],z_m=xyz[2],
                distance_m=distance, description=description)


def detect_issues(paths):
    """Exact union-of-boxes clashes for the generated subset; no bbox-only wall void test."""
    models = [_open_model(path) for path in paths]
    objects = [obj for m in models for obj in m.by_type('IfcProduct') if obj.Representation and _pset(obj)]
    physical = [o for o in objects if _pset(o)['Kind'] not in ('opening','space','crane','hoist')]
    geometry = {o.GlobalId:_boxes(o) for o in physical}
    issues = []
    for a,b in itertools.combinations(physical,2):
        pa,pb = _pset(a),_pset(b)
        if pa['Discipline'] == pb['Discipline']:
            continue
        pairs = list(itertools.product(geometry[a.GlobalId], geometry[b.GlobalId]))
        intersections = [_intersection(x,y) for x,y in pairs]
        hard = next((i for i in intersections if i is not None),None)
        if hard is not None:
            issues.append(_issue('hard',a,b,location=_location(hard), description='Positive-volume intersection of physical solids.'))
            duct,wall = (a,b) if a.is_a('IfcDuctSegment') and b.is_a('IfcWall') else (b,a)
            if duct.is_a('IfcDuctSegment') and wall.is_a('IfcWall'):
                issues.append(_issue('unprovided_opening',duct,wall,location=_location(hard), description='Duct intersects remaining wall material; provide or resize an opening.'))
        elif pairs:
            distance = min(_distance(x,y) for x,y in pairs)
            required = max(pa.get('Clearance_m',0), pb.get('Clearance_m',0))
            # Contact alone is not a hard clash; boundary equality is never a clearance failure.
            if distance < required-EPS:
                issues.append(_issue('clearance',a,b,distance=distance, description=f'Physical surface gap {distance:.6g} m is below {required:.6g} m.'))
    for model in models:
        for port in model.by_type('IfcDistributionPort'):
            parent = next((r.RelatingObject for r in port.Nests), None)
            if parent is None:
                continue
            pos = ifcopenshell.util.placement.get_local_placement(port.ObjectPlacement)[:3,3].tolist()
            if not port.ConnectedTo and not port.ConnectedFrom:
                issue = _issue('disconnected_port',parent,location=pos, description=f'Distribution port {port.Name} has no IfcRelConnectsPorts relation.')
                issue['issue_id'] = guid('disconnected/'+port.GlobalId)
                issues.append(issue)
        for rel in model.by_type('IfcRelConnectsPorts'):
            a,b = rel.RelatingPort,rel.RelatedPort
            xyz_a = ifcopenshell.util.placement.get_local_placement(a.ObjectPlacement)[:3,3].tolist()
            xyz_b = ifcopenshell.util.placement.get_local_placement(b.ObjectPlacement)[:3,3].tolist()
            if math.dist(xyz_a,xyz_b) > EPS:
                parent = a.Nests[0].RelatingObject
                issues.append(_issue('misaligned_ports',parent,location=xyz_a,distance=math.dist(xyz_a,xyz_b),description=f'Connected ports {a.Name} and {b.Name} do not coincide.'))
    for crane in [o for o in objects if _pset(o)['Kind']=='crane']:
        center = _location(_base_box(crane))
        radius = _pset(crane)['SwingRadius_m']
        for target in objects:
            if target.GlobalId == crane.GlobalId or _pset(target)['Kind'] in ('opening','space'):
                continue
            lo,hi = _base_box(target)
            closest = [max(lo[i],min(hi[i],center[i])) for i in range(2)]
            distance = math.dist(center[:2],closest)
            if distance < radius-EPS:
                issues.append(_issue('crane_swing',crane,target,location=[*closest,0.],distance=distance,
                                     description='Target footprint intersects crane plan swing disk; height/load/dynamics are not checked.'))
    return sorted(issues,key=lambda i:(i['kind'],i['element_a'],i['element_b'],i['issue_id']))


def _csv(path, fields, rows):
    with path.open('w',newline='',encoding='utf-8') as stream:
        writer = csv.DictWriter(stream,fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def _exports(paths, out, data):
    """Export reopened actual IFC tessellations and geometry-based plan footprints."""
    models = [_open_model(path) for path in paths]
    settings = ifcopenshell.geom.settings(); settings.set(settings.USE_WORLD_COORDS,True)
    offset = 1
    with (out/'coordination.obj').open('w',encoding='utf-8') as stream:
        stream.write('# Actual reopened IFC tessellation, metres; spaces/openings omitted\n')
        for model in models:
            for obj in model.by_type('IfcProduct'):
                pset = _pset(obj)
                if not obj.Representation or not pset or pset['Kind'] in ('opening','space'):
                    continue
                shape = ifcopenshell.geom.create_shape(settings,obj)
                verts, faces = shape.geometry.verts,shape.geometry.faces
                stream.write('o '+obj.GlobalId+'\n')
                for i in range(0,len(verts),3):
                    stream.write('v '+' '.join(f'{v:.9g}' for v in verts[i:i+3])+'\n')
                for i in range(0,len(faces),3):
                    stream.write('f '+' '.join(str(v+offset) for v in faces[i:i+3])+'\n')
                offset += len(verts)//3
    # Storey ordinal in filename prevents unsafe input identifiers becoming paths.
    drawings = []
    for index,storey in enumerate(data['storeys'],1):
        doc = ezdxf.new('R2010'); doc.units = 6
        msp = doc.modelspace()
        for discipline in sorted(DISCIPLINES):
            doc.layers.new(discipline)
        for model in models:
            for obj in model.by_type('IfcProduct'):
                pset = _pset(obj)
                if not obj.Representation or not pset:
                    continue
                container = ifcopenshell.util.element.get_container(obj)
                if obj.is_a('IfcSpace'):
                    container = ifcopenshell.util.element.get_aggregate(obj)
                if obj.is_a('IfcOpeningElement'):
                    host = obj.VoidsElements[0].RelatingBuildingElement
                    container = ifcopenshell.util.element.get_container(host)
                if container is None or container.Name != storey['id']:
                    continue
                lo,hi = _base_box(obj)
                msp.add_lwpolyline([(lo[0],lo[1]),(hi[0],lo[1]),(hi[0],hi[1]),(lo[0],hi[1])],
                                   close=True,dxfattribs={'layer':pset['Discipline']})
                msp.add_text(str(pset['ElementId']),dxfattribs={'height':.15,'insert':(lo[0],lo[1]),'layer':pset['Discipline']})
                if pset['Kind']=='crane':
                    c = _location((lo,hi))
                    msp.add_circle(c[:2],pset['SwingRadius_m'],dxfattribs={'layer':'site'})
        path = out/f'plan-L{index}.dxf'; doc.saveas(path); drawings.append(str(path))
    return drawings


def run(input_dict, output_dir):
    """Build IFCs, reopen, coordinate and export; return a JSON-serializable summary."""
    validate(input_dict)
    out = Path(output_dir); out.mkdir(parents=True,exist_ok=True)
    paths = _write_models(input_dict,out)
    schedule = extract_schedule(paths)
    issues = detect_issues(paths)
    _csv(out/'schedule.csv',SCHEDULE_FIELDS,schedule)
    _csv(out/'issues.csv',ISSUE_FIELDS,issues)
    rows = ''.join('<tr>'+''.join('<td>'+html.escape(str(issue[field]))+'</td>' for field in ISSUE_FIELDS)+'</tr>' for issue in issues)
    (out/'issues.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Coordination issues</title>'
        '<style>body{font:15px system-ui;margin:2rem}table{border-collapse:collapse}td,th{padding:.4rem;border:1px solid #bbb;text-align:left}</style>'
        '<h1>Synthetic coordination study</h1><p>BCF-style issue list, not a full BCF archive. Locations in metres. '
        'Rectangular axis-aligned solids only; spaces excluded. Touching faces are not hard clashes; a positive requested clearance still applies. The exact clearance boundary passes. '
        'Crane checks are plan-radius screens, not lift approval.</p><table><thead><tr>'
        +''.join('<th>'+html.escape(field)+'</th>' for field in ISSUE_FIELDS)+'</tr></thead><tbody>'+rows+'</tbody></table></html>',encoding='utf-8')
    drawings = _exports(paths,out,input_dict)
    return {'schema':'IFC4','element_count':len(schedule),'issue_count':len(issues),'issues':issues,
            'issue_counts':{kind:sum(i['kind']==kind for i in issues) for kind in sorted({i['kind'] for i in issues})},
            'artifacts':{'architecture_ifc':str(paths[0]),'services_ifc':str(paths[1]),
                         'schedule_csv':str(out/'schedule.csv'),'issues_csv':str(out/'issues.csv'),
                         'issues_html':str(out/'issues.html'),'obj':str(out/'coordination.obj'),'plans_dxf':drawings},
            'assumptions':['Synthetic educational model, not the actual house.',
                'Axis-aligned rectangular extrusions; actual wall void volumes are subtracted.',
                'Cross-discipline clashes only; spaces and site objects excluded from physical clashes.',
                'Clearance is Euclidean surface gap, strict below maximum of pair clearances; contact fails only a positive requested clearance.',
                'Crane swing is a 2D radius screen, without capacity, lift path or height checks.']}
