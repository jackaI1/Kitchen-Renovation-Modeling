"""One-dimensional steady-state heat and vapour screening, SI units."""
from dataclasses import dataclass
import math

@dataclass(frozen=True)
class Layer:
    name: str
    thickness_m: float
    conductivity_w_mk: float
    permeance_ng_pa_s_m2: float
    controls: tuple = ()
    continuous: bool = True

def saturation_pressure(temperature_c):
    """Approximate saturation vapour pressure in Pa (Magnus equation)."""
    if not math.isfinite(temperature_c) or not -45 <= temperature_c <= 60:
        raise ValueError('temperature must be between -45 and 60 C')
    a, b = (17.625, 243.04) if temperature_c >= 0 else (22.587, 273.86)
    return 610.94 * math.exp(a * temperature_c / (b + temperature_c))

def analyze(layers, indoor_c, outdoor_c, indoor_rh, outdoor_rh):
    """Layers are ordered indoors to outdoors; RH is a fraction, not percent."""
    if not layers or not all(math.isfinite(x) and 0 <= x <= 1 for x in (indoor_rh, outdoor_rh)):
        raise ValueError('layers and relative humidities from 0 to 1 required')
    pi, po = indoor_rh * saturation_pressure(indoor_c), outdoor_rh * saturation_pressure(outdoor_c)
    known = {'air', 'water', 'vapour', 'thermal'}
    for layer in layers:
        if not layer.name or any(not math.isfinite(x) or x <= 0 for x in (layer.thickness_m, layer.conductivity_w_mk, layer.permeance_ng_pa_s_m2)) or set(layer.controls) - known:
            raise ValueError('invalid layer')
    resistances = [l.thickness_m / l.conductivity_w_mk for l in layers]
    vapour_resistances = [1 / l.permeance_ng_pa_s_m2 for l in layers]
    rsi, zv = sum(resistances), sum(vapour_resistances)
    interfaces = []
    for i in range(len(layers)-1):
        temp = indoor_c + (outdoor_c - indoor_c) * sum(resistances[:i+1]) / rsi
        pressure = pi + (po - pi) * sum(vapour_resistances[:i+1]) / zv
        interfaces.append({'after': layers[i].name, 'temperature_c': temp, 'vapour_pressure_pa': pressure, 'saturation_pressure_pa': saturation_pressure(temp), 'exceeds_saturation': pressure > saturation_pressure(temp)})
    missing = sorted(control for control in known if not any(control in layer.controls and layer.continuous for layer in layers))
    warnings = []
    insulation_indices = [i for i, l in enumerate(layers) if 'thermal' in l.controls]
    vapour_indices = [i for i, l in enumerate(layers) if 'vapour' in l.controls]
    if indoor_c > outdoor_c and insulation_indices and vapour_indices and min(vapour_indices) > max(insulation_indices):
        warnings.append('Vapour control is outside the thermal layer under heating conditions; review the assembly.')
    return {'rsi': rsi, 'interfaces': interfaces, 'missing_controls': missing, 'warnings': warnings}
