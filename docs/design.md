# Renovation study design

I want to compare the services and wall details behind my kitchen model while learning building calculations. The new examples are synthetic, including a small two-storey building used to exercise coordination checks; they do not describe the actual house.

The Python package keeps four independent calculation modules and a reproducible command-line report. Inputs use named SI units, reject non-finite or unsupported values, and identify study assumptions. Electrical calculations use an explicitly bounded published copper ampacity table, assigned demand factors, radial impedance and point lighting. Mechanical calculations use steady-state heat balances, equal-friction circular ducts and an explicitly bounded fixture-unit table. Envelope calculations extend the existing resistance screen to a constrained steady-state Glaser condensation plane solution. BIM uses real IFC4 geometry and ports, separate architectural and services files, deterministic IDs, axis-aligned solid clash checks and site logistics checks.

Alternatives considered were a single large notebook or connecting proprietary CAD applications. Separate Python modules with small JSON examples let me test the equations and reopen IFC files in CI without requiring paid software or containers. HTML is the portable calculation-sheet export; DXF is the editable drawing format. The notebooks use the same tested functions as the reports.

## Deliverables and boundaries

- `renovation/electrical.py`, `examples/electrical.json`, `docs/electrical.md`, and hand-check tests: panel tree, connected/demand current, branch/feeder sizing, voltage drop, transformer/cable fault impedance, interrupting checks, DXF one-line, intensity-based room illuminance.
- `renovation/mechanical.py`, `examples/mechanical.json`, `docs/mechanical.md`, and hand-check tests: room heating/cooling, circular duct pressure drop/size selection, fixture-unit pipe selection and velocity limits.
- `renovation/bim.py`, `examples/building.json`, `docs/bim.md`, and reopen/export tests: two-storey IFC4 architecture, structural/MEP models, openings, properties/schedules, connectivity, hard/clearance clashes, crane/hoist swing checks, CSV/HTML reports and plan DXF. Axis-aligned geometry is an explicit supported subset; openings must remove clashes only within their actual void volume.
- `renovation/envelope.py`, `examples/walls.json`, `docs/envelope-screen.md`, and tests: preserve existing API, four control continuity checks, bounded climate inputs, resistance/temperature profiles and diffusion condensation planes/fluxes.
- `renovation/sheets.py`, notebooks, and tests: SymPy substitutions and pint dimension checks for electrical calculations, rendered HTML assumptions and references.
- `renovation/__main__.py`: `python -m renovation --output output` generates all studies from committed synthetic inputs. CI runs pytest, the generator, IFC reopening and notebook execution and uploads reports.

All methods are preliminary educational comparisons, with no permit, safety, product selection or construction signoff. Load diversity is user assigned, not an automatic Ontario code interpretation. Mechanical loads omit full hourly solar/dynamic cooling; plumbing tables are bounded and labeled. AABB clashes are exact only for the generated rectangular geometry. Crane checks are plan-radius screening without lifting capacity or collision dynamics. Declared membrane continuity cannot establish field workmanship.
