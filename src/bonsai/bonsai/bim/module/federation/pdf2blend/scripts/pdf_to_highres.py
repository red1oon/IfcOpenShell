#!/usr/bin/env python3
"""Convert survey PDF to high-resolution PNG"""

import fitz  # PyMuPDF
from pathlib import Path

def convert_pdf_to_png(pdf_path, output_path, dpi=300):
    """
    Convert PDF to high-resolution PNG

    Args:
        pdf_path: Path to PDF file
        output_path: Path for output PNG
        dpi: Resolution (300 = print quality, 150 = screen)
    """
    print(f"Converting PDF to PNG at {dpi} DPI...")

    doc = fitz.open(pdf_path)
    page = doc[0]  # First page

    # Calculate zoom factor for desired DPI (72 is default PDF DPI)
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)

    # Render page to pixmap
    pix = page.get_pixmap(matrix=matrix)

    # Save as PNG
    pix.save(output_path)

    print(f"Saved: {output_path}")
    print(f"Size: {pix.width} x {pix.height} pixels")
    print(f"File size: {Path(output_path).stat().st_size / 1024 / 1024:.1f} MB")

    doc.close()
    return pix.width, pix.height

if __name__ == "__main__":
    base = Path(__file__).parent
    pdf_path = base / "survey_PPD_Original_23nov2025.pdf"
    output_path = base / "survey_highres.png"

    if not pdf_path.exists():
        print(f"PDF not found: {pdf_path}")
        exit(1)

    width, height = convert_pdf_to_png(pdf_path, output_path, dpi=300)
