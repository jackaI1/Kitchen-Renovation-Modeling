"""Validate the stored, metre-based source before Blender touches it."""
import math
EXPECTED={'tank_port','tank_starboard','tank_freshwater','engine_room'}
def vector(value):
    return isinstance(value,list) and len(value)==3 and all(isinstance(v,(int,float)) and math.isfinite(v) for v in value)
def validate_source(data):
    if data.get('units')!='metres':raise ValueError('Source units must be metres')
    parts=data.get('parts',[])
    if len(parts)!=4 or {p.get('id') for p in parts}!=EXPECTED:raise ValueError('Part names must be unique and match all four compartments')
    for p in parts:
        if not vector(p.get('center')):raise ValueError('Centers must be finite 3D vectors')
        if not vector(p.get('size')) or any(v<=0 or v>20 for v in p['size']):raise ValueError('Invalid compartment dimensions')
    stations=data.get('stations',[])
    if len(stations)<3 or any(len(s)!=2 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in s) or s[1]<=0 for s in stations) or any(a[0]>=b[0] for a,b in zip(stations,stations[1:])):raise ValueError('Hull stations must have increasing x and positive widths')
    return len(parts)
