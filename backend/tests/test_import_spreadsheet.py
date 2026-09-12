import io

import pytest
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.database import Base
from app.services.equipment_import import import_equipment_rows
from app.services.spreadsheet_io import build_xlsx_template, read_tabular_file, rows_to_pipe_text
from app.services.wizard_import import spreadsheet_to_wizard_text


@pytest.fixture
def db(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    get_settings.cache_clear()

    test_engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=test_engine)
    session = sessionmaker(bind=test_engine)()
    yield session
    session.close()
    get_settings.cache_clear()


def test_build_and_read_xlsx_template():
    content = build_xlsx_template(["a", "b"], ["1", "2"])
    rows = read_tabular_file(content, "template.xlsx")
    assert rows == [["a", "b"], ["1", "2"]]


def test_read_csv_semicolon():
    content = "description;quantity;unit\nstaal;8;stuks".encode()
    rows = read_tabular_file(content, "lines.csv")
    assert rows[0] == ["description", "quantity", "unit"]
    assert rows[1] == ["staal", "8", "stuks"]


def test_wizard_spreadsheet_to_text():
    rows = [
        ["description", "quantity", "unit"],
        ["staal hoekprofiel 80x80x8x6000", "8", "stuks"],
    ]
    text, has_header = spreadsheet_to_wizard_text(rows)
    assert has_header is True
    assert "staal hoekprofiel 80x80x8x6000 | 8 | stuks" in text


def test_recognised_headers_apply_their_column_order():
    rows = [["Aantal", "Omschrijving", "Eenheid"], ["5", "Machine parts", "pallet"]]
    text, has_header = spreadsheet_to_wizard_text(rows)
    assert has_header
    assert text == "Machine parts | 5 | pallet"


def test_rows_to_pipe_text_skips_header():
    rows = [["description", "quantity"], ["item a", "2"]]
    assert rows_to_pipe_text(rows, skip_header=True) == "item a | 2"


def test_import_equipment_from_xlsx(db: Session):
    wb = Workbook()
    ws = wb.active
    ws.append(["specifications", "length_cm", "width_cm", "height_cm", "wall_thickness_mm", "weight_kg", "aliases", "active"])
    ws.append(["TEST VEHICLE", "400", "180", "170", "6", "1500", "test vehicle", "yes"])
    buf = io.BytesIO()
    wb.save(buf)

    rows = read_tabular_file(buf.getvalue(), "import.xlsx")
    result = import_equipment_rows(db, rows)
    assert result.created == 1
    assert result.errors == []

    ws.cell(row=2, column=6, value="1600")  # the weight column
    buf2 = io.BytesIO()
    wb.save(buf2)
    rows2 = read_tabular_file(buf2.getvalue(), "import.xlsx")
    result2 = import_equipment_rows(db, rows2)
    assert result2.updated == 1
    assert result2.created == 0
