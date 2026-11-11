"""Batch-clean site photos with GIMP (Script-Fu) so every photo has the frame's shape and look.

The GIMP script sheet_kit/gimp/clean_site_photo.scm is run once per photo in batch mode with no
window (gimp -i). It levels the tones, sharpens slightly, crops to the frame's aspect ratio and
scales to a fixed width, then saves a PNG. Nothing here runs GIMP unless a path is given.
"""
from pathlib import Path
import subprocess

SCRIPT = Path(__file__).resolve().parent / 'gimp' / 'clean_site_photo.scm'
EXTENSIONS = ('.jpg', '.jpeg', '.png', '.tif', '.tiff')
TIMEOUT_SECONDS = 240


def find_photo(photo_dir, photo_id):
    for extension in EXTENSIONS:
        for candidate in (Path(photo_dir) / f'{photo_id}{extension}', Path(photo_dir) / f'{photo_id}{extension.upper()}'):
            if candidate.is_file():
                return candidate
    return None


def _scheme_string(path):
    text = str(path)
    if '"' in text or '\\' in text:
        raise ValueError(f'path cannot be passed to GIMP safely: {text!r}')
    return f'"{text}"'


def clean_photo(gimp, source, destination, width, ratio):
    """Run GIMP in batch mode for one photo. Raises if GIMP does not write the output."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    call = f'(sheet-kit-clean-photo {_scheme_string(source)} {_scheme_string(destination)} {int(width)} {ratio:.6f})'
    command = [
        str(gimp), '-i', '--no-data', '--no-fonts', '--no-splash',
        '--batch-interpreter=plug-in-script-fu-eval',
        '-b', f'(load {_scheme_string(SCRIPT)})',
        '-b', call,
        '-b', '(gimp-quit 0)',
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
    if not destination.is_file():
        tail = (completed.stderr or completed.stdout)[-800:]
        raise RuntimeError(f'GIMP did not write {destination.name}: {tail}')
    return destination


def clean_photos(gimp, photo_dir, output_dir, photos, width, ratio_for):
    """Clean every photo listed in the data. Returns {photo id: cleaned PNG path}."""
    cleaned = {}
    for photo in photos:
        source = find_photo(photo_dir, photo['id'])
        if source is None:
            continue
        cleaned[photo['id']] = clean_photo(gimp, source, Path(output_dir) / f"{photo['id']}.png",
                                           width, ratio_for(photo['id']))
    return cleaned
