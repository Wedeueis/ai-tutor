import pytest
from fpdf import FPDF

from pipeline.adapters.docling.document_parser import DoclingDocumentParser

pytestmark = pytest.mark.integration


def _make_fixture_pdf(path) -> None:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=16)
    pdf.cell(0, 10, "Espresso Brewing Report", ln=True)
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 8, "A good espresso uses a 1:2 ratio of coffee to water.")
    pdf.ln(5)
    pdf.set_font("Helvetica", size=11)
    with pdf.table() as table:
        header = table.row()
        for col in ("Dose (g)", "Yield (g)", "Time (s)"):
            header.cell(col)
        row = table.row()
        for value in ("18", "36", "28"):
            row.cell(value)
    pdf.output(str(path))


def test_parses_pdf_text_and_table(tmp_path):
    pdf_path = tmp_path / "report.pdf"
    _make_fixture_pdf(pdf_path)

    parser = DoclingDocumentParser(image_output_dir=tmp_path / "images")
    parsed = parser.parse(str(pdf_path))

    assert "Espresso Brewing Report" in parsed.text
    assert "1:2 ratio" in parsed.text
    assert "Dose" in parsed.text and "Yield" in parsed.text
