import copy
import json
import os
from pathlib import Path

import pytest
from lxml import etree
from PIL import Image

from sheet_kit import build as build_module
from sheet_kit import exports, layout, photos

DATA = Path(build_module.DEFAULT_DATA)
TEMPLATE = Path(build_module.DEFAULT_TEMPLATE)
SVG_NS = layout.SVG


@pytest.fixture(scope='module')
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp('sheet-kit')
    manifest = build_module.build(out)
    return out, manifest


def _data():
    return json.loads(DATA.read_text(encoding='utf-8'))


def test_export_sizes_match_their_paper(built):
    out, manifest = built
    sizes = {item['name']: item for item in manifest['files']}
    assert sizes['kitchen-sheets-print-24x18.pdf']['page_points'] == [1728.0, 1296.0]
    assert sizes['kitchen-sheets-contractor-11x8.25.pdf']['page_points'] == [792.0, 594.0]
    assert sizes['kitchen-sheets-share-3000x2250.png']['pixels'] == [3000, 2250]
    with Image.open(out / 'kitchen-sheets-share-3000x2250.png') as image:
        assert image.size == (3000, 2250)
    assert exports.pdf_page_points(out / 'kitchen-sheets-print-24x18.pdf') == (1728.0, 1296.0)
    assert exports.pdf_page_points(out / 'kitchen-sheets-contractor-11x8.25.pdf') == (792.0, 594.0)


def test_every_text_cell_fits_its_box(built):
    _, manifest = built
    assert manifest['text_cells_checked'] >= 80


def test_filled_svg_has_no_guides_and_keeps_text_ids(built):
    out, _ = built
    root = etree.parse(str(out / 'kitchen-sheets.svg')).getroot()
    labels = [g.get('{http://www.inkscape.org/namespaces/inkscape}label') for g in root.iter(f'{{{SVG_NS}}}g')]
    assert 'Sheet' in labels and not any('Guides' in (label or '') for label in labels)
    ids = {el.get('id') for el in root.iter(f'{{{SVG_NS}}}text')}
    assert {'text:title', 'text:notes', 'text:table:sheets:row-0:number'} <= ids


def test_overflowing_text_stops_the_build():
    data = _data()
    data['revisions'][0]['change'] = 'A revision description that is far too long for the change column in the table ' * 2
    tree, boxes, pitches, tables = layout.load_template(TEMPLATE)
    with pytest.raises(layout.FitError, match='revisions'):
        layout.build_cells(data, tree.getroot(), boxes, pitches, tables)


def test_too_many_note_lines_stop_the_build():
    data = _data()
    data['notes'] = [' '.join(['word'] * 60)] * 12
    tree, boxes, pitches, tables = layout.load_template(TEMPLATE)
    with pytest.raises(layout.FitError, match='notes'):
        layout.build_cells(data, tree.getroot(), boxes, pitches, tables)


def test_wrap_keeps_lines_inside_width():
    lines = layout.wrap('alpha beta gamma delta epsilon zeta eta theta iota kappa', 24, False, 200)
    assert len(lines) > 1
    assert all(layout.text_width(line, 24) <= 200 for line in lines)


def test_build_is_repeatable(tmp_path):
    first = build_module.build(tmp_path / 'a')
    second = build_module.build(tmp_path / 'b')
    hashes_a = {item['name']: item['sha256'] for item in first['files'] if 'sha256' in item}
    hashes_b = {item['name']: item['sha256'] for item in second['files'] if 'sha256' in item}
    assert hashes_a == hashes_b


def test_photos_are_placed_and_checked_for_frame_shape(tmp_path):
    photo_dir = tmp_path / 'photos'
    photo_dir.mkdir()
    Image.new('RGB', (1500, 600), (120, 90, 60)).save(photo_dir / 'existing-range-wall.png')
    manifest = build_module.build(tmp_path / 'out', photo_dir=photo_dir)
    assert manifest['photos_used'] == ['existing-range-wall']
    assert manifest['photos_missing'] == ['existing-sink-window']
    svg = (tmp_path / 'out' / 'kitchen-sheets.svg').read_text(encoding='utf-8')
    assert 'image:photo-1' in svg and 'image:photo-2' not in svg


def test_wrong_photo_shape_is_rejected(tmp_path):
    photo_dir = tmp_path / 'photos'
    photo_dir.mkdir()
    Image.new('RGB', (1000, 1000), (0, 0, 0)).save(photo_dir / 'existing-range-wall.png')
    with pytest.raises(layout.FitError, match='aspect'):
        build_module.build(tmp_path / 'out', photo_dir=photo_dir)


def test_photo_paths_with_quotes_are_refused(tmp_path):
    with pytest.raises(ValueError):
        photos.clean_photo('gimp', tmp_path / 'bad"name.jpg', tmp_path / 'out.png', 1500, 2.5)


@pytest.mark.skipif(not os.environ.get('SHEET_KIT_GIMP'), reason='set SHEET_KIT_GIMP to a GIMP executable to run the GIMP batch test')
def test_gimp_batch_crops_levels_and_scales(tmp_path):
    source = tmp_path / 'source.png'
    Image.new('RGB', (1600, 1000), (200, 180, 160)).save(source)
    destination = photos.clean_photo(os.environ['SHEET_KIT_GIMP'], source, tmp_path / 'clean.png', 1500, 2.5)
    with Image.open(destination) as image:
        assert image.size == (1500, 600)
