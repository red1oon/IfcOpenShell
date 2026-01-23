#!/usr/bin/env python3
"""
PDF to PNG Conversion - Step 1 of 2D-to-3D Pipeline

Converts PDF pages to high-resolution PNG images for Vision API processing.
"""

import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    print("ERROR: PyMuPDF not installed. Run: pip install PyMuPDF")
    sys.exit(1)


def pdf_to_png(pdf_path: str, output_dir: str, dpi: int = 300, pages: list = None):
    """
    Convert PDF pages to PNG images.

    Args:
        pdf_path: Path to input PDF
        output_dir: Directory for PNG outputs
        dpi: Resolution (300 recommended for architectural drawings)
        pages: List of page numbers to convert (1-indexed). None = all pages.

    Returns:
        List of output PNG paths
    """
    pdf_path = Path(pdf_path)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    doc = fitz.open(str(pdf_path))
    output_files = []

    # Determine which pages to convert
    if pages is None:
        page_indices = range(len(doc))
    else:
        page_indices = [p - 1 for p in pages if 0 < p <= len(doc)]

    print(f"Converting {pdf_path.name} ({len(doc)} pages) at {dpi} DPI")
    print(f"Pages to convert: {[i+1 for i in page_indices]}")
    print("-" * 50)

    for page_num in page_indices:
        page = doc[page_num]

        # High resolution matrix for text clarity
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)

        output_file = output_path / f"page{page_num + 1}.png"
        pix.save(str(output_file))

        print(f"  Page {page_num + 1}: {pix.width} x {pix.height} px -> {output_file.name}")
        output_files.append(output_file)

    doc.close()

    print("-" * 50)
    print(f"Done. {len(output_files)} PNG files created in {output_path}")

    return output_files


def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python pdf_to_png.py <pdf_path> [output_dir] [dpi] [pages]")
        print("")
        print("Examples:")
        print("  python pdf_to_png.py input.pdf")
        print("  python pdf_to_png.py input.pdf ../CACHE 300")
        print("  python pdf_to_png.py input.pdf ../CACHE 300 1,8")
        print("")
        print("Arguments:")
        print("  pdf_path   : Path to PDF file")
        print("  output_dir : Output directory (default: ../CACHE)")
        print("  dpi        : Resolution (default: 300)")
        print("  pages      : Comma-separated page numbers (default: all)")
        sys.exit(1)

    pdf_path = sys.argv[1]

    # Default output to CACHE folder relative to script
    script_dir = Path(__file__).parent.parent
    output_dir = sys.argv[2] if len(sys.argv) > 2 else str(script_dir / "CACHE")

    dpi = int(sys.argv[3]) if len(sys.argv) > 3 else 300

    pages = None
    if len(sys.argv) > 4:
        pages = [int(p.strip()) for p in sys.argv[4].split(",")]

    pdf_to_png(pdf_path, output_dir, dpi, pages)


if __name__ == "__main__":
    main()
