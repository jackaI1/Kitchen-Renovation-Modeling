"""Fill the Inkscape template from the kitchen data and check that every text fits its box.

Geometry is in SVG user units: the sheet is 2400 x 1800 units, so 1 unit = 0.01 inch.
Boxes come from the template's Guides layer. Text is placed from the box's top-left corner
(baseline = top + font size), so moving a box in Inkscape moves its text on the next build.
"""
import base64
import copy
from dataclasses import dataclass
import io
import re

from lxml import etree
from PIL import Image
from reportlab.pdfbase.pdfmetrics import stringWidth

SVG = 'http://www.w3.org/2000/svg'
XLINK = 'http://www.w3.org/1999/xlink'
SHEET_LAYER = 'layer-sheet'
PAD = 8.0          # inner padding on the left and right of each box, in units
DESCENT = 0.25     # fraction of font size reserved below the last baseline
ASPECT_TOLERANCE = 0.01


class FitError(ValueError):
    """Raised when text would overflow its box, so the build stops instead of clipping."""


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    w: float
    h: float


@dataclass
class Cell:
    name: str
    lines: list
    size: float
    bold: bool
    box: Box
    line_pitch: float


def _font(bold):
    return 'Helvetica-Bold' if bold else 'Helvetica'


def text_width(text, size, bold=False):
    """Width in user units. reportlab uses the same Helvetica metrics that the PDF export draws with."""
    return stringWidth(text, _font(bold), size)


def wrap(text, size, bold, width):
    lines, current = [], ''
    for word in text.split():
        candidate = word if not current else f'{current} {word}'
        if not current or text_width(candidate, size, bold) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def check_fit(cell):
    inner = cell.box.w - 2 * PAD
    for line in cell.lines:
        width = text_width(line, cell.size, cell.bold)
        if width > inner + 1e-9:
            raise FitError(f'{cell.name}: "{line}" is {width:.1f} units wide but its box allows {inner:.1f}')
    needed = cell.size + (len(cell.lines) - 1) * cell.line_pitch + DESCENT * cell.size
    if needed > cell.box.h + 1e-9:
        raise FitError(f'{cell.name}: {len(cell.lines)} line(s) need {needed:.1f} units of height, box has {cell.box.h:.1f}')


def _style_size(style):
    return float(re.search(r'font-size:([\d.]+)px', style).group(1))


def load_template(path):
    tree = etree.parse(str(path))
    root = tree.getroot()
    boxes, pitches, tables = {}, {}, {}
    for rect in root.iter(f'{{{SVG}}}rect'):
        ident = rect.get('id') or ''
        if ident.startswith('box:'):
            boxes[ident[4:]] = Box(float(rect.get('x')), float(rect.get('y')),
                                   float(rect.get('width')), float(rect.get('height')))
            if rect.get('data-line-pitch'):
                pitches[ident[4:]] = float(rect.get('data-line-pitch'))
    for group in root.iter(f'{{{SVG}}}g'):
        ident = group.get('id') or ''
        if ident.startswith('table:'):
            tables[ident[6:]] = {
                'pitch': float(group.get('data-pitch')),
                'size': float(group.get('data-font-size')),
                'columns': group.get('data-columns').split(','),
                'limit_y': float(group.get('data-limit-y')),
            }
    return tree, boxes, pitches, tables


def _table_rows(data):
    p = data
    return {
        'sheets': [[s['number'], s['title'], s['source']] for s in p['sheets']],
        'revisions': [[r['rev'], r['date'], r['change']] for r in p['revisions']],
        'finishes': [[f['item'], f['finish'], f['location'], f['status']] for f in p['finishes']],
    }


def _dynamic_text(data):
    project = data['project']
    values = {
        'title': project['title'],
        'subtitle': project['subtitle'],
        'date': f"Date {project['date']}",
        'revision': f"Revision {project['revision']}",
        'sheet-number': project['sheet_number'],
        'sheet-title': project['sheet_title'],
        'scale-note': project['scale_note'],
    }
    for index, photo in enumerate(data['photos'], start=1):
        values[f'caption:photo-{index}'] = photo['caption']
    return values


def build_cells(data, template, boxes, pitches, tables):
    """Return every text cell with its wrapped lines, after checking that each fits."""
    dynamic = _dynamic_text(data)
    cells = []
    for text in template.iter(f'{{{SVG}}}text'):
        ident = text.get('id') or ''
        if not ident.startswith('text:'):
            continue
        name = ident[5:]
        if name not in boxes:
            raise FitError(f'{ident} has no box:{name} in the Guides layer')
        size = _style_size(text.get('style'))
        bold = 'font-weight:bold' in text.get('style')
        box = boxes[name]
        if name == 'notes':
            lines, pitch = [], pitches['notes']
            for note in data['notes']:
                lines.extend(wrap(note, size, bold, box.w - 2 * PAD))
        else:
            value = dynamic.get(name)
            if value is None:
                value = ''.join(text.itertext()).strip()
            lines, pitch = [value], 0.0
        cells.append(Cell(ident, lines, size, bold, box, pitch))

    rows = _table_rows(data)
    for table_name, spec in tables.items():
        for index, row in enumerate(rows[table_name]):
            for column, value in zip(spec['columns'], row):
                base = boxes[f'table:{table_name}:{column}']
                box = Box(base.x, base.y + index * spec['pitch'], base.w, base.h)
                if box.y + box.h > spec['limit_y'] + 1e-9:
                    raise FitError(f'table {table_name} row {index + 1} runs past y={spec["limit_y"]:.0f}')
                cells.append(Cell(f'text:table:{table_name}:row-{index}:{column}', [value], spec['size'], False, box, 0.0))
    for cell in cells:
        check_fit(cell)
    return cells


def _text_element(cell):
    weight = 'font-weight:bold;' if cell.bold else ''
    element = etree.Element(f'{{{SVG}}}text', id=cell.name)
    element.set('style', f'font-family:Helvetica;{weight}font-size:{cell.size:g}px;fill:#111111')
    x = cell.box.x + PAD
    for index, line in enumerate(cell.lines):
        y = cell.box.y + cell.size + index * cell.line_pitch
        span = etree.SubElement(element, f'{{{SVG}}}tspan', x=f'{x:g}', y=f'{y:g}')
        span.text = line
    return element


def _photo_element(frame_box, png_bytes, ident):
    image = etree.Element(f'{{{SVG}}}image', id=ident)
    image.set('x', f'{frame_box.x:g}')
    image.set('y', f'{frame_box.y:g}')
    image.set('width', f'{frame_box.w:g}')
    image.set('height', f'{frame_box.h:g}')
    image.set('preserveAspectRatio', 'xMidYMid meet')
    image.set(f'{{{XLINK}}}href', 'data:image/png;base64,' + base64.b64encode(png_bytes).decode('ascii'))
    return image


def check_photo_aspect(png_path, frame_box):
    with Image.open(png_path) as image:
        width, height = image.size
    expected = frame_box.w / frame_box.h
    if abs((width / height) / expected - 1) > ASPECT_TOLERANCE:
        raise FitError(f'{png_path} is {width}x{height}, which does not match the frame aspect {expected:.3f}')
    return width, height


def compose(template, cells, boxes, photos):
    """Return a new SVG tree with text and photos placed and the Guides layer removed.

    photos: list of (frame index, cleaned PNG path) for frames that have a photo.
    """
    tree = copy.deepcopy(template)
    root = tree.getroot()
    sheet = next(g for g in root.iter(f'{{{SVG}}}g') if g.get('id') == SHEET_LAYER)
    for text in list(sheet.iter(f'{{{SVG}}}text')):
        if (text.get('id') or '').startswith('text:'):
            sheet.remove(text)
    for cell in cells:
        sheet.append(_text_element(cell))
    for index, png_path in photos:
        frame = boxes[f'photo:photo-{index}']
        check_photo_aspect(png_path, frame)
        with open(png_path, 'rb') as handle:
            sheet.append(_photo_element(frame, handle.read(), f'image:photo-{index}'))
    for group in list(root):
        if group.get('id') == 'layer-guides':
            root.remove(group)
    return tree
