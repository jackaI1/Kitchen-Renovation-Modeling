"""Export the composed SVG as PDF (print and contractor sizes) and PNG (sharing)."""
from pathlib import Path

import pypdfium2 as pdfium
from reportlab import rl_config
from reportlab.graphics import renderPDF
from svglib.svglib import svg2rlg

rl_config.invariant = 1  # no timestamps or random IDs, so the same input gives the same PDF bytes

POINTS_PER_INCH = 72
PRINT_INCHES = (24, 18)          # matches the existing 24 x 18 in sheet set
CONTRACTOR_INCHES = (11, 8.25)   # letter-width landscape, same 4:3 shape
SHARE_DPI = 125                  # 24 in x 125 dpi = 3000 px wide


def export_pdf(svg_path, pdf_path, inches):
    """Write the SVG as a PDF page of the given size in inches, scaling the drawing to fit."""
    drawing = svg2rlg(str(svg_path))
    width, height = inches[0] * POINTS_PER_INCH, inches[1] * POINTS_PER_INCH
    scale_x, scale_y = width / drawing.width, height / drawing.height
    if abs(scale_x - 1) > 1e-9 or abs(scale_y - 1) > 1e-9:
        drawing.scale(scale_x, scale_y)
    drawing.width, drawing.height = width, height
    Path(pdf_path).parent.mkdir(parents=True, exist_ok=True)
    renderPDF.drawToFile(drawing, str(pdf_path))
    return pdf_path


def pdf_page_points(pdf_path):
    document = pdfium.PdfDocument(str(pdf_path))
    try:
        if len(document) != 1:
            raise ValueError(f'{pdf_path} should have one page, found {len(document)}')
        return document[0].get_size()
    finally:
        document.close()


def export_png(pdf_path, png_path, dpi=SHARE_DPI):
    """Rasterise the print PDF with PDFium so the PNG matches the PDF page exactly."""
    document = pdfium.PdfDocument(str(pdf_path))
    try:
        image = document[0].render(scale=dpi / POINTS_PER_INCH).to_pil().convert('RGB')
    finally:
        document.close()
    image.save(str(png_path), optimize=True)
    return png_path, image.size
