# Mechanical calculation study

These synthetic kitchen and upper-room examples teach arithmetic and expose assumptions. They do not describe the owner's house and do not establish Ontario compliance, equipment suitability, potable-water design, ventilation adequacy, or construction approval.

`renovation.mechanical.run(input_dict, output_dir)` returns a JSON-serializable dictionary and writes `mechanical.json`, `room-loads.csv`, `ducts.csv` and `plumbing.csv`. The committed input is `examples/mechanical.json`. The three independently callable calculations are `room_load(room, design)`, `duct_run(run, settings)` and `plumbing_branch(branch, settings)`. Each rejects missing/unknown fields, including unit-mislabeled fields. `run` requires the exact `units` map shown in the example; helper arguments use the unit-suffixed field names directly. No implicit conversions are made.

## Room heat and moisture arithmetic

The basis is [ASHRAE Handbook—Fundamentals 2021, SI, Chapter 17](https://handbook.ashrae.org/Handbooks/F21/SI/f21_ch17/F21_Ch17_si.aspx), section 2, Common Data and Procedures (air heat-transfer equations), ventilation/infiltration latent equation (16), and Table 16 (heating summary). Heating takes no solar/internal credit. This implementation makes its own fixed-property approximation: density 1.2 kg/m³, specific heat 1006 J/(kg K), and latent heat 2,501,000 J/kg. These yield 1207.2 W/(m³/s K) and 3,001,200 W/(m³/s) per kg/kg, rather than copying the Handbook's rounded air factors.

For each room:

- `UA = sum(U * A)`; areas are net opaque and glazing areas, without overlap.
- `Q_infiltration = volume * ACH / 3600`; supplied ventilation is added independently, without heat recovery or an interaction correction.
- Heating is `UA * (Ti - To) + rho * cp * (Q_infiltration + Q_ventilation) * (Ti - To)`.
- Cooling sensible uses the summer temperature difference plus explicit non-occupant internal sensible W, occupant sensible W and `sum(glazing_area * irradiance * SHGC * shading_factor)`.
- Cooling latent is `internal_latent + occupant_latent + rho * hfg * Q_outdoor * max(w_outdoor - w_indoor, 0)`. A drier outdoor condition receives no dehumidification credit.
- Sensible supply airflow is `load / (rho * cp * supply_delta_K)`, with separate heating/cooling deltas. Cooling airflow excludes latent load; it does not establish latent coil capacity.

Optional `occupancy` contains an integer `count` and explicit `sensible_w_person`/`latent_w_person`; count times each per-person gain is reported separately. Fixed `internal_*` gains exclude occupants, so they are not counted twice. Omitted occupancy means zero people. Sample per-person gains (75 W sensible, 55 W latent) are declared study inputs, not a prescribed occupancy/activity table. Heating takes no occupant credit.

Cooling is an instantaneous gain balance, not the Handbook RLF method, an hourly heat-balance solver or an F280 calculation. There is no radiant storage, sol-air opaque gain, ground heat transfer, duct leakage, distribution heat transfer, ventilation rate selection, humidity saturation check or winter humidification load. The caller must establish consistent humidity ratios and avoid counting mechanical air exchange twice. Irradiance and internal gains are explicit study assumptions, not weather or occupancy defaults.

## Round ducts and explicit fittings

[ASHRAE Handbook—Fundamentals 2021, SI, Chapter 21](https://handbook.ashrae.org/Handbooks/F21/SI/f21_ch21/f21_ch21_si.aspx), equations (18)–(20) and (29)–(30), and the Equal Friction Method subsection provide the friction/dynamic-loss basis. This implementation uses all diameters in metres:

```text
A = pi * D² / 4; v = Q/A; Re = rho*v*D/mu
1/sqrt(f) = -2*log10(epsilon/(3.7*D) + 2.51/(Re*sqrt(f)))
dp/L = f*rho*v²/(2*D)
dp_fittings = sum(count*K) * rho*v²/2
dp_run = (dp/L)*length + dp_fittings
```

Air viscosity is the declared assumption 1.81e-5 Pa s. For `Re < 2300`, `f=64/Re`; from 2300 through 4000 the result carries a transition warning. Available diameters are sorted, and the smallest meeting both the common friction target and user velocity limit is recommended. Discrete rounding usually produces friction below the common target. Selected smaller diameters receive separate friction and velocity warnings. If the catalogue is exhausted, recommendation is null and the largest is a flagged fallback unless an explicit selection was supplied.

Sample friction target 0.8 Pa/m, maximum velocity 4 m/s, roughness 0.09 mm, and fitting K values are user assumptions. They are not prescriptive limits or fitting geometry lookups. Every K refers to the selected run velocity. Runs are independent, constant-area segments; add connected segments externally to obtain a path. No network balancing, fan/system intersection, pressure recovery, junction coefficient conversion, acoustics or flexible-duct compression model is implemented.

## Plumbing table and bounded selection

The primary source is [ICC, 2012 North Carolina Plumbing Code, Appendix E](https://media.iccsafe.org/NC/2012_NC_Plumbing.pdf#page=142): Table E103.3(2), printed page 126 (PDF page 142), private combined load column; and Table E103.3(3), printed page 127 (PDF page 143), flush-tank demand column. The code includes only named private fixtures and the first 20 demand rows. A bathroom group replaces its constituent fixtures; entering both double counts them. Hot/cold branch scopes and flush-valve systems are rejected.

Sum fixture count times its tabulated combined WSFU, then select the next whole published row upward. For example, a private kitchen sink plus dishwasher totals 2.8 WSFU, selects row 3 and 6.5 US gpm. Totals below 1 or above 20 are rejected; there is no extrapolation or arbitrary WSFU-to-flow multiplier. US gpm converts using 3.785411784 litres per US gallon and 60 seconds per minute. Pipe velocity is `v=(L/s / 1000)/(pi*inside_diameter²/4)`. The smallest available inside diameter meeting the user limit is recommended, with explicit-selection and exhausted-catalogue warnings.

Pipe choices are user-supplied **actual inside diameters**, not nominal sizes, and the sample 2 m/s velocity limit is an assumption. This is a velocity screen, not complete pressure-based pipe sizing: available pressure, elevation, friction, water temperature, meters, backflow devices and required outlet pressure remain unchecked. No drainage fixture units or continuous-flow fixtures are supported.

## Input bounds and verification

All numbers must be finite numeric values; booleans and numeric strings are rejected. Counts are positive integers; diameters must be unique; an explicit selection must occur in its catalogue. Temperatures span −50 to 60 °C, with heating indoor ≥ outdoor and cooling outdoor ≥ indoor. The following are implementation limits, not source recommendations: room volume `(0,3000] m³`, infiltration `[0,5] ACH`, ventilation `[0,0.5] m³/s`, surface area `(0,1000] m²`, U-value `(0,15] W/(m² K)`, internal gains `[0,5000] W` each, solar area `[0,300] m²`, irradiance `[0,1400] W/m²`, SHGC/shading `[0,1]`, and humidity ratio `[0,0.03] kg/kg`. Occupancy count is 0–100 and each per-person gain is 0–250 W. Supply deltas are 1–40 K heating and 1–30 K cooling. Duct flow is `1e-8–10 m³/s`, length `0–1000 m`, roughness `0–0.001 m` with relative roughness ≤0.05; catalogue diameters are `0.005–3 m`. Target friction is `(0,10] Pa/m`, duct velocity limit `(0,30] m/s`, plumbing limit `(0,5] m/s`, and K is `0–100`. Collections and fitting/fixture counts are bounded at 1000.

Run `python -m pytest tests/test_mechanical.py -q`. Hand checks cover separate transmission/infiltration/ventilation and occupant loads, explicit solar and latent terms, laminar Poiseuille friction, turbulent Colebrook residual, fitting losses, discrete sizing, WSFU boundary rows, exhausted catalogues, invalid units and non-finite values. Reports use `allow_nan=False` and are calculated/validated before any report write.
