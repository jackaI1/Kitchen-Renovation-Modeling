"""Hand checks catch load omission, wrong phase factors and unsafe sizing."""
import importlib
import json
import math
from pathlib import Path

import ezdxf
import pytest


def module():
    # A missing feature fails as an assertion before implementation exists.
    assert importlib.util.find_spec("renovation.electrical"), "electrical study missing"
    return importlib.import_module("renovation.electrical")


def system():
    return {
        "voltage_ll_v": 208,
        "transformer": {"rating_kva": 75, "impedance_pct": 5, "x_r_ratio": 3},
        "panels": [
            {"id": "MAIN", "parent": None, "breaker_a": 100,
             "interrupt_ka": 10, "length_m": 0},
            {"id": "SUB", "parent": "MAIN", "breaker_a": 40,
             "interrupt_ka": 10, "length_m": 20},
        ],
        "circuits": [
            {"id": "oven", "panel": "MAIN", "load_va": 3600,
             "demand_factor": 1, "continuous": False, "power_factor": 1,
             "phases": 1, "voltage_v": 208, "length_m": 10,
             "breaker_a": 20, "interrupt_ka": 10},
            {"id": "lights", "panel": "SUB", "load_va": 2400,
             "demand_factor": 0.5, "continuous": True, "power_factor": 1,
             "phases": 1, "voltage_v": 208 / math.sqrt(3), "length_m": 30,
             "breaker_a": 15, "interrupt_ka": 10},
        ],
    }


def room():
    return {"width_m": 4, "depth_m": 4, "height_m": 3,
            "workplane_m": 1, "grid_x_m": [0, 2, 4], "grid_y_m": [2],
            "luminaires": [{"x_m": 2, "y_m": 2, "z_m": 3,
                            "candela": [[0, 400], [45, 200], [90, 0]]}]}


def test_connected_demand_and_continuous_load_reach_both_panels():
    out = module().calculate(system())
    assert out["panels"]["MAIN"]["connected_va"] == 6000
    assert out["panels"]["MAIN"]["demand_va"] == 4800
    assert out["panels"]["MAIN"]["design_current_a"] == pytest.approx(14.156184485)
    assert out["panels"]["SUB"]["demand_va"] == 1200
    assert out["circuits"]["lights"]["design_current_a"] == pytest.approx(24.981502032)
    assert out["circuits"]["lights"]["connected_current_a"] == pytest.approx(19.9852016258)


def test_lagging_loads_aggregate_real_and_reactive_power():
    data = system()
    data["circuits"][0].update(load_va=3000, power_factor=0.8)
    data["circuits"][1].update(load_va=4000, demand_factor=1, power_factor=1,
                                 continuous=False, breaker_a=40)
    out = module().calculate(data)["panels"]["MAIN"]
    # S=(2400+j1800)+4000: sum nameplates 7000VA, resultant 6648.308VA.
    assert out["connected_va"] == 7000
    assert out["demand_va"] == 7000
    assert out["demand_kw"] == pytest.approx(6.4)
    assert out["demand_kvar"] == pytest.approx(1.8)
    assert out["demand_current_a"] == pytest.approx(18.453857911)


def test_selects_branch_and_feeder_against_device_and_derating():
    e = module()
    assert e.select_conductor(10, 20)["awg"] == "12"
    assert e.select_conductor(32, 40)["awg"] == "8"
    assert e.select_conductor(32, 40, derating_factor=0.8)["awg"] == "8"
    assert e.select_conductor(32, 40, derating_factor=0.7)["awg"] == "6"
    out = e.calculate(system())
    assert out["circuits"]["oven"]["conductor"]["awg"] == "12"
    assert out["panels"]["SUB"]["conductor"]["awg"] == "8"
    assert out["panels"]["MAIN"]["conductor"]["awg"] == "3"
    with pytest.raises(ValueError, match="table"):
        e.select_conductor(500, 500)


def test_voltage_drop_uses_actual_conductor_and_one_way_length():
    e = module()
    # 90 C copper 0.02369 ohm mm2/m, #12 area 3.31 mm2, round trip 60m.
    d = e.voltage_drop(10, 30, 120, "12", phases=1, power_factor=1)
    assert d["volts"] == pytest.approx(4.2942598187)
    assert d["percent"] == pytest.approx(3.5785498489)
    assert e.voltage_drop(10, 30, 208, "12", phases=3)["volts"] == pytest.approx(3.718938096)
    data = system()
    data["circuits"][1].update({"conductor_awg": "14", "length_m": 100,
                                 "load_va": 4800, "interrupt_ka": 0.1})
    out = e.calculate(data)
    branch = out["circuits"]["lights"]
    assert branch["conductor"]["awg"] == "14"
    assert {"device_overload", "conductor_undersized", "voltage_drop_exceeded",
            "interrupt_rating_exceeded"} <= set(branch["warnings"])
    assert branch["voltage_drop"]["percent"] > 30


def test_complex_radial_fault_impedance_and_interrupt_location():
    out = module().calculate(system())
    # |Zt|=208^2/75000*0.05=0.0288426667 ohm; transformer X/R=3.
    assert out["panels"]["MAIN"]["fault_current_a"] == pytest.approx(4163.58367204)
    # #8 8.37mm2: cable cold R=.01851*20/8.37, X=.000096*20.
    assert out["panels"]["SUB"]["impedance_ohm"]["r"] == pytest.approx(0.053350242727)
    assert out["panels"]["SUB"]["fault_current_a"] == pytest.approx(1973.257853)
    assert out["panels"]["SUB"]["fault_current_a"] < out["panels"]["MAIN"]["fault_current_a"]
    data = system()
    data["panels"][1]["interrupt_ka"] = 3
    # Feeder breaker sits at MAIN, so 3kA fails even though SUB fault <3kA.
    assert "interrupt_rating_exceeded" in module().calculate(data)["panels"]["SUB"]["warnings"]


def test_lighting_inverse_square_cosine_and_interpolated_intensity():
    e = module()
    out = e.lighting(room())
    values = [p["lux"] for p in out["points"]]
    assert values == pytest.approx([17.6776695297, 100, 17.6776695297])
    r = room()
    r["grid_x_m"] = [2 + 2 * math.tan(math.pi / 8)]
    # 22.5deg -> 300cd, d^2=4/cos^2(22.5): 300*cos^3/4.
    assert e.lighting(r)["points"][0]["lux"] == pytest.approx(59.14353806)


def test_zero_demand_and_zero_candela_remain_finite():
    data = system()
    for circuit in data["circuits"]:
        circuit["demand_factor"] = 0
    assert module().calculate(data)["panels"]["MAIN"]["demand_current_a"] == 0
    r = room()
    r["luminaires"][0]["candela"] = [[0, 0], [90, 0]]
    assert module().lighting(r)["minimum_to_average"] is None


def test_finite_arithmetic_extremes_raise_input_errors():
    e = module()
    data = system()
    data["transformer"]["rating_kva"] = 1e-320
    with pytest.raises(ValueError):
        e.calculate(data)
    with pytest.raises(ValueError):
        e.voltage_drop(1e308, 1e308, 120, "12")
    r = room()
    r["workplane_m"] = 0
    r["luminaires"][0].update(z_m=1e-320)
    with pytest.raises(ValueError):
        e.lighting(r)
    with pytest.raises(ValueError):
        e.select_conductor(10**1000, 15)


@pytest.mark.parametrize("mutator", [
    lambda d: d["panels"][1].update(parent="missing"),
    lambda d: d["panels"][0].update(parent="SUB"),
    lambda d: d["panels"][1].update(parent=None),
    lambda d: d["panels"][1].update(id="MAIN"),
    lambda d: d["circuits"][0].update(panel="missing"),
    lambda d: d["circuits"][0].update(load_va=float("nan")),
    lambda d: d["circuits"][0].update(load_va=True),
    lambda d: d["circuits"][0].update(demand_factor=1.2),
    lambda d: d["circuits"][0].update(continuous="yes"),
    lambda d: d["circuits"][0].update(power_factor=0),
    lambda d: d["circuits"][0].update(length_m=-1),
    lambda d: d["circuits"][0].update(phases=2),
    lambda d: d["circuits"][0].update(voltage_v=240),
    lambda d: d["circuits"][0].update(conductor_awg="500"),
    lambda d: d.update(ambient_c=40),
    lambda d: d.update(temperature_rating_c=90),
    lambda d: d["circuits"][0].update(length_ft=1000),
    lambda d: d["panels"][0].update(length_ft=1000),
    lambda d: d["transformer"].update(rating_va=75000),
    lambda d: d.update(voltage_ll_kv=0.208),
])
def test_rejects_invalid_units_values_and_topologies(mutator):
    data = system()
    mutator(data)
    with pytest.raises(ValueError):
        module().calculate(data)


@pytest.mark.parametrize("mutator", [
    lambda r: r.update(height_m=float("inf")),
    lambda r: r.update(grid_x_m=[]),
    lambda r: r.update(grid_x_m=[5]),
    lambda r: r["luminaires"][0].update(z_m=1),
    lambda r: r["luminaires"][0].update(x_m=-1),
    lambda r: r["luminaires"][0].update(candela=[[0, 1], [30, 2]]),
    lambda r: r["luminaires"][0].update(candela=[[0, 1], [0, 2], [90, 0]]),
    lambda r: r["luminaires"][0].update(candela=[[0, -1], [90, 0]]),
    lambda r: r.update(width_ft=10),
    lambda r: r["luminaires"][0].update(height_ft=10),
])
def test_rejects_invalid_room_geometry_and_photometry(mutator):
    data = room()
    mutator(data)
    with pytest.raises(ValueError):
        module().lighting(data)


def test_sample_run_writes_json_csv_html_and_reopenable_dxf(tmp_path):
    data = json.loads(Path("examples/electrical.json").read_text())
    out = module().run(data, tmp_path)
    json.dumps(out, allow_nan=False)
    assert json.loads((tmp_path / "electrical.json").read_text())["panels"]
    assert (tmp_path / "lighting.csv").read_text().startswith("x_m,y_m,lux")
    assert "Preliminary" in (tmp_path / "electrical.html").read_text()
    dxf = ezdxf.readfile(tmp_path / "electrical-single-line.dxf")
    assert len(dxf.modelspace().query("LINE")) >= len(data["panels"]) + len(data["circuits"])
    labels = [entity.dxf.text for entity in dxf.modelspace().query("TEXT")]
    for circuit in data["circuits"]:
        assert any(circuit["id"] in label for label in labels)


@pytest.mark.parametrize('factor', [0, .1, .5])
def test_branch_diversity_cannot_hide_connected_overload(factor):
    data = system()
    data['circuits'][1].update(load_va=3600, voltage_v=120, demand_factor=factor,
                               continuous=True, breaker_a=20)
    result = module().calculate(data)
    branch = result['circuits']['lights']
    assert branch['design_current_a'] == pytest.approx(37.5)
    assert branch['demand_current_a'] == pytest.approx(30*factor)
    assert branch['conductor']['awg'] == '8'
    assert 'device_overload' in branch['warnings']
    # Feeder diversity remains explicit, even when branch protection fails.
    assert result['panels']['SUB']['design_current_a'] == pytest.approx(4500*factor/(math.sqrt(3)*208))
    data['circuits'][1]['conductor_awg'] = '12'
    branch = module().calculate(data)['circuits']['lights']
    assert {'conductor_undersized', 'device_overload'} <= set(branch['warnings'])
