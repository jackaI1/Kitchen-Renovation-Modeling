"""Generate all synthetic renovation studies without servers or paid CAD tools."""
import argparse
import importlib
from html import escape
import json
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path(__file__).resolve().parent.parent/'examples', help='folder with electrical.json, mechanical.json, walls.json and building.json')
    parser.add_argument('--output', type=Path, default=Path('output'), help='folder for generated study artifacts')
    args = parser.parse_args(argv)
    try:
        inputs = {}
        for name, filename in [('electrical','electrical.json'),('mechanical','mechanical.json'),('envelope','walls.json'),('bim','building.json')]:
            inputs[name] = json.loads((args.input/filename).read_text())
        studies = {}
        for name in ['electrical','mechanical','envelope','bim','sheets']:
            module = importlib.import_module(f'renovation.{name}')
            studies[name] = module.run(inputs.get(name, {}), args.output/name)
        summary = {'scope':'Synthetic preliminary studies; review all warnings and method limits before interpreting results.', 'studies':studies}
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output/'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
        links = []
        for path in sorted(args.output.rglob('*')):
            if path.is_file() and path.name != 'index.html':
                relative = path.relative_to(args.output).as_posix()
                links.append(f'<li><a href="{escape(relative,quote=True)}">{escape(relative)}</a></li>')
        (args.output/'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Renovation study reports</title><style>body{max-width:850px;margin:2rem auto;padding:1rem;font:17px/1.6 system-ui}a{color:#175777}</style><h1>Renovation study reports</h1><p>I use these synthetic examples to compare services, wall layers and building coordination. Start with the calculation sheets and clash report, then open the JSON reports for numbers and warnings. IFC files open in an IFC viewer or FreeCAD; DXF drawings open in a CAD viewer.</p><p>These are preliminary learning studies, with no construction, permit or equipment approval. Assumptions and source tables are in the repository documentation.</p><ul>'+''.join(links)+'</ul></html>')
        print(f'Generated {len(studies)} studies in {args.output.resolve()}')
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
