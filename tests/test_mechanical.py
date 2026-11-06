"""Hand checks catch missing heat terms, Darcy/K factors and FU table misuse."""
import copy
import importlib
import importlib.util
import json
from pathlib import Path

import pytest


def mechanical():
    assert importlib.util.find_spec('renovation.mechanical') is not None, 'mechanical calculation module is missing'
    return importlib.import_module('renovation.mechanical')


def design():
    return {'heating_indoor_c': 20, 'heating_outdoor_c': -10,
            'cooling_indoor_c': 24, 'cooling_outdoor_c': 34,
            'cooling_indoor_humidity_ratio_kg_kg': 0.009,
            'cooling_outdoor_humidity_ratio_kg_kg': 0.014,
            'heating_supply_delta_k': 20, 'cooling_supply_delta_k': 10}


def room():
    return {'name': 'Hand room', 'volume_m3': 100, 'infiltration_ach': 0.36,
            'ventilation_m3_s': 0.02,
            'surfaces': [{'name': 'Envelope', 'area_m2': 20, 'u_w_m2k': 0.5}],
            'internal_sensible_w': 100, 'internal_latent_w': 50,
            'solar': [{'name': 'Window', 'area_m2': 2, 'irradiance_w_m2': 500,
                       'shgc': 0.5, 'shading_factor': 0.8}]}


def duct_settings():
    return {'available_diameters_m': [0.1, 0.2, 0.3], 'target_friction_pa_m': 1,
            'max_velocity_m_s': 4, 'roughness_m': 0.00009}


def duct():
    return {'name': 'Hand duct', 'airflow_m3_s': 0.05, 'length_m': 10,
            'fittings': [{'name': 'Two bends', 'k': 0.5, 'count': 2}]}


def plumbing_settings():
    return {'available_inside_diameters_m': [0.015, 0.02, 0.025, 0.032],
            'max_velocity_m_s': 2}


def branch():
    return {'name': 'Kitchen', 'system': 'flush_tank', 'load_scope': 'combined',
            'fixtures': [{'type': 'kitchen_sink_private', 'count': 1},
                         {'type': 'dishwasher_private', 'count': 1}]}


def test_room_hand_balance_and_separate_outdoor_air_terms():
    result = mechanical().room_load(room(), design())
    # UA=10 W/K; infiltration 0.36*100/3600=.01 m3/s; rho*cp=1207.2.
    assert result['transmission_heating_w'] == pytest.approx(300)
    assert result['infiltration_heating_w'] == pytest.approx(362.16)
    assert result['ventilation_heating_w'] == pytest.approx(724.32)
    assert result['heating_w'] == pytest.approx(1386.48)
    assert result['solar_sensible_w'] == pytest.approx(400)
    assert result['cooling_sensible_w'] == pytest.approx(962.16)
    # rho*Q*hfg*dW = 1.2*.03*2501000*.005 = 450.18 W.
    assert result['outdoor_air_latent_w'] == pytest.approx(450.18)
    assert result['cooling_latent_w'] == pytest.approx(500.18)
    assert result['cooling_total_w'] == pytest.approx(1462.34)
    assert result['heating_airflow_m3_s'] == pytest.approx(0.05742544731610338)
    assert result['cooling_airflow_m3_s'] == pytest.approx(0.07970178926441352)


def test_heating_does_not_take_credit_for_internal_or_solar_gains():
    data = room()
    data['internal_sensible_w'] = 5000
    assert mechanical().room_load(data, design())['heating_w'] == pytest.approx(1386.48)
    climate = design()
    climate['cooling_outdoor_humidity_ratio_kg_kg'] = 0.004
    assert mechanical().room_load(room(), climate)['outdoor_air_latent_w'] == 0


def test_duct_laminar_hand_check_includes_explicit_fittings():
    # D=.1, Q=.0001 => v=.0127324, Re=84.41; f=64/Re=.75817.
    data = {'name': 'Laminar', 'airflow_m3_s': 0.0001, 'length_m': 10,
            'selected_diameter_m': 0.1, 'fittings': [{'name': 'Loss', 'k': 2, 'count': 1}]}
    result = mechanical().duct_run(data, duct_settings())
    assert result['velocity_m_s'] == pytest.approx(0.0127323954473516)
    assert result['friction_pa_m'] == pytest.approx(0.000737460344310606)
    assert result['fittings_pressure_pa'] == pytest.approx(0.000194536672593)
    assert result['pressure_drop_pa'] == pytest.approx(0.00756914011569935)


def test_equal_friction_selects_first_available_meeting_both_limits():
    result = mechanical().duct_run(duct(), duct_settings())
    assert result['recommended_diameter_m'] == 0.2
    assert result['selected_diameter_m'] == 0.2
    assert result['velocity_m_s'] == pytest.approx(1.59154943091895)
    # Colebrook iteration: Re=21103.42, eps/D=.00045 => f=.0265315.
    assert result['darcy_factor'] == pytest.approx(0.0265315, rel=2e-5)
    assert result['pressure_drop_pa'] == pytest.approx(3.53597, rel=2e-5)
    assert result['warnings'] == []


def test_duct_undersized_selection_and_exhausted_catalog_warn():
    data = duct()
    data['selected_diameter_m'] = 0.1
    result = mechanical().duct_run(data, duct_settings())
    assert result['recommended_diameter_m'] == 0.2
    assert any('velocity' in w for w in result['warnings'])
    assert any('friction' in w for w in result['warnings'])
    data['airflow_m3_s'] = 2
    result = mechanical().duct_run(data, duct_settings())
    assert result['recommended_diameter_m'] is None
    assert any('available' in w for w in result['warnings'])


def test_fixture_units_use_published_next_row_not_linear_conversion():
    result = mechanical().plumbing_branch(branch(), plumbing_settings())
    assert result['fixture_units'] == pytest.approx(2.8)
    assert result['table_fixture_units'] == 3
    assert result['demand_us_gpm'] == 6.5
    assert result['demand_l_s'] == pytest.approx(0.4100862766)
    assert result['recommended_inside_diameter_m'] == 0.02
    assert result['velocity_m_s'] == pytest.approx(1.305345160300805)


def test_plumbing_undersized_and_exhausted_catalog_warn():
    data = branch()
    data['selected_inside_diameter_m'] = 0.015
    result = mechanical().plumbing_branch(data, plumbing_settings())
    assert any('velocity' in w for w in result['warnings'])
    settings = plumbing_settings()
    settings['available_inside_diameters_m'] = [0.01]
    result = mechanical().plumbing_branch(branch(), settings)
    assert result['recommended_inside_diameter_m'] is None
    assert any('available' in w for w in result['warnings'])


@pytest.mark.parametrize('fixture,count,want_fu,want_gpm', [
    ('kitchen_sink_private', 1, 1.4, 5),
    ('lavatory_private', 10, 7, 11.8),
    ('bathroom_group_private_flush_tank', 5, 18, 18.8),
])
def test_fixture_table_rows(fixture, count, want_fu, want_gpm):
    data = branch()
    data['fixtures'] = [{'type': fixture, 'count': count}]
    result = mechanical().plumbing_branch(data, plumbing_settings())
    assert result['fixture_units'] == pytest.approx(want_fu)
    assert result['demand_us_gpm'] == want_gpm


@pytest.mark.parametrize('fixture,count', [('lavatory_private', 1), ('kitchen_sink_private', 15)])
def test_no_fixture_demand_extrapolation_below_or_above_bounded_table(fixture, count):
    data = branch()
    data['fixtures'] = [{'type': fixture, 'count': count}]
    with pytest.raises(ValueError, match='1.*20'):
        mechanical().plumbing_branch(data, plumbing_settings())


@pytest.mark.parametrize('key,value', [('volume_m3', -1), ('infiltration_ach', float('nan')),
                                      ('ventilation_m3_s', float('inf')), ('internal_latent_w', -1),
                                      ('internal_sensible_w', True), ('volume_ft3', 100)])
def test_room_rejects_bad_or_mislabeled_inputs(key, value):
    data = room()
    data[key] = value
    with pytest.raises(ValueError):
        mechanical().room_load(data, design())


@pytest.mark.parametrize('case', ['negative_flow', 'negative_fitting', 'nan_diameter', 'unknown_size',
                                  'bad_system', 'unknown_fixture', 'fractional_count', 'hot_scope'])
def test_duct_and_plumbing_invalid_inputs(case):
    data, settings = duct(), duct_settings()
    if case == 'negative_flow':
        data['airflow_m3_s'] = -1
    elif case == 'negative_fitting':
        data['fittings'][0]['k'] = -0.1
    elif case == 'nan_diameter':
        settings['available_diameters_m'] = [float('nan')]
    elif case == 'unknown_size':
        data['selected_diameter_m'] = 0.123
    else:
        data, settings = branch(), plumbing_settings()
        if case == 'bad_system': data['system'] = 'flush_valve'
        if case == 'unknown_fixture': data['fixtures'][0]['type'] = 'imaginary'
        if case == 'fractional_count': data['fixtures'][0]['count'] = 0.5
        if case == 'hot_scope': data['load_scope'] = 'hot'
    with pytest.raises(ValueError):
        if case in ['negative_flow', 'negative_fitting', 'nan_diameter', 'unknown_size']:
            mechanical().duct_run(data, settings)
        else:
            mechanical().plumbing_branch(data, settings)


def test_run_committed_example_writes_finite_reports_and_rejects_bad_units(tmp_path):
    module = mechanical()
    source = json.loads(Path('examples/mechanical.json').read_text())
    result = module.run(source, tmp_path)
    encoded = json.dumps(result, allow_nan=False)
    assert json.loads((tmp_path / 'mechanical.json').read_text()) == json.loads(encoded)
    for filename in ['room-loads.csv', 'ducts.csv', 'plumbing.csv']:
        assert (tmp_path / filename).stat().st_size > 30
    assert result['rooms'] and result['ducts'] and result['plumbing']
    assert result['scope']
    invalid = copy.deepcopy(source)
    invalid['units']['airflow'] = 'cfm'
    with pytest.raises(ValueError, match='units'):
        module.run(invalid, tmp_path)


def test_extreme_integer_rejected_as_value_error_not_overflow():
    data = room()
    data['volume_m3'] = 10 ** 1000
    with pytest.raises(ValueError):
        mechanical().room_load(data, design())


def test_exact_twenty_fu_boundary_is_supported():
    data = branch()
    data['fixtures'] = [
        {'type': 'water_closet_private_flush_tank', 'count': 4},
        {'type': 'kitchen_sink_private', 'count': 8},
    ]
    result = mechanical().plumbing_branch(data, plumbing_settings())
    assert result['fixture_units'] == 20
    assert result['table_fixture_units'] == 20
    assert result['demand_us_gpm'] == 19.6


def test_occupancy_adds_explicit_sensible_and_latent_gains_separately():
    data = room()
    data['occupancy'] = {'count': 2, 'sensible_w_person': 75, 'latent_w_person': 55}
    result = mechanical().room_load(data, design())
    assert result['occupancy_count'] == 2
    assert result['occupancy_sensible_w'] == 150
    assert result['occupancy_latent_w'] == 110
    assert result['internal_sensible_w'] == 100
    assert result['internal_latent_w'] == 50
    assert result['cooling_sensible_w'] == pytest.approx(1112.16)
    assert result['cooling_latent_w'] == pytest.approx(610.18)
    assert result['cooling_total_w'] == pytest.approx(1722.34)
    assert result['heating_w'] == pytest.approx(1386.48)


@pytest.mark.parametrize('occupancy', [
    {'count': -1, 'sensible_w_person': 75, 'latent_w_person': 55},
    {'count': 1.5, 'sensible_w_person': 75, 'latent_w_person': 55},
    {'count': 1, 'sensible_w_person': float('nan'), 'latent_w_person': 55},
    {'count': 1, 'sensible_w_person': 75, 'latent_w_person': -1},
    {'count': 1, 'sensible_btu_h_person': 75, 'latent_w_person': 55},
])
def test_occupancy_rejects_bad_count_gains_or_units(occupancy):
    data = room()
    data['occupancy'] = occupancy
    with pytest.raises(ValueError):
        mechanical().room_load(data, design())
