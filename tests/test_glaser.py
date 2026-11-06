import math
import pytest
from renovation.envelope import Layer, analyze, saturation_pressure


def test_single_plane_glaser_hand_balance():
    # Equal thermal and diffusion resistances, cold interface at 0 C.
    layers = [Layer('insulation', .1, .05, 100), Layer('sheathing', .1, .05, 100)]
    result = analyze(layers, 20, -20, .8, .8)
    ps = saturation_pressure(0)
    pi, po = .8 * saturation_pressure(20), .8 * saturation_pressure(-20)
    expected = (100 * (pi - ps) - 100 * (ps - po)) * 86400e-9
    assert result['condensation_g_m2_day'] == pytest.approx(expected)
    assert result['interfaces'][0]['glaser_pressure_pa'] == pytest.approx(ps)
    assert result['interfaces'][0]['condensation_g_m2_day'] == pytest.approx(expected)


def test_no_condensation_and_diffusion_mass_balance():
    r = analyze([Layer('a', .1, .1, 100), Layer('b', .1, .1, 100)], 20, 10, .2, .2)
    assert r['condensation_g_m2_day'] == 0
    assert r['diffusion_in_ng_m2_s'] == pytest.approx(r['diffusion_out_ng_m2_s'])


def test_multiple_planes_obey_saturation_and_mass_balance():
    layers = [Layer(str(i), .05, .05, p) for i, p in enumerate([1000, 100, 300, 100])]
    r = analyze(layers, 22, -20, .9, .7)
    assert all(i['glaser_pressure_pa'] <= i['saturation_pressure_pa'] + 1e-7 for i in r['interfaces'])
    assert all(i['condensation_g_m2_day'] >= 0 for i in r['interfaces'])
    assert r['condensation_g_m2_day'] == pytest.approx((r['diffusion_in_ng_m2_s']-r['diffusion_out_ng_m2_s'])*86400e-9)


def test_control_placement_and_continuity():
    layers = [Layer('insulation', .1, .04, 100, ('thermal',)), Layer('outside', .01, .1, 1, ('vapour', 'air', 'water'), False)]
    r = analyze(layers, 20, -10, .4, .8)
    assert r['missing_controls'] == ['air', 'vapour', 'water']
    assert any('continuous' in w for w in r['warnings'])
    assert any('outside' in w for w in r['warnings'])


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), -1, 1.01])
def test_bad_relative_humidity(bad):
    with pytest.raises(ValueError):
        analyze([Layer('a', 1, 1, 1)], 20, -10, bad, .8)


def test_rejects_bad_continuity_and_duplicate_names():
    with pytest.raises(ValueError):
        analyze([Layer('a', 1, 1, 1, continuous='yes')], 20, -10, .4, .8)
    with pytest.raises(ValueError):
        analyze([Layer('a', 1, 1, 1), Layer('a', 1, 1, 1)], 20, -10, .4, .8)


def test_generated_ontario_examples(tmp_path):
    import json
    from pathlib import Path
    from renovation.envelope import run
    data = json.loads(Path('examples/walls.json').read_text())
    result = run(data, tmp_path)
    assert len(result['assemblies']) == 3
    assert all(a['rsi'] > 0 for a in result['assemblies'])
    assert (tmp_path/'envelope.json').is_file()


def test_extreme_permeance_is_rejected_before_zero_width_segment():
    with pytest.raises(ValueError):
        analyze([Layer('a', .1, .1, 1), Layer('b', .1, .1, 1e300)], 20, -10, .4, .8)


@pytest.mark.parametrize('bad', [True, '100', 10**1000], ids=['boolean', 'string', 'integer-overflow'])
def test_properties_require_representable_real_numbers(bad):
    with pytest.raises(ValueError):
        analyze([Layer('a', .1, .1, bad)], 20, -10, .4, .8)
