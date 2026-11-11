"""Command line: python -m sheet_kit --output output/sheet-kit [--photos DIR --gimp gimp]."""
import argparse
from pathlib import Path

from .build import build


def main(argv=None):
    parser = argparse.ArgumentParser(description='Build the kitchen title block and notes sheet exports.')
    parser.add_argument('--output', type=Path, default=Path('output/sheet-kit'))
    parser.add_argument('--data', type=Path, default=None, help='kitchen data JSON (default: sheet_kit/data/kitchen.json)')
    parser.add_argument('--template', type=Path, default=None, help='Inkscape SVG template (default: sheet_kit/template/title_block.svg)')
    parser.add_argument('--photos', type=Path, default=None, help='folder with raw site photos named <photo id>.jpg/.png')
    parser.add_argument('--gimp', default=None, help='GIMP executable used to clean the photos in batch mode')
    parser.add_argument('--photo-width', type=int, default=1500, help='pixel width of cleaned photos')
    args = parser.parse_args(argv)
    manifest = build(args.output, data_path=args.data, template_path=args.template,
                     photo_dir=args.photos, gimp=args.gimp, photo_width=args.photo_width)
    for item in manifest['files']:
        print(f"{item['name']}: {item['description']}")


if __name__ == '__main__':
    main()
