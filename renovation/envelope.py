"""One-dimensional heat flow and interface-plane Glaser diffusion, SI units.

Permeance is for the whole layer, not permeability per unit thickness.
No liquid storage, annual drying, thermal bridge or air leakage calculation.
"""
from dataclasses import dataclass
import json
import math
from pathlib import Path


@dataclass(frozen=True)
class Layer:
    name: str
    thickness_m: float
    conductivity_w_mk: float
    permeance_ng_pa_s_m2: float
    controls: tuple = ()
    continuous: bool = True


def _finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def saturation_pressure(temperature_c):
    """Magnus saturation pressure in Pa, over ice below 0 C."""
    if not _finite(temperature_c) or not -45 <= temperature_c <= 60:
        raise ValueError('temperature must be between -45 and 60 C')
    a, b = (17.625, 243.04) if temperature_c >= 0 else (22.587, 273.86)
    return 610.94 * math.exp(a * temperature_c / (b + temperature_c))


def _glaser(z, saturation, indoor_pa, outdoor_pa):
    """Lower convex pressure envelope: nonnegative sink at active interfaces.

    Linear vapour pressure between condensation planes; flux is -dp/dZ.
    Iterated hull removal is equivalent to removing planes requiring evaporation
    from an initially dry wall. The endpoint pressures are prescribed.
    """
    caps = [indoor_pa] + saturation + [outdoor_pa]
    hull = []
    for i in range(len(z)):
        while len(hull) >= 2:
            a, b = hull[-2:]
            left = (caps[b] - caps[a]) / (z[b] - z[a])
            right = (caps[i] - caps[b]) / (z[i] - z[b])
            if left < right:
                break
            hull.pop()
        hull.append(i)
    pressures = [0.] * len(z)
    for a, b in zip(hull, hull[1:]):
        for i in range(a, b + 1):
            pressures[i] = caps[a] + (caps[b] - caps[a]) * (z[i]-z[a])/(z[b]-z[a])
    flux = [(pressures[i]-pressures[i+1])/(z[i+1]-z[i]) for i in range(len(z)-1)]
    sinks = [max(0., flux[i]-flux[i+1]) if i+1 in hull else 0. for i in range(len(flux)-1)]
    return pressures, flux, sinks


def analyze(layers, indoor_c, outdoor_c, indoor_rh, outdoor_rh):
    """Return resistance, temperatures, controls and daily condensation potential.

    Layers run indoors to outdoors. RH is a fraction. No surface films are
    implicit: RSI is the sum of the specified layer resistances only.
    """
    if not layers or not all(_finite(x) and 0 <= x <= 1 for x in (indoor_rh, outdoor_rh)):
        raise ValueError('layers and relative humidities from 0 to 1 required')
    pi, po = indoor_rh * saturation_pressure(indoor_c), outdoor_rh * saturation_pressure(outdoor_c)
    known = {'air', 'water', 'vapour', 'thermal'}
    names = set()
    for layer in layers:
        if (not isinstance(layer.name, str) or not layer.name.strip() or layer.name in names
                or any(not _finite(x) or x <= 0 for x in (layer.thickness_m, layer.conductivity_w_mk, layer.permeance_ng_pa_s_m2))
                or not isinstance(layer.controls, (tuple, list))
                or any(not isinstance(c, str) or c not in known for c in layer.controls)
                or type(layer.continuous) is not bool):
            raise ValueError('invalid layer: unique names, positive SI properties and boolean continuity required')
        names.add(layer.name)
    resistances = [l.thickness_m / l.conductivity_w_mk for l in layers]
    vapour_resistances = [1 / l.permeance_ng_pa_s_m2 for l in layers]
    rsi, zv = sum(resistances), sum(vapour_resistances)
    if not math.isfinite(rsi) or not math.isfinite(zv) or min(rsi, zv) <= 0:
        raise ValueError('layer properties exceed numerical range')
    interfaces, z = [], [0.]
    accumulated_r = 0.
    for i in range(len(layers)-1):
        accumulated_r += resistances[i]
        z.append(z[-1] + vapour_resistances[i])
        temp = indoor_c + (outdoor_c - indoor_c) * accumulated_r / rsi
        pressure = pi + (po - pi) * z[-1] / zv
        saturation = saturation_pressure(temp)
        interfaces.append({'after': layers[i].name, 'temperature_c': temp,
                           'vapour_pressure_pa': pressure, 'saturation_pressure_pa': saturation,
                           'exceeds_saturation': pressure > saturation})
    z.append(zv)
    if any(b <= a for a, b in zip(z, z[1:])):
        raise ValueError('permeance contrast exceeds numerical resolution')
    pressures, flux, sinks = _glaser(z, [i['saturation_pressure_pa'] for i in interfaces], pi, po)
    for i, interface in enumerate(interfaces):
        interface.update(glaser_pressure_pa=pressures[i+1], condensation_g_m2_day=sinks[i] * 86400e-9)
    missing = sorted(c for c in known if not any(c in l.controls and l.continuous for l in layers))
    warnings = [f'{l.name}: declared control layer is not continuous.' for l in layers if l.controls and not l.continuous]
    insulation = [i for i, l in enumerate(layers) if 'thermal' in l.controls]
    vapour = [i for i, l in enumerate(layers) if 'vapour' in l.controls]
    water = [i for i, l in enumerate(layers) if 'water' in l.controls]
    if indoor_c > outdoor_c and insulation and vapour and min(vapour) > max(insulation):
        warnings.append('Vapour control is outside the thermal layer under heating conditions; review the assembly.')
    if insulation and water and max(water) < min(insulation):
        warnings.append('Water control is inside all insulation; review drainage and flashing transitions.')
    if sum(sinks) > 1e-7:
        warnings.append('Interface condensation is predicted for these steady boundary conditions; review moisture management.')
    return {'rsi': rsi, 'u_w_m2k': 1/rsi, 'interfaces': interfaces,
            'missing_controls': missing, 'warnings': warnings,
            'condensation_g_m2_day': sum(sinks)*86400e-9,
            'diffusion_in_ng_m2_s': flux[0], 'diffusion_out_ng_m2_s': flux[-1]}


def run(data, output_dir):
    """Analyze the named synthetic wall examples and write a portable JSON report."""
    if data.get('units') != {'length': 'm', 'conductivity': 'W/(m*K)', 'permeance': 'ng/(Pa*s*m^2)', 'temperature': 'degC', 'rh': 'fraction'}:
        raise ValueError('unsupported envelope units')
    climate = data['climate']
    results = []
    for assembly in data['assemblies']:
        result = analyze([Layer(**l) for l in assembly['layers']], **climate)
        results.append({'name': assembly['name'], **result})
    result = {'method': 'dry-start interface-plane Glaser, constant climate; not annual ISO 13788 certification',
              'climate': climate, 'assemblies': results}
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out/'envelope.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    return result
