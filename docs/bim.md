# Plan-driven building and coordination study

The committed input is a synthetic two-storey building, unrelated to the actual house. It demonstrates two workflows: generating architecture/structure/services from a plan, and coordinating federated disciplines and temporary site logistics. There is no proprietary CAD application or server requirement.

```python
import json
from pathlib import Path
from renovation.bim import run

summary = run(json.loads(Path('examples/building.json').read_text()), 'output/bim')
print(summary['issue_counts'])
```

`run(input_dict, output_dir)` validates the input before writing files and returns a JSON-serializable dictionary with `schema`, `element_count`, `issue_count`, `issue_counts`, `issues`, `artifacts` and `assumptions`. `extract_schedule(ifc_paths)` reopens IFC files and returns schedule rows; `detect_issues(ifc_paths)` reopens files and returns coordination issues. These readers support only the generated rectangular extrusion subset, not arbitrary IFC models.

## Input contract

All geometry uses metres in a common world coordinate system. Storey elevation records are metadata and placement; **element `origin_m` and port `position_m` are absolute world coordinates**, including height. Each element supplies:

| Field | Meaning |
|---|---|
| `id` | Unique, nonempty element identity; keep stable across revisions |
| `type` | `wall`, `slab`, `column`, `space`, `opening`, `duct`, `pipe`, `equipment`, `crane` or `hoist` |
| `discipline` | `architecture`, `structure`, `mechanical`, `plumbing` or `site` |
| `storey` | ID from `storeys`, whose records include `id` and `elevation_m` |
| `origin_m` | Minimum x/y/z corner of the rectangular solid |
| `size_m` | Strictly positive x/y/z lengths |
| `tag` | Optional occurrence tag, defaulting to ID |
| `flow_m3_s` | Optional nonnegative design flow, stored as a named IFC property |
| `clearance_m` | Optional nonnegative required physical surface gap, default zero |
| `host` | Required wall ID for an opening; opening must intersect host on same storey |
| `ports` | Optional distribution ports, each with unique `id`, world `position_m`, and `direction` (`SOURCE`, `SINK`, `SOURCEANDSINK`) |
| `swing_radius_m` | Required positive plan screening radius for a crane |

`connections` is a list of pairs of port IDs. Connections must join different elements, coincide spatially, share the air-conditioning or domestic-cold-water system, and have compatible flow direction. Each explicit port can connect once. Ports are placed relative to their nesting element; their axis follows the longest box dimension, oriented using endpoint position and flow direction. This models simple straight runs, not fittings or branched hydraulic networks. Port positions describe connections; the generator does not infer or route them. Elements without explicit ports receive no connectivity checks.

`site` is an additional list of elements using the same contract. The example includes a tower crane and a man/material hoist within its swing disk, plus a second hoist outside it. Numeric magnitudes are bounded to 1,000,000 SI units, and positive geometry dimensions/radii must be at least 1e-6 m. Readers require IFC4 metre length units. Finite numeric inputs are required; rotations, round sections, freeform geometry and unknown types/disciplines are rejected or outside this schema. Pipes use rectangular screening solids, not circular hydraulic sections.

## IFC and artifacts

- `architecture.ifc`: real IFC4 project/site/building/two storeys, `IfcWall`, `IfcSlab`, `IfcSpace`, `IfcOpeningElement` and `IfcRelVoidsElement` relationships. Spaces aggregate under storeys. Openings actually subtract from wall tessellation.
- `services.ifc`: matching spatial hierarchy, structural `IfcColumn`, `IfcDuctSegment`, `IfcPipeSegment`, `IfcUnitaryEquipment`, and site `IfcBuildingElementProxy` objects. The crane solid represents its tower and the hoist solid its rectangular envelope. The swing radius is a property and DXF circle, not a moving boom simulation.
- Distribution ports use IFC4 `IfcRelNests` and `IfcRelConnectsPorts`. The models store occurrence tags, discipline, clearance and flow in `StudyCoordination` properties. SI length/area/volume units are explicit; flow property names explicitly state m³/s.
- Element GUIDs use UUID5 of the persistent element ID, independent of output directory and input order. Use globally unique element IDs in this project namespace; changing an ID deliberately changes its identity.
- `schedule.csv` is extracted **after reopening the written IFC**, including tags, flow properties, geometry dimensions, tessellated net volume and GUIDs. It is not a copy of the input table. The opening dimensions describe the void cutter; wall dimensions are gross extents while wall volume is net of the opening.
- `issues.csv` and escaped `issues.html` contain issue IDs, element IDs, IFC GUIDs, world locations, distances and descriptions. They are **BCF-style issue lists, not a full BCF archive**: no BCF XML, snapshots or viewpoint packaging is claimed.
- `plan-L1.dxf` and `plan-L2.dxf` use metre units, discipline layers, labeled plan footprints and crane swing circles. The ordinal filenames follow the input storey sequence. They are schematic top-down footprints, including separate opening outlines, not section-cut working drawings.
- `coordination.obj` contains actual reopened IFC tessellation, with wall voids, grouped by IFC GUID. Spaces and opening cutter solids are omitted to keep the model view usable. It provides a lightweight geometry-only viewer export without IFC properties.

## Exact supported coordination rules

Hard clashes require a positive intersection volume between different disciplines. Touching faces/edges do not cause a hard clash. Walls are decomposed into nonoverlapping rectangular pieces after subtracting **each actual opening volume**. An overlapping service is clear only where it fits within that void; partial height/width overlap still hits wall material. Multiple rectangular cutters use sequential subtraction, preserving union semantics.

Clearance uses minimum Euclidean distance between the remaining physical solids, compared strictly with the maximum clearance assigned to either element. Equality at the requested boundary passes. Corner-to-corner distance is Euclidean, avoiding the false positives produced by expanding each bounding-box axis independently. Contact fails when a positive clearance is requested. A hard clash is reported instead of a duplicate clearance issue for that pair. A numerical length tolerance of 1e-8 m excludes numerical boundary noise.

Physical checks omit spaces, opening cutter solids, cranes and hoists. Structural elements and building services participate; normal intentional column/slab intersections can therefore appear as hard clashes and need review. Same-discipline self-coordination, join design, automatic classification of intentional penetrations, circular/rotated geometry, insulation thickness, arbitrary imported meshes and swept fittings are outside this demonstration.

A duct hitting remaining wall material additionally creates `unprovided_opening`. This is derived from geometry, not an `opening` label or existence of some unrelated void in the wall. Connectivity reports every explicitly modeled unconnected port, and detects noncoincident connected ports when IFC placements are subsequently edited. It does not solve fluid flow, detect unused elements with no ports, or certify system completeness.

Crane swing checks compare the tower plan center with the nearest point on each target footprint. A target strictly inside the swing radius is flagged; exact boundary contact passes. Elevation, boom/tail shape, capacity, working radius/load charts, oversailing rights, wind and lifting sequence are omitted. These are layout prompts, not lift plans or safety approvals.

## Expected demonstration and checks

The example contains a duct crossing a real service opening without a clash, one blocked duct hitting the partition and column, a clearance failure, touching/clearance-boundary/disjoint examples that remain clear, connected AHU/duct ports and three intentionally free ports. The pipe riser intersects the upper slab. The lower column also intersects that slab; the report deliberately leaves this visible rather than guessing whether the joint is intentional.

`python -m pytest tests/test_bim.py -q` reopens both IFCs, generates every represented product's geometry, checks actual opening volume, stable GUIDs, stored flow and changed properties, relationships/connectivity, exact and partial void cases, touching/clearance boundaries, diagonal gaps, escaped issue text, DXF reopening and the safe/unsafe hoists. The example files also pass IfcOpenShell IFC4 schema/EXPRESS validation.

## Opening in viewers and FreeCAD

Open `architecture.ifc` in an IFC-capable viewer such as Bonsai and add `services.ifc` to the same scene without coordinate offsets. Hide spaces/opening cutter objects if the viewer exposes them as visible solids. Select an issue by its IFC GUID, then compare the recorded world coordinates in metres. The CSV is a separate schedule/issue list; a viewer will not automatically import it as BCF.

In an installed FreeCAD build with IFC import available, use **File → Open** for `architecture.ifc`, then **File → Import** to add `services.ifc` into the same document. Import settings and IFC support depend on the installed FreeCAD build. As a geometry fallback, open/import `coordination.obj`; it carries geometry and GUID group names, without semantic IFC property sets. Open a plan DXF in a DXF-capable editor for editable layers and circles. GUI import was not automated here; reopening/tessellation was verified through IfcOpenShell and DXF through ezdxf.

## Primary references

The implementation follows [IfcOpenShell geometry processing](https://docs.ifcopenshell.org/ifcopenshell-python/geometry_processing.html) for `create_shape`, world-coordinate tessellation and volume extraction. [IfcOpenShell opening feature documentation](https://docs.ifcopenshell.org/autoapi/ifcopenshell/api/feature/add_feature/index.html) describes opening geometry and void relationships. The [buildingSMART IFC4 distribution-port definition](https://standards.buildingsmart.org/IFC/RELEASE/IFC4/FINAL/HTML/schema/ifcsharedbldgserviceelements/lexical/ifcdistributionport.htm) specifies port placement, flow direction and IFC4 nesting; [IfcOpenShell port connection documentation](https://docs.ifcopenshell.org/autoapi/ifcopenshell/api/system/connect_port/index.html) describes port connection semantics. These are interoperability references, not engineering design rules. Some buildingSMART IFC4.3 web pages returned access denied during source checking; the accessible IFC4 definition matches the schema generated here.
