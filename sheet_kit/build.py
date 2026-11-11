"""Build every sheet export from the one Inkscape SVG template and the kitchen data.

Outputs (in the output folder):
  kitchen-sheets.svg                   filled, editable copy without guides
  kitchen-sheets-print-24x18.pdf       full size, prints at 100 percent on 24 x 18 in paper
  kitchen-sheets-contractor-11x8.25.pdf  letter-width copy to send to the contractor
  kitchen-sheets-share-3000x2250.png   image for messages and email
  manifest.json                         sizes, checks and cleaned photo list
"""
import copy
import hashlib
import json
from pathlib import Path

from lxml import etree

from . import exports, layout, photos

PACKAGE = Path(__file__).resolve().parent
DEFAULT_DATA = PACKAGE / 'data' / 'kitchen.json'
DEFAULT_TEMPLATE = PACKAGE / 'template' / 'title_block.svg'


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(output, data_path=None, template_path=None, photo_dir=None, gimp=None, photo_width=1500):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    data = json.loads(Path(data_path or DEFAULT_DATA).read_text(encoding='utf-8'))
    tree, boxes, pitches, tables = layout.load_template(template_path or DEFAULT_TEMPLATE)
    template = tree.getroot()

    frame_ratio = {}
    for index, photo in enumerate(data['photos'], start=1):
        box = boxes[f'photo:photo-{index}']
        frame_ratio[photo['id']] = box.w / box.h

    cleaned = {}
    if photo_dir and gimp:
        cleaned = photos.clean_photos(gimp, photo_dir, output / 'photos', data['photos'], photo_width,
                                      lambda photo_id: frame_ratio[photo_id])
    elif photo_dir:
        for photo in data['photos']:
            found = photos.find_photo(photo_dir, photo['id'])
            if found is not None:
                cleaned[photo['id']] = found

    # Captions say so when a frame is still empty; the sheet still builds.
    for index, photo in enumerate(data['photos'], start=1):
        if photo['id'] not in cleaned:
            photo['caption'] = f"{photo['caption']} (photo to add)"

    cells = layout.build_cells(data, template, boxes, pitches, tables)
    photo_pairs = [(index, cleaned[photo['id']]) for index, photo in enumerate(data['photos'], start=1)
                   if photo['id'] in cleaned]
    composed = layout.compose(tree, cells, boxes, photo_pairs)

    svg_path = output / 'kitchen-sheets.svg'
    composed.write(str(svg_path), xml_declaration=True, encoding='UTF-8', pretty_print=False)

    print_pdf = exports.export_pdf(svg_path, output / 'kitchen-sheets-print-24x18.pdf', exports.PRINT_INCHES)
    contractor_pdf = exports.export_pdf(svg_path, output / 'kitchen-sheets-contractor-11x8.25.pdf', exports.CONTRACTOR_INCHES)
    png_path, png_size = exports.export_png(print_pdf, output / 'kitchen-sheets-share-3000x2250.png')

    files = [
        {'name': svg_path.name, 'description': 'editable filled sheet (open in Inkscape)'},
        {'name': print_pdf.name, 'description': 'print PDF, 24 x 18 in, 100 percent scale',
         'page_points': list(exports.pdf_page_points(print_pdf))},
        {'name': contractor_pdf.name, 'description': 'contractor PDF, 11 x 8.25 in',
         'page_points': list(exports.pdf_page_points(contractor_pdf))},
        {'name': png_path.name, 'description': 'share PNG at 125 dpi', 'pixels': list(png_size)},
    ]
    for item in files:
        item['sha256'] = _sha256(output / item['name'])
    manifest = {
        'project': data['project']['title'],
        'revision': data['project']['revision'],
        'photos_used': sorted(cleaned),
        'photos_missing': sorted(p['id'] for p in data['photos'] if p['id'] not in cleaned),
        'text_cells_checked': len(cells),
        'files': files,
    }
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    manifest['files'].append({'name': 'manifest.json', 'description': 'sizes, checks and photo list'})
    return manifest
