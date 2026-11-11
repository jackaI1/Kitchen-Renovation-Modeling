# Sheet kit design notes

The sheet kit is one Inkscape title block and notes sheet (`sheet_kit/template/title_block.svg`) filled from `sheet_kit/data/kitchen.json`. The build writes the print PDF, contractor PDF, share PNG and a filled SVG from that one source.

## Files

- `sheet_kit/template/title_block.svg`: Inkscape SVG. The `Sheet` layer is exported. The `Guides` layer holds the text boxes and is removed from every export.
- `sheet_kit/data/kitchen.json`: sheet list, revision table, finish schedule, notes and photo captions. Values come from `AutoCAD/README.txt` and the project README.
- `sheet_kit/layout.py`: places text inside boxes, wraps notes and runs the fit checks.
- `sheet_kit/exports.py`: SVG to PDF (svglib with reportlab) and PDF to PNG (pypdfium2).
- `sheet_kit/photos.py` and `sheet_kit/gimp/clean_site_photo.scm`: GIMP batch cleanup of site photos (levels, light sharpening, crop to the frame shape, scale to a fixed width).
- `sheet_kit/build.py` and `sheet_kit/__main__.py`: the build command.
- `tests/test_sheet_kit.py`: export sizes, text fit, determinism, photo placement and the GIMP run.
- `.github/workflows/sheet-kit.yml`: runs the tests with Inkscape and GIMP installed, builds the sheets, and checks the output sizes.

## Commands

```sh
python -m pip install -r sheet_kit/requirements.txt
python -m sheet_kit --output output/sheet-kit
python -m sheet_kit --output output/sheet-kit --photos my-photos --gimp /Applications/GIMP.app/Contents/MacOS/gimp
```

Raw photos belong in a folder outside the repository and are named after the photo IDs in `kitchen.json` (`existing-range-wall.jpg`, `existing-sink-window.jpg`). They are not committed.

## Design choices

- **Units.** The sheet is 24 x 18 in and uses 2400 x 1800 user units, so one unit is 0.01 in. Font sizes and box sizes are in the same units.
- **Text fit is checked, not assumed.** The build measures every string with the Helvetica metrics that the PDF uses. A string wider than its box, or a block that runs past its box or table limit, raises an error. The build stops instead of writing a clipped sheet.
- **Boxes live in the SVG.** Moving a box in Inkscape moves its text on the next build. Data changes do not need any SVG edits.
- **Deterministic output.** reportlab invariant mode removes PDF timestamps, so the same inputs produce the same bytes. A test checks this.
- **Photos.** Photos are cropped by GIMP to the frame's aspect ratio. The build refuses a photo whose shape differs from its frame by more than 1 percent. An empty frame is labelled "(photo to add)" in its caption.
- **Contractor copy.** The contractor PDF is the same sheet scaled to letter width. The notes say to take measurements only from the 24 x 18 in print.

## Limits

- The overflow check covers text in the template. It does not check line art, photos drawn outside their frames, or text added by hand in Inkscape outside a box.
- Fonts are Helvetica, which matches Arial and Liberation Sans metrics. A different font in Inkscape can change the widths. Keep Helvetica or Arial for text that goes through the build.
- GIMP is only run where it is installed and an explicit `--gimp` path is given. The GIMP script was written for GIMP 2.10 Script-Fu, and CI runs it there.
