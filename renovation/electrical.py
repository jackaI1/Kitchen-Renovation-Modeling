"""Bounded, synthetic electrical and point-lighting studies; see docs/electrical.md."""
from __future__ import annotations

import bisect
import csv
from functools import wraps
import html
import json
import math
from pathlib import Path

# Copper 75 C column: Southwire MC Installation Guide, PDF page 30.
# Areas are rounded nominal AWG geometric areas, not measured product data.
COPPER = {
    "14": (2.08, 20), "12": (3.31, 25), "10": (5.26, 35),
    "8": (8.37, 50), "6": (13.3, 65), "4": (21.2, 85),
    "3": (26.7, 100), "2": (33.6, 115),
}
SMALL_DEVICE_LIMIT = {"14": 15, "12": 20, "10": 30}
RHO_COLD = 0.01851  # ohm mm2/m, 20 C, conservative maximum-fault screen
RHO_HOT = 0.02369  # ohm mm2/m, 90 C, conservative operating-drop screen
X_PER_M = 0.000096  # ohm/m, 60 Hz approximation
REFERENCES = [
    "https://www.southwire.com/medias/sys_master/installation-manuals/installation-manuals/hca/hff/8887676010526/MC-Installation-Guide-Southwire.pdf",
    "https://www.electrical-installation.org/enwiki/3-phase_short-circuit_current_(Isc)_at_any_point_within_a_LV_installation",
    "https://www.electrical-installation.org/enwiki/Calculation_of_voltage_drop_in_steady_load_conditions",
    "https://ies.org/definitions/inverse-square-law/",
    "https://ies.org/definitions/cosine-law/",
]
ASSUMPTIONS = [
    "Preliminary educational study; no permit, code compliance or construction signoff.",
    "Synthetic balanced 60 Hz three-phase radial supply; single-phase loads perfectly distributed across phases.",
    "Explicit user demand factors; continuous demand multiplied by 1.25 only for sizing.",
    "Copper 75 C ampacity at 30 C ambient, at most three current-carrying conductors; user derating multiplier only.",
    "Small conductor device caps 15/20/30 A for AWG 14/12/10; no next-size-up exception.",
    "Drop uses 90 C copper resistance, faults use 20 C resistance; reactance 0.096 milliohm/m at 60 Hz.",
    "Infinite upstream bus; symmetrical bolted three-phase fault only, no motor contribution or arc-flash calculation.",
    "Point luminaires vertical and rotationally symmetric; direct light only, no reflections or obstructions.",
]


def _number(value, name, *, minimum=0, maximum=None, positive=False):
    try:
        finite_number = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
    except OverflowError:
        finite_number = False
    if not finite_number:
        raise ValueError(f"{name} must be a finite number in the named SI unit")
    if value < minimum or (positive and value <= minimum) or (maximum is not None and value > maximum):
        raise ValueError(f"{name} outside supported range")
    return float(value)


def _name(value, name):
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
        raise ValueError(f"{name} must be a nonempty printable string")
    return value


def _list(value, name, *, nonempty=False):
    if not isinstance(value, list) or (nonempty and not value):
        raise ValueError(f"{name} must be {'a nonempty' if nonempty else 'a'} list")
    return value


def _record(value, name, allowed):
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    if set(value) - set(allowed):
        raise ValueError(f"{name} contains unsupported fields; use the documented SI field names")
    return value


def _awg(value):
    if not isinstance(value, str) or value not in COPPER:
        raise ValueError("conductor_awg is outside copper table (14 through 2 AWG)")
    return value


def _conductor(awg, derating):
    area, base = COPPER[_awg(awg)]
    return {"awg": awg, "area_mm2": area, "base_ampacity_a": base,
            "ampacity_a": base * derating,
            "device_limit_a": min(base * derating, SMALL_DEVICE_LIMIT.get(awg, math.inf))}


def _finite_calculation(function):
    """Translate finite-input arithmetic overflow/underflow into input errors."""
    @wraps(function)
    def checked(*args, **kwargs):
        try:
            result = function(*args, **kwargs)
        except ArithmeticError as exc:
            raise ValueError("input magnitudes exceed finite calculation range") from exc
        try:
            json.dumps(result, allow_nan=False)
        except ValueError as exc:
            raise ValueError("input magnitudes exceed finite calculation range") from exc
        return result
    return checked


def select_conductor(design_current_a, breaker_a, *, derating_factor=1):
    """Smallest bounded copper conductor supporting both design current and breaker."""
    design = _number(design_current_a, "design_current_a")
    breaker = _number(breaker_a, "breaker_a", positive=True)
    factor = _number(derating_factor, "derating_factor", positive=True, maximum=1)
    for awg in COPPER:
        c = _conductor(awg, factor)
        if c["ampacity_a"] >= design and c["device_limit_a"] >= breaker:
            return c
    raise ValueError("required conductor exceeds bounded ampacity table; specify a supported conductor for an undersizing diagnostic")


@_finite_calculation
def voltage_drop(current_a, length_m, voltage_v, conductor_awg, *, phases=1, power_factor=1):
    """Approximate operating drop; length is one-way, power factor is lagging."""
    i = _number(current_a, "current_a")
    length = _number(length_m, "length_m")
    voltage = _number(voltage_v, "voltage_v", positive=True)
    pf = _number(power_factor, "power_factor", positive=True, maximum=1)
    if isinstance(phases, bool) or phases not in (1, 3):
        raise ValueError("phases must be 1 or 3")
    area = COPPER[_awg(conductor_awg)][0]
    resistance = RHO_HOT * length / area
    reactance = X_PER_M * length
    volts = (2 if phases == 1 else math.sqrt(3)) * i * (resistance * pf + reactance * math.sqrt(1 - pf * pf))
    return {"volts": volts, "percent": 100 * volts / voltage,
            "r_one_way_ohm": resistance, "x_one_way_ohm": reactance}


@_finite_calculation
def calculate(data):
    """Calculate a common-voltage radial panel tree without writing files."""
    data = _record(data, "electrical input", ("description", "voltage_ll_v", "transformer", "panels", "circuits", "room", "ambient_c", "temperature_rating_c", "derating_factor", "drop_limit_pct", "total_drop_limit_pct"))
    voltage = _number(data.get("voltage_ll_v"), "voltage_ll_v", positive=True, maximum=600)
    if _number(data.get("ambient_c", 30), "ambient_c") != 30:
        raise ValueError("ampacity table supports ambient_c=30 only; use explicit derating_factor")
    if _number(data.get("temperature_rating_c", 75), "temperature_rating_c") != 75:
        raise ValueError("ampacity table supports temperature_rating_c=75 only")
    derating = _number(data.get("derating_factor", 1), "derating_factor", positive=True, maximum=1)
    drop_limit = _number(data.get("drop_limit_pct", 3), "drop_limit_pct", positive=True, maximum=100)
    total_limit = _number(data.get("total_drop_limit_pct", 5), "total_drop_limit_pct", positive=True, maximum=100)
    transformer = _record(data.get("transformer"), "transformer", ("rating_kva", "impedance_pct", "x_r_ratio"))
    kva = _number(transformer.get("rating_kva"), "rating_kva", positive=True)
    z_pct = _number(transformer.get("impedance_pct"), "impedance_pct", positive=True, maximum=100)
    xr = _number(transformer.get("x_r_ratio"), "x_r_ratio")
    magnitude = voltage * voltage / (kva * 1000) * z_pct / 100
    r = magnitude / math.hypot(1, xr)
    source_z = complex(r, r * xr)
    panels = {}
    for p in _list(data.get("panels"), "panels", nonempty=True):
        _record(p, "panel", ("id", "parent", "breaker_a", "interrupt_ka", "length_m", "derating_factor", "conductor_awg"))
        name = _name(p.get("id"), "panel id")
        if name in panels:
            raise ValueError("duplicate panel id")
        panels[name] = p
    roots = [name for name, p in panels.items() if p.get("parent") is None]
    if len(roots) != 1:
        raise ValueError("panel tree must have exactly one root")
    order, children = [], {name: [] for name in panels}
    for name, p in panels.items():
        parent = p.get("parent")
        if parent is not None:
            if not isinstance(parent, str) or parent not in panels or parent == name:
                raise ValueError("invalid panel parent")
            children[parent].append(name)
    # Iterative traversal rejects disconnected cycles without recursion limits.
    queue = [roots[0]]
    while queue:
        name = queue.pop()
        order.append(name)
        queue.extend(children[name])
    if len(order) != len(panels):
        raise ValueError("panel tree contains a disconnected cycle")

    totals = {name: [0.0, 0.0, 0j, 0j] for name in panels}
    circuit_out = {}

    def cable(item, design_current, operating_current, v, phases, pf):
        breaker = _number(item.get("breaker_a"), "breaker_a", positive=True)
        interrupt = _number(item.get("interrupt_ka"), "interrupt_ka", positive=True)
        length = _number(item.get("length_m"), "length_m")
        factor = _number(item.get("derating_factor", derating), "derating_factor", positive=True, maximum=1)
        conductor = (_conductor(item["conductor_awg"], factor) if "conductor_awg" in item
                     else select_conductor(design_current, breaker, derating_factor=factor))
        warnings = []
        if design_current > breaker:
            warnings.append("device_overload")
        if design_current > conductor["ampacity_a"] or breaker > conductor["device_limit_a"]:
            warnings.append("conductor_undersized")
        drop = voltage_drop(operating_current, length, v, conductor["awg"], phases=phases, power_factor=pf)
        if drop["percent"] > drop_limit:
            warnings.append("voltage_drop_exceeded")
        return {"design_current_a": design_current, "demand_current_a": operating_current,
                "breaker_a": breaker, "interrupt_ka": interrupt, "length_m": length,
                "derating_factor": factor, "conductor": conductor,
                "conductor_source": "specified" if "conductor_awg" in item else "selected",
                "voltage_drop": drop, "warnings": warnings}

    for c in _list(data.get("circuits"), "circuits"):
        _record(c, "circuit", ("id", "panel", "load_va", "demand_factor", "continuous", "power_factor", "phases", "voltage_v", "length_m", "breaker_a", "interrupt_ka", "derating_factor", "conductor_awg"))
        name = _name(c.get("id"), "circuit id")
        if name in circuit_out:
            raise ValueError("duplicate circuit id")
        panel = c.get("panel")
        if not isinstance(panel, str) or panel not in panels:
            raise ValueError("circuit panel not found")
        load = _number(c.get("load_va"), "load_va")
        factor = _number(c.get("demand_factor"), "demand_factor", maximum=1)
        continuous = c.get("continuous")
        if not isinstance(continuous, bool):
            raise ValueError("continuous must be a boolean")
        pf = _number(c.get("power_factor"), "power_factor", positive=True, maximum=1)
        phases = c.get("phases")
        if isinstance(phases, bool) or phases not in (1, 3):
            raise ValueError("phases must be 1 or 3")
        v = _number(c.get("voltage_v"), "voltage_v", positive=True)
        supported = [voltage] if phases == 3 else [voltage, voltage / math.sqrt(3)]
        if not any(math.isclose(v, allowed, rel_tol=0.002) for allowed in supported):
            raise ValueError("circuit voltage incompatible with common supply voltage")
        demand = load * factor
        sizing = demand * (1.25 if continuous else 1)
        current_divisor = v * (math.sqrt(3) if phases == 3 else 1)
        result = cable(c, sizing / current_divisor, demand / current_divisor, v, phases, pf)
        result.update(panel=panel, connected_va=load, demand_va=demand, phases=phases,
                      connected_current_a=load / current_divisor,
                      voltage_v=v, power_factor=pf, continuous=continuous, demand_factor=factor)
        circuit_out[name] = result
        s = complex(pf, math.sqrt(1 - pf * pf))
        totals[panel][0] += load
        totals[panel][1] += demand
        totals[panel][2] += demand * s
        totals[panel][3] += sizing * s
    for name in reversed(order):
        parent = panels[name].get("parent")
        if parent is not None:
            totals[parent] = [a + b for a, b in zip(totals[parent], totals[name])]
    panel_out, impedances = {}, {}
    for name in order:
        p = panels[name]
        connected, demand, s, sizing_s = totals[name]
        pf = s.real / abs(s) if abs(s) else 1
        out = cable(p, abs(sizing_s) / (math.sqrt(3) * voltage),
                    abs(s) / (math.sqrt(3) * voltage), voltage, 3, pf)
        parent = p.get("parent")
        upstream_z = source_z if parent is None else impedances[parent]
        area = out["conductor"]["area_mm2"]
        z = upstream_z + complex(RHO_COLD / area, X_PER_M) * out["length_m"]
        impedances[name] = z
        fault = voltage / (math.sqrt(3) * abs(z))
        breaker_fault = voltage / (math.sqrt(3) * abs(upstream_z))
        if breaker_fault > out["interrupt_ka"] * 1000:
            out["warnings"].append("interrupt_rating_exceeded")
        cumulative = out["voltage_drop"]["percent"] + (panel_out[parent]["total_voltage_drop_pct"] if parent else 0)
        if cumulative > total_limit:
            out["warnings"].append("total_voltage_drop_exceeded")
        out.update(parent=parent, connected_va=connected, demand_va=demand,
                   demand_kw=s.real / 1000, demand_kvar=s.imag / 1000,
                   connected_current_a=connected / (math.sqrt(3) * voltage),
                   voltage_ll_v=voltage, power_factor=pf, fault_current_a=fault,
                   breaker_available_fault_a=breaker_fault,
                   impedance_ohm={"r": z.real, "x": z.imag}, total_voltage_drop_pct=cumulative)
        panel_out[name] = out
    for out in circuit_out.values():
        p = panel_out[out["panel"]]
        fault = p["fault_current_a"]
        if fault > out["interrupt_ka"] * 1000:
            out["warnings"].append("interrupt_rating_exceeded")
        cumulative = p["total_voltage_drop_pct"] + out["voltage_drop"]["percent"]
        if cumulative > total_limit:
            out["warnings"].append("total_voltage_drop_exceeded")
        out.update(breaker_available_fault_a=fault, total_voltage_drop_pct=cumulative)
    result = {"panels": panel_out, "circuits": circuit_out,
              "assumptions": ASSUMPTIONS, "references": REFERENCES}
    return result


@_finite_calculation
def lighting(room):
    """Direct horizontal illuminance from piecewise-linear 0..90 degree candela."""
    room = _record(room, "room", ("width_m", "depth_m", "height_m", "workplane_m", "grid_x_m", "grid_y_m", "luminaires"))
    width = _number(room.get("width_m"), "width_m", positive=True)
    depth = _number(room.get("depth_m"), "depth_m", positive=True)
    height = _number(room.get("height_m"), "height_m", positive=True)
    plane = _number(room.get("workplane_m"), "workplane_m", maximum=height)
    if plane >= height:
        raise ValueError("workplane must be below room ceiling")
    xs = [_number(x, "grid_x_m", maximum=width) for x in _list(room.get("grid_x_m"), "grid_x_m", nonempty=True)]
    ys = [_number(y, "grid_y_m", maximum=depth) for y in _list(room.get("grid_y_m"), "grid_y_m", nonempty=True)]
    if len(xs) * len(ys) > 100000:
        raise ValueError("lighting grid exceeds 100000 points")
    sources = []
    for lum in _list(room.get("luminaires"), "luminaires", nonempty=True):
        _record(lum, "luminaire", ("x_m", "y_m", "z_m", "candela"))
        x = _number(lum.get("x_m"), "x_m", maximum=width)
        y = _number(lum.get("y_m"), "y_m", maximum=depth)
        z = _number(lum.get("z_m"), "z_m", maximum=height)
        if z <= plane:
            raise ValueError("luminaire must be above workplane")
        angles, intensities = [], []
        for pair in _list(lum.get("candela"), "candela", nonempty=True):
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError("candela requires [angle_deg, intensity_cd] pairs")
            angles.append(_number(pair[0], "angle_deg", maximum=90))
            intensities.append(_number(pair[1], "intensity_cd"))
        if len(angles) < 2 or angles[0] != 0 or angles[-1] != 90 or any(a >= b for a, b in zip(angles, angles[1:])):
            raise ValueError("candela angles must strictly increase from 0 to 90 degrees")
        sources.append((x, y, z, angles, intensities))
    points = []
    for y in ys:
        for x in xs:
            lux = 0.0
            for lx, ly, lz, angles, intensities in sources:
                h = lz - plane
                d = math.hypot(x - lx, y - ly, h)
                angle = math.degrees(math.atan2(math.hypot(x - lx, y - ly), h))
                idx = min(bisect.bisect_right(angles, angle), len(angles) - 1)
                fraction = (angle - angles[idx - 1]) / (angles[idx] - angles[idx - 1])
                intensity = intensities[idx - 1] + fraction * (intensities[idx] - intensities[idx - 1])
                lux += intensity * (h / d) / (d * d)
            if not math.isfinite(lux):
                raise ValueError("lighting magnitudes exceed finite calculation range")
            points.append({"x_m": x, "y_m": y, "lux": lux})
    mean = sum(p["lux"] / len(points) for p in points)
    minimum = min(p["lux"] for p in points)
    return {"points": points, "average_lux": mean, "minimum_lux": minimum,
            "maximum_lux": max(p["lux"] for p in points),
            "minimum_to_average": minimum / mean if mean else None}


def _single_line(result, path):
    import ezdxf

    doc = ezdxf.new("R2010")
    doc.units = 4  # drawing millimetres; diagram is schematic, no physical scale
    space = doc.modelspace()
    space.add_text("PRELIMINARY SYNTHETIC SINGLE LINE - NOT FOR CONSTRUCTION", height=3).set_placement((0, 20))
    positions = {}
    for index, (name, p) in enumerate(result["panels"].items()):
        depth, ancestor = 0, p["parent"]
        while ancestor is not None:
            depth += 1
            ancestor = result["panels"][ancestor]["parent"]
        x, y = depth * 160, -index * 100
        positions[name] = (x, y)
        space.add_line((x, y), (x + 100, y))
        space.add_text(f"{name}: {p['breaker_a']:g}A / {p['interrupt_ka']:g}kA; Cu #{p['conductor']['awg']}", height=2.5).set_placement((x, y + 6))
        space.add_text(f"Demand {p['demand_va']:.0f} VA; fault {p['fault_current_a']:.0f} A", height=2.5).set_placement((x, y + 2))
        if p["parent"] is not None:
            px, py = positions[p["parent"]]
            space.add_line((px + 100, py), (x, y))
        else:
            space.add_circle((x - 12, y), 5)
            space.add_line((x - 7, y), (x, y))
    offsets = {name: 0 for name in positions}
    for name, c in result["circuits"].items():
        x, y = positions[c["panel"]]
        offset = offsets[c["panel"]]
        offsets[c["panel"]] += 1
        cx = x + 12 + offset * 28
        space.add_line((cx, y), (cx, y - 15 - offset * 10))
        space.add_text(f"{name} {c['breaker_a']:g}A Cu #{c['conductor']['awg']} {c['voltage_drop']['percent']:.1f}%", height=2).set_placement((cx, y - 18 - offset * 10))
    doc.saveas(path)


def run(input_dict, output_dir):
    """Write electrical.json/html, lighting.csv and editable DXF; return plain dict."""
    result = calculate(input_dict)
    if "room" in input_dict:
        result["lighting"] = lighting(input_dict["room"])
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    names = ["electrical.json", "electrical.html", "electrical-single-line.dxf"]
    if "lighting" in result:
        names.append("lighting.csv")
        with (directory / "lighting.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["x_m", "y_m", "lux"])
            writer.writeheader()
            writer.writerows(result["lighting"]["points"])
    _single_line(result, directory / "electrical-single-line.dxf")
    result["artifacts"] = {name: str(directory / name) for name in names}
    (directory / "electrical.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    rows = []
    for kind in ("panels", "circuits"):
        for name, item in result[kind].items():
            rows.append("<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in
                        (kind, name, f"{item['connected_va']:.0f}", f"{item['demand_va']:.0f}",
                         f"{item['design_current_a']:.2f}", item["conductor"]["awg"],
                         f"{item['voltage_drop']['percent']:.2f}", ", ".join(item["warnings"]) or "none")) + "</tr>")
    page = "<!doctype html><html lang='en'><meta charset='utf-8'><title>Electrical study</title><style>body{font:16px system-ui;max-width:1100px;margin:40px auto;padding:20px;color:#182c38}table{border-collapse:collapse;width:100%}td,th{border:1px solid #bccbd3;padding:8px;text-align:left}pre{white-space:pre-wrap}</style><h1>Preliminary electrical study</h1>"
    page += "<ul>" + "".join(f"<li>{html.escape(a)}</li>" for a in ASSUMPTIONS) + "</ul>"
    page += "<table><tr><th>Type</th><th>ID</th><th>Connected VA</th><th>Demand VA</th><th>Design A</th><th>Cu AWG</th><th>Local drop %</th><th>Warnings</th></tr>" + "".join(rows) + "</table>"
    if "lighting" in result:
        light = result["lighting"]
        page += f"<h2>Direct lighting grid</h2><p>Average {light['average_lux']:.1f} lx; minimum {light['minimum_lux']:.1f} lx; maximum {light['maximum_lux']:.1f} lx. See lighting.csv for every point.</p>"
    page += "<h2>References</h2><ul>" + "".join(f"<li><a href='{html.escape(ref)}'>{html.escape(ref)}</a></li>" for ref in REFERENCES) + "</ul></html>"
    (directory / "electrical.html").write_text(page)
    return result
