"""Bounded SI mechanical studies; see docs/mechanical.md for sources and limits."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

AIR_DENSITY_KG_M3 = 1.2
AIR_CP_J_KG_K = 1006.0
AIR_DYNAMIC_VISCOSITY_PA_S = 1.81e-5
LATENT_HEAT_J_KG = 2501000.0
US_GALLON_LITRES = 3.785411784
UNITS = {'length': 'm', 'area': 'm2', 'volume': 'm3', 'temperature': 'degC',
         'temperature_difference': 'K', 'airflow': 'm3/s', 'power': 'W',
         'u_value': 'W/(m2*K)', 'pressure': 'Pa', 'water_flow': 'L/s',
         'humidity_ratio': 'kg/kg', 'irradiance': 'W/m2'}
SCOPE = ('Synthetic educational comparison only; no Ontario compliance, permit, '
         'equipment or construction selection. Cooling is an instantaneous balance, '
         'ducts are independent round runs, and plumbing is a velocity screen.')
REFERENCES = [
    'https://handbook.ashrae.org/Handbooks/F21/SI/f21_ch17/F21_Ch17_si.aspx',
    'https://handbook.ashrae.org/Handbooks/F21/SI/f21_ch21/f21_ch21_si.aspx',
    'https://media.iccsafe.org/NC/2012_NC_Plumbing.pdf#page=142',
]
# ICC 2012 NC Plumbing, E103.3(2), combined column, private occupancy only.
FIXTURE_UNITS = {'kitchen_sink_private': 1.4, 'dishwasher_private': 1.4,
                 'lavatory_private': 0.7, 'shower_private': 1.4,
                 'bathtub_private': 1.4, 'laundry_tray_private': 1.4,
                 'washing_machine_8lb_private': 1.4,
                 'water_closet_private_flush_tank': 2.2,
                 'bathroom_group_private_flush_tank': 3.6}
# E103.3(3), flush-tank gpm column only. This deliberately ends at 20 FU.
DEMAND_GPM = (3.0, 5.0, 6.5, 8.0, 9.4, 10.7, 11.8, 12.8, 13.7, 14.6,
              15.4, 16.0, 16.5, 17.0, 17.5, 18.0, 18.4, 18.8, 19.2, 19.6)


def _fields(value, required, optional=()):
    if not isinstance(value, dict):
        raise ValueError('expected an input object')
    if set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ValueError(f'input fields must include {sorted(required)}; optional {sorted(optional)}')


def _number(value, label, low, high, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{label} must be a finite number')
    if not low <= value <= high or not math.isfinite(value) or (positive and value == 0):
        raise ValueError(f'{label} outside supported range {low} to {high}')
    return float(value)


def _name(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError('name must be a nonempty string of at most 200 characters')
    return value


def _items(value, label, *, empty=False):
    if not isinstance(value, list) or len(value) > 1000 or (not value and not empty):
        raise ValueError(f'{label} must be a list of {0 if empty else 1} to 1000 entries')
    return value


def _diameters(values):
    result = [_number(d, 'inside diameter_m', 0.005, 3) for d in _items(values, 'diameters')]
    if len(set(result)) != len(result):
        raise ValueError('diameters must be unique')
    return sorted(result)


def _count(value):
    result = _number(value, 'count', 1, 1000)
    if result != int(result):
        raise ValueError('count must be an integer')
    return int(result)


def room_load(room, design):
    """Return room W and sensible supply-air m3/s from explicitly named SI fields."""
    _fields(design, ('heating_indoor_c', 'heating_outdoor_c', 'cooling_indoor_c',
                     'cooling_outdoor_c', 'cooling_indoor_humidity_ratio_kg_kg',
                     'cooling_outdoor_humidity_ratio_kg_kg', 'heating_supply_delta_k',
                     'cooling_supply_delta_k'))
    temperatures = {k: _number(design[k], k, -50, 60) for k in
                    ('heating_indoor_c', 'heating_outdoor_c', 'cooling_indoor_c', 'cooling_outdoor_c')}
    heating_dt = temperatures['heating_indoor_c'] - temperatures['heating_outdoor_c']
    cooling_dt = temperatures['cooling_outdoor_c'] - temperatures['cooling_indoor_c']
    if heating_dt < 0 or cooling_dt < 0:
        raise ValueError('heating/cooling indoor and outdoor temperatures have reversed order')
    wi = _number(design['cooling_indoor_humidity_ratio_kg_kg'], 'indoor humidity ratio', 0, 0.03)
    wo = _number(design['cooling_outdoor_humidity_ratio_kg_kg'], 'outdoor humidity ratio', 0, 0.03)
    supply_heat = _number(design['heating_supply_delta_k'], 'heating supply delta K', 1, 40)
    supply_cool = _number(design['cooling_supply_delta_k'], 'cooling supply delta K', 1, 30)
    _fields(room, ('name', 'volume_m3', 'infiltration_ach', 'ventilation_m3_s', 'surfaces',
                   'internal_sensible_w', 'internal_latent_w', 'solar'), ('occupancy',))
    name = _name(room['name'])
    volume = _number(room['volume_m3'], 'volume_m3', 0, 3000, positive=True)
    ach = _number(room['infiltration_ach'], 'infiltration_ach', 0, 5)
    ventilation = _number(room['ventilation_m3_s'], 'ventilation_m3_s', 0, 0.5)
    internal_sensible = _number(room['internal_sensible_w'], 'internal_sensible_w', 0, 5000)
    internal_latent = _number(room['internal_latent_w'], 'internal_latent_w', 0, 5000)
    occupancy = room.get('occupancy', {'count': 0, 'sensible_w_person': 0, 'latent_w_person': 0})
    _fields(occupancy, ('count', 'sensible_w_person', 'latent_w_person'))
    people = _number(occupancy['count'], 'occupancy count', 0, 100)
    if people != int(people):
        raise ValueError('occupancy count must be a nonnegative integer')
    occupancy_sensible = int(people) * _number(occupancy['sensible_w_person'], 'sensible_w_person', 0, 250)
    occupancy_latent = int(people) * _number(occupancy['latent_w_person'], 'latent_w_person', 0, 250)
    ua = 0.0
    for surface in _items(room['surfaces'], 'surfaces'):
        _fields(surface, ('name', 'area_m2', 'u_w_m2k'))
        _name(surface['name'])
        ua += (_number(surface['area_m2'], 'surface area_m2', 0, 1000, positive=True)
               * _number(surface['u_w_m2k'], 'u_w_m2k', 0, 15, positive=True))
    solar = 0.0
    for window in _items(room['solar'], 'solar', empty=True):
        _fields(window, ('name', 'area_m2', 'irradiance_w_m2', 'shgc', 'shading_factor'))
        _name(window['name'])
        solar += (_number(window['area_m2'], 'solar area_m2', 0, 300)
                  * _number(window['irradiance_w_m2'], 'irradiance_w_m2', 0, 1400)
                  * _number(window['shgc'], 'shgc', 0, 1)
                  * _number(window['shading_factor'], 'shading_factor', 0, 1))
    infiltration = volume * ach / 3600
    rho_cp = AIR_DENSITY_KG_M3 * AIR_CP_J_KG_K
    transmission_heating = ua * heating_dt
    infiltration_heating = rho_cp * infiltration * heating_dt
    ventilation_heating = rho_cp * ventilation * heating_dt
    heating = transmission_heating + infiltration_heating + ventilation_heating
    transmission_cooling = ua * cooling_dt
    infiltration_cooling = rho_cp * infiltration * cooling_dt
    ventilation_cooling = rho_cp * ventilation * cooling_dt
    sensible = transmission_cooling + infiltration_cooling + ventilation_cooling + internal_sensible + occupancy_sensible + solar
    outdoor_latent = AIR_DENSITY_KG_M3 * LATENT_HEAT_J_KG * (infiltration + ventilation) * max(wo - wi, 0)
    latent = outdoor_latent + internal_latent + occupancy_latent
    return {'name': name, 'ua_w_k': ua, 'infiltration_m3_s': infiltration,
            'ventilation_m3_s': ventilation, 'transmission_heating_w': transmission_heating,
            'infiltration_heating_w': infiltration_heating, 'ventilation_heating_w': ventilation_heating,
            'heating_w': heating, 'transmission_cooling_w': transmission_cooling,
            'infiltration_cooling_w': infiltration_cooling, 'ventilation_cooling_w': ventilation_cooling,
            'internal_sensible_w': internal_sensible, 'internal_latent_w': internal_latent,
            'occupancy_count': int(people), 'occupancy_sensible_w': occupancy_sensible,
            'occupancy_latent_w': occupancy_latent,
            'solar_sensible_w': solar, 'cooling_sensible_w': sensible,
            'outdoor_air_latent_w': outdoor_latent, 'cooling_latent_w': latent,
            'cooling_total_w': sensible + latent,
            'heating_airflow_m3_s': heating / (rho_cp * supply_heat),
            'cooling_airflow_m3_s': sensible / (rho_cp * supply_cool),
            'warnings': ['Cooling is an instantaneous gain screen; latent capacity and hourly peaks require separate design.']}


def _duct_physics(flow, diameter, length, roughness, fitting_k):
    velocity = flow / (math.pi * diameter ** 2 / 4)
    reynolds = AIR_DENSITY_KG_M3 * velocity * diameter / AIR_DYNAMIC_VISCOSITY_PA_S
    warnings = []
    if reynolds < 2300:
        factor = 64 / reynolds
    else:
        # Solve Colebrook in x=1/sqrt(f), with fixed iterations and tight convergence.
        x = 7.0
        for _ in range(100):
            updated = -2 * math.log10(roughness / (3.7 * diameter) + 2.51 * x / reynolds)
            if abs(updated - x) < 1e-12:
                x = updated
                break
            x = updated
        factor = 1 / x ** 2
        if reynolds < 4000:
            warnings.append('Reynolds number is in the 2300–4000 transition range; friction is uncertain.')
    velocity_pressure = AIR_DENSITY_KG_M3 * velocity ** 2 / 2
    friction = factor * velocity_pressure / diameter
    return {'velocity_m_s': velocity, 'reynolds_number': reynolds, 'darcy_factor': factor,
            'friction_pa_m': friction, 'straight_pressure_pa': friction * length,
            'fittings_pressure_pa': fitting_k * velocity_pressure,
            'pressure_drop_pa': friction * length + fitting_k * velocity_pressure,
            'warnings': warnings}


def duct_run(run, settings):
    """Size an independent round run at a common straight-duct friction target."""
    _fields(settings, ('available_diameters_m', 'target_friction_pa_m', 'max_velocity_m_s', 'roughness_m'))
    diameters = _diameters(settings['available_diameters_m'])
    target = _number(settings['target_friction_pa_m'], 'target_friction_pa_m', 0, 10, positive=True)
    limit = _number(settings['max_velocity_m_s'], 'max_velocity_m_s', 0, 30, positive=True)
    roughness = _number(settings['roughness_m'], 'roughness_m', 0, 0.001)
    if roughness / min(diameters) > 0.05:
        raise ValueError('relative roughness exceeds supported 0.05')
    _fields(run, ('name', 'airflow_m3_s', 'length_m', 'fittings'), ('selected_diameter_m',))
    name = _name(run['name'])
    flow = _number(run['airflow_m3_s'], 'airflow_m3_s', 1e-8, 10)
    length = _number(run['length_m'], 'length_m', 0, 1000)
    fitting_k = 0.0
    for fitting in _items(run['fittings'], 'fittings', empty=True):
        _fields(fitting, ('name', 'k', 'count'))
        _name(fitting['name'])
        fitting_k += _number(fitting['k'], 'fitting k', 0, 100) * _count(fitting['count'])
    trials = {d: _duct_physics(flow, d, length, roughness, fitting_k) for d in diameters}
    recommendation = next((d for d, p in trials.items()
                           if p['friction_pa_m'] <= target and p['velocity_m_s'] <= limit), None)
    selected = _number(run.get('selected_diameter_m', recommendation or diameters[-1]),
                       'selected_diameter_m', 0.005, 3)
    if selected not in trials:
        raise ValueError('selected duct diameter must be one of the available sizes')
    result = trials[selected]
    warnings = result['warnings']
    if recommendation is None:
        warnings.append('No available diameter meets both friction and velocity limits; largest is only a fallback.')
    if result['friction_pa_m'] > target:
        warnings.append('Selected duct exceeds the target friction rate; undersized for this target.')
    if result['velocity_m_s'] > limit:
        warnings.append('Selected duct exceeds the velocity limit; undersized for this limit.')
    return {'name': name, 'airflow_m3_s': flow, 'length_m': length,
            'recommended_diameter_m': recommendation, 'selected_diameter_m': selected,
            'total_fitting_k': fitting_k, 'target_friction_pa_m': target,
            'max_velocity_m_s': limit, **result}


def plumbing_branch(branch, settings):
    """Use combined WSFU table rows 1–20 then choose inside diameter by velocity."""
    _fields(settings, ('available_inside_diameters_m', 'max_velocity_m_s'))
    diameters = _diameters(settings['available_inside_diameters_m'])
    limit = _number(settings['max_velocity_m_s'], 'max_velocity_m_s', 0, 5, positive=True)
    _fields(branch, ('name', 'system', 'load_scope', 'fixtures'), ('selected_inside_diameter_m',))
    name = _name(branch['name'])
    if branch['system'] != 'flush_tank' or branch['load_scope'] != 'combined':
        raise ValueError('only combined private-fixture flush_tank systems are supported')
    fixture_units = 0.0
    for fixture in _items(branch['fixtures'], 'fixtures'):
        _fields(fixture, ('type', 'count'))
        kind = fixture['type']
        if not isinstance(kind, str) or kind not in FIXTURE_UNITS:
            raise ValueError('unsupported fixture type; no assumed analogue permitted')
        fixture_units += FIXTURE_UNITS[kind] * _count(fixture['count'])
    # Rounding addresses floating arithmetic only, not an out-of-table load.
    fixture_units = round(fixture_units, 10)
    if not 1 <= fixture_units <= 20:
        raise ValueError('combined fixture-unit total must lie within published subset 1 to 20 FU')
    table_fu = math.ceil(fixture_units)
    gpm = DEMAND_GPM[table_fu - 1]
    flow_l_s = gpm * US_GALLON_LITRES / 60
    velocities = {d: flow_l_s / 1000 / (math.pi * d ** 2 / 4) for d in diameters}
    recommendation = next((d for d, velocity in velocities.items() if velocity <= limit), None)
    selected = _number(branch.get('selected_inside_diameter_m', recommendation or diameters[-1]),
                       'selected_inside_diameter_m', 0.005, 3)
    if selected not in velocities:
        raise ValueError('selected pipe inside diameter must be one of the available sizes')
    warnings = []
    if recommendation is None:
        warnings.append('No available pipe inside diameter meets velocity limit; largest is only a fallback.')
    if velocities[selected] > limit:
        warnings.append('Selected pipe exceeds velocity limit; undersized for this limit.')
    return {'name': name, 'fixture_units': fixture_units, 'table_fixture_units': table_fu,
            'demand_us_gpm': gpm, 'demand_l_s': flow_l_s,
            'recommended_inside_diameter_m': recommendation, 'selected_inside_diameter_m': selected,
            'velocity_m_s': velocities[selected], 'max_velocity_m_s': limit,
            'warnings': warnings,
            'limitation': 'Velocity-only pipe screen; supply pressure, elevation, friction, meter and fixture pressure are not checked.'}


def run(input_dict, output_dir):
    """Validate all inputs before writing JSON and three CSV reports; return dict."""
    _fields(input_dict, ('units', 'design', 'rooms', 'duct_settings', 'ducts',
                         'plumbing_settings', 'plumbing'), ('study_name',))
    if input_dict['units'] != UNITS:
        raise ValueError(f'units must exactly match the documented SI map: {UNITS}')
    name = _name(input_dict.get('study_name', 'Synthetic mechanical study'))
    rooms = [room_load(r, input_dict['design']) for r in _items(input_dict['rooms'], 'rooms')]
    ducts = [duct_run(d, input_dict['duct_settings']) for d in _items(input_dict['ducts'], 'ducts')]
    plumbing = [plumbing_branch(p, input_dict['plumbing_settings']) for p in _items(input_dict['plumbing'], 'plumbing')]
    for section in (rooms, ducts, plumbing):
        if len({item['name'] for item in section}) != len(section):
            raise ValueError('names must be unique within each section')
    result = {'study_name': name, 'scope': SCOPE, 'units': dict(UNITS),
              'assumptions': {'air_density_kg_m3': AIR_DENSITY_KG_M3,
                              'air_specific_heat_j_kg_k': AIR_CP_J_KG_K,
                              'air_dynamic_viscosity_pa_s': AIR_DYNAMIC_VISCOSITY_PA_S,
                              'water_latent_heat_j_kg': LATENT_HEAT_J_KG,
                              'outdoor_air': 'Infiltration and ventilation are additive, no heat recovery; avoid double counting.',
                              'occupancy': 'Explicit count times sensible/latent W per person; other internal gains exclude occupants.',
                              'solar': 'Explicit irradiance * glazing area * SHGC * shading factor; instantaneous only.',
                              'fittings': 'User-assigned K referenced to the selected run velocity, not a geometry lookup.',
                              'plumbing': 'ICC 2012 NC E103.3(2)/(3), combined private flush-tank subset 1–20 FU; round up to next row.'},
              'references': list(REFERENCES), 'rooms': rooms, 'ducts': ducts, 'plumbing': plumbing,
              'totals': {key: sum(r[key] for r in rooms) for key in
                         ('heating_w', 'cooling_sensible_w', 'cooling_latent_w', 'cooling_total_w')}}
    encoded = json.dumps(result, indent=2, allow_nan=False) + '\n'
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'mechanical.json').write_text(encoded, encoding='utf-8')
    for filename, rows in [('room-loads.csv', rooms), ('ducts.csv', ducts), ('plumbing.csv', plumbing)]:
        with (output / filename).open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows({key: '; '.join(value) if isinstance(value, list) else value
                              for key, value in row.items()} for row in rows)
    return result
