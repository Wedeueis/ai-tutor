"""§5.1 credibility-signal capture at parse time (RF1.5, ADR 0001).

The pure date/author coercion is tested directly; the format readers are
exercised against real files built in `tmp_path`, which needs no network and
no ML models — so only the PDF-via-fpdf2 cases carry the integration marker
that the Docling parser tests use."""

import re
from datetime import datetime

import pytest

from pipeline.adapters.docling.source_metadata import (
    _from_core_properties,
    _parse_pdf_date,
    read_document_metadata,
)
from pipeline.domain.source_document import DocumentMetadata

# --- coercion ------------------------------------------------------------


def test_a_pdf_date_becomes_the_yyyy_mm_dd_that_section_5_1_specifies():
    assert _parse_pdf_date("D:20240410211143Z") == "2024-04-10"
    assert _parse_pdf_date("D:20250811001530+00'00'") == "2025-08-11"


def test_a_pdf_date_missing_its_month_or_day_falls_back_to_january_first():
    assert _parse_pdf_date("D:2024") == "2024-01-01"
    assert _parse_pdf_date("D:202404") == "2024-04-01"


def test_an_unparseable_pdf_date_is_unknown_rather_than_a_guess():
    assert _parse_pdf_date(None) is None
    assert _parse_pdf_date("") is None
    assert _parse_pdf_date("April 2024") is None
    assert _parse_pdf_date("D:20241340") is None  # month 13


def test_an_unreadable_file_yields_empty_signals_rather_than_raising():
    """A missing credibility signal must never be a reason a document fails to
    ingest."""
    assert read_document_metadata("/nonexistent/file.pdf") == DocumentMetadata()


def test_a_format_with_no_metadata_reader_yields_empty_signals():
    assert read_document_metadata("photo.png") == DocumentMetadata()


# --- real documents ------------------------------------------------------


def test_docx_core_properties_are_read(tmp_path):
    docx = pytest.importorskip("docx")

    path = tmp_path / "note.docx"
    document = docx.Document()
    document.add_paragraph("Body text.")
    document.core_properties.author = "Ada Lovelace"
    document.core_properties.modified = datetime(2025, 3, 14, 9, 30)
    document.save(path)

    metadata = read_document_metadata(str(path))

    assert metadata.author == "Ada Lovelace"
    assert metadata.last_modified == "2025-03-14"


def test_a_document_declaring_no_author_reports_unknown_not_an_empty_author(tmp_path):
    """ADR 0001: absent means unknown, and unknown must stay neutral. An
    author of `""` would serialize into the vault as a real, empty value."""
    docx = pytest.importorskip("docx")

    path = tmp_path / "anonymous.docx"
    document = docx.Document()
    document.add_paragraph("Body text.")
    document.core_properties.author = ""
    document.save(path)

    assert read_document_metadata(str(path)).author is None


def test_pptx_core_properties_are_read(tmp_path):
    pptx = pytest.importorskip("pptx")

    path = tmp_path / "deck.pptx"
    presentation = pptx.Presentation()
    presentation.core_properties.author = "Grace Hopper"
    presentation.core_properties.modified = datetime(2024, 12, 1)
    presentation.save(path)

    metadata = read_document_metadata(str(path))

    assert metadata.author == "Grace Hopper"
    assert metadata.last_modified == "2024-12-01"


def test_xlsx_core_properties_are_read(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")

    path = tmp_path / "sheet.xlsx"
    workbook = openpyxl.Workbook()
    workbook.properties.creator = "Katherine Johnson"
    workbook.save(path)

    metadata = read_document_metadata(str(path))

    assert metadata.author == "Katherine Johnson"
    # openpyxl stamps `modified` with the save time and ignores whatever it was
    # set to, so the value can't be pinned from here — only that the field is
    # found and coerced to §5.1's shape. Real workbooks come from Excel, where
    # the date is the document's own.
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", metadata.last_modified or "")


def test_last_modified_falls_back_to_the_creation_date():
    """A document never revised since it was written still carries a genuine
    recency signal — its own creation date. Tested on the shared OOXML
    coercion because none of the writers here will emit a file with `modified`
    unset."""

    class NeverRevised:
        author = "Ada Lovelace"
        modified = None
        created = datetime(2021, 4, 2)

    assert _from_core_properties(NeverRevised()) == DocumentMetadata(
        author="Ada Lovelace", last_modified="2021-04-02"
    )


def test_a_document_with_neither_date_reports_no_recency_signal():
    class Undated:
        author = None
        modified = None
        created = None

    assert _from_core_properties(Undated()) == DocumentMetadata()


@pytest.mark.integration
def test_pdf_metadata_is_read_from_a_real_file(tmp_path):
    fpdf = pytest.importorskip("fpdf")

    path = tmp_path / "paper.pdf"
    pdf = fpdf.FPDF()
    pdf.set_author("Alan Turing")
    pdf.set_creation_date(datetime(2022, 8, 17))
    pdf.add_page()
    pdf.set_font("helvetica", size=12)
    pdf.cell(text="On computable numbers.")
    pdf.output(str(path))

    metadata = read_document_metadata(str(path))

    assert metadata.author == "Alan Turing"
    assert metadata.last_modified == "2022-08-17"
