# Synthetic electrical study

I use this study to compare how assigned appliance diversity, conductor size,
feeder length and luminaire distribution affect a small building. The input is
synthetic. It is a preliminary educational comparison, with no Ontario code
compliance, permit, equipment selection or construction signoff.

## Reproduce and inspect

The repository CLI calls `run(input_dict, output_dir)` with
[`examples/electrical.json`](../examples/electrical.json). To run just this domain:

```python
import json
from pathlib import Path
from renovation.electrical import run

result = run(json.loads(Path("examples/electrical.json").read_text()), "output/electrical")
```

This writes `electrical.json`, `electrical.html`,
`electrical-single-line.dxf`, and, when a room is provided, `lighting.csv`.
The return value is JSON serializable, including artifact paths. All artifacts
come from the same result. The DXF contains real editable line, circle and text
entities in R2010 format, with schematic millimetre coordinates. It depicts the
panel hierarchy, branch connections, conductor/device labels and panel fault
currents; it is not a scaled installation plan. Tests reopen it with ezdxf.

Public helpers in `renovation.electrical`:

| Function | Contract |
| --- | --- |
| `calculate(data)` | Pure calculation; returns `panels` and `circuits` keyed by input ID, assumptions and references. |
| `select_conductor(design_current_a, breaker_a, *, derating_factor=1)` | Returns smallest supported copper AWG satisfying ampacity and device limits. |
| `voltage_drop(current_a, length_m, voltage_v, conductor_awg, *, phases=1, power_factor=1)` | Returns `volts`, `percent`, and one-way `r_one_way_ohm`, `x_one_way_ohm`. |
| `lighting(room)` | Returns every grid point, average/minimum/maximum lux, and minimum/average uniformity. |
| `run(input_dict, output_dir)` | Validates, calculates and exports the artifacts above. |

Invalid or unsupported inputs raise `ValueError`. Numerical inputs must be finite
numbers, not numeric strings or booleans. Finite inputs whose arithmetic cannot
produce finite outputs also raise `ValueError`. IDs must be nonempty printable
strings. No unit inference or conversion occurs: field suffixes specify SI units,
with amperes, volts, metres, VA, kVA, kA and degrees Celsius used as named.
Unknown fields at every calculation object are rejected, including mixed-unit
fields such as `length_ft` alongside `length_m`. The top-level `description`
field is optional annotation and does not affect calculations.

## Input and calculation sequence

The supply uses `voltage_ll_v`, greater than zero and at most 600 V, at 60 Hz.
`transformer` requires positive `rating_kva`, `impedance_pct` (at most 100), and
nonnegative `x_r_ratio`. It represents one three-phase transformer with an infinite
upstream bus. Every panel shares the same nominal supply voltage.

`panels` must be a nonempty list forming one connected radial tree. Each panel
has `id`, `parent` (null for the single root), positive `breaker_a` and
`interrupt_ka`, and nonnegative one-way `length_m`. The root cable runs from
the transformer to the main bus; each other cable runs from its parent bus to
the panel. Duplicate IDs, missing parents, self-parenting and disconnected
cycles are rejected.

`circuits` is a list, optionally empty. Each requires `id`, `panel`, nonnegative
`load_va`, `demand_factor` in [0,1], boolean `continuous`, lagging `power_factor`
in (0,1], `phases` of 1 or 3, `voltage_v`, one-way `length_m`, `breaker_a`, and
`interrupt_ka`. Three-phase branches must use the supply line voltage;
single-phase branches must use line voltage or line voltage divided by √3
(0.2% nominal-voltage rounding tolerance). Leading power factor and split-phase
120/240 V supplies are not supported. Omitted electrical fields are not silently
replaced by appliance assumptions.

For each circuit, assigned demand is `load_va × demand_factor`. Demand factors
are user scenarios, not a jurisdictional demand schedule. Operating current is
`demand_va / voltage_v` for one phase, or `demand_va / (√3 × voltage_v)` for
three phases. `design_current_a` multiplies continuous demand by 1.25 before
sizing. Voltage drop always uses operating demand, without that sizing multiplier.

Downstream loads are counted exactly once in every ancestor. The report retains
scalar sums `connected_va` and `demand_va`, while panel operating current uses
the magnitude of summed complex powers: `P = VA × pf`,
`Q = VA × √(1 − pf²)`, `I = |Σ(P+jQ)| / (√3 Vll)`. Design current uses the same
sum with each continuous load increased by 25%. Connected current is a
conservative nameplate-VA equivalent, `ΣVA/(√3 Vll)` at panels and
`load_va/(phase_factor × voltage_v)` at branches.

Single-phase branches are assumed perfectly distributed among the three phases
when calculating panel and feeder currents. There is no phase-assignment model,
neutral-current calculation, harmonic analysis or worst-leg check. A panel with
only one single-phase branch therefore remains an ideal balanced equivalent,
not an installation-ready feeder calculation.

## Bounded conductor table

Source: [Southwire MC Installation & Application Guide, printed page 29,
PDF page 30](https://www.southwire.com/medias/sys_master/installation-manuals/installation-manuals/hca/hff/8887676010526/MC-Installation-Guide-Southwire.pdf).
The copper 75°C column is transcribed below. The guide labels its table
310.15(B)(16), formerly 310.16, at 30°C ambient and at most three
current-carrying conductors in raceway/cable/earth. This is a bounded published
reference, not a claim to implement the current NEC or Canadian code.

| Copper AWG | 75°C ampacity A | Nominal geometric area mm² |
| --- | ---: | ---: |
| 14 | 20 | 2.08 |
| 12 | 25 | 3.31 |
| 10 | 35 | 5.26 |
| 8 | 50 | 8.37 |
| 6 | 65 | 13.3 |
| 4 | 85 | 21.2 |
| 3 | 100 | 26.7 |
| 2 | 115 | 33.6 |

Areas are rounded AWG geometric areas (`diameter_in = .005 ×
92^((36 − AWG)/39)`, `area_mm2 = π(diameter_in × 25.4)²/4`), not measured cable
data. AWG 5, 7 and other unlisted sizes are intentionally unsupported.

The model fixes `ambient_c=30` and `temperature_rating_c=75`; other settings
are rejected. Global or per-cable `derating_factor` in (0,1] explicitly multiplies
the table ampacity. It is user assigned and does not calculate ambient,
grouping or installation correction factors. Equipment is assumed to permit
75°C terminations. Conservative small-wire device caps are 15, 20 and 30 A
for copper 14, 12 and 10 AWG, respectively, as noted in the table footnote.
Device limit is the lesser of adjusted ampacity and that cap.

Automatic selection checks both design current and the assigned breaker; it
does not choose a breaker or apply next-size-up exceptions. A requirement
beyond the table raises `ValueError`. To study an inadequate existing cable,
set its `conductor_awg` explicitly to a supported string. It is retained for
all drop and fault calculations and reports `conductor_undersized` when the
design current or breaker exceeds its bounds. `device_overload` reports design
current above the breaker rating. Neither warning repairs the input.

## Voltage drop and fault impedance

[Schneider Electric's voltage-drop equations](https://www.electrical-installation.org/enwiki/Calculation_of_voltage_drop_in_steady_load_conditions)
give `ΔV = k I (R pf + X √(1 − pf²))`, where k is 2 for a single-phase circuit
and √3 for balanced three phase. R and X here include one-way length.
`voltage_drop.percent = 100 ΔV / nominal circuit voltage`. The model sums local
percentage drops along the feeder path for `total_voltage_drop_pct`; this
assumes balanced supply and comparable voltage bases and is a first-order
approximation. Defaults of 3% local and 5% total are study targets, adjustable
with `drop_limit_pct` and `total_drop_limit_pct`; they are not asserted code limits.

[Schneider Electric's radial three-phase fault method](https://www.electrical-installation.org/enwiki/3-phase_short-circuit_current_(Isc)_at_any_point_within_a_LV_installation)
adds per-phase R and X separately. Transformer magnitude in ohms is
`|Zt| = Vll²/(kVA × 1000) × impedance_pct/100`. User X/R resolves
`Rt=|Zt|/√(1+(X/R)²)`, `Xt=Rt×X/R`. Each cable adds
`R=ρL/A` and `X=0.000096L` ohm at 60 Hz. Available symmetrical three-phase
bolted fault current at each panel is `Vll/(√3 |ΣZ|)`.
The guide's copper resistivities are 0.01851 Ω mm²/m at 20°C for the maximum
fault screen and 0.02369 Ω mm²/m at 90°C for the conservative operating-drop
screen. Hot resistance does not imply 90°C ampacity or terminations.

Each branch breaker is checked against the fault current at its supply panel.
Each feeder breaker is located at its **upstream** bus, so its interrupting
rating is checked there rather than against the lower downstream fault level.
The root breaker is conservatively checked at the transformer terminals.
`breaker_available_fault_a` records the comparison value and
`interrupt_rating_exceeded` flags insufficient assigned kA rating.

These are not IEC 60909 or complete protection studies. Voltage factors,
transformer tolerances, finite utility strength, source/motor contributions,
unbalanced or earth faults, DC asymmetry, withstand energy, clearing time,
selectivity, grounding and arc flash are omitted. The model does not establish
that a breaker trips fast enough. It also does not check transformer thermal
loading, panel bus ratings separately from breaker ratings, or equipment SCCR.

## Point-by-point room lighting

`room` requires positive `width_m`, `depth_m`, `height_m`, a nonnegative
`workplane_m` below the ceiling, nonempty `grid_x_m` and `grid_y_m` arrays
inside the room, and a nonempty `luminaires` list. The grid is their Cartesian
product, capped at 100,000 points. Every luminaire has `x_m`, `y_m`, `z_m`
inside the room with z above the workplane. Its synthetic `candela` pairs
`[angle_deg, intensity_cd]` must be nonnegative and strictly increase in angle
from 0° (vertically downward) through 90°. Intensity is linearly interpolated;
all fixture contributions are summed.

The [IES inverse-square law](https://ies.org/definitions/inverse-square-law/)
and [IES cosine law](https://ies.org/definitions/cosine-law/) give
`E = I(θ) cos(θ)/d²` lux for a horizontal plane. With vertical separation h,
`d=√(dx²+dy²+h²)` and `cos(θ)=h/d`. This is direct lighting from rotationally
symmetric vertical point sources; no azimuth dependence, reflectance,
maintenance factors, shadows, glare or daylight is included. The arithmetic
mean describes sampled points, not an area-integrated room average. Zero
light returns zero lux and null minimum/average uniformity. IES notes the
usual point-source distance check of at least five source dimensions; source
dimensions are not present here and the synthetic table is not a product IES
photometric file or measured luminaire performance.

## Verification

```sh
python -m pytest tests/test_electrical.py -q
```

Hand checks cover 6,000 connected VA / 4,800 assigned demand VA, continuous
load sizing, different power factors, conductor/device/derating boundaries,
4.29426 V round-trip drop for 10 A through 30 m of #12 copper, 4,163.58 A at
a 75 kVA / 208 V / 5% transformer, complex downstream impedance, upstream
breaker interrupt duty, and 100 lux directly below a 400 cd source at 2 m.
Tests also exercise 45° cosine response, candela interpolation, specified
undersized wire, zero demand, invalid topology/finite units, numerical extremes,
and every exported artifact including DXF reopening.
