from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest
from pypdf import PdfReader

from imdb_extractor import movie_to_pdf_converter as reports
from imdb_extractor.demo import write_demo_data
from imdb_extractor.tabular import read_table


@pytest.mark.parametrize('extension', ['csv', 'xlsx'])
def test_offline_export_and_real_pdf(tmp_path, extension, monkeypatch):
    source = write_demo_data(tmp_path / f'movies.{extension}')
    frame = read_table(source)
    assert len(frame) == 3
    assert not any(str(column).startswith('Unnamed:') for column in frame.columns)
    # The old template path failed when the command was launched elsewhere.
    monkeypatch.chdir(tmp_path)
    output = reports.execute(source, tmp_path / 'reports' / 'movies.pdf')
    reader = PdfReader(output)
    assert len(reader.pages) == 2
    text = '\n'.join(page.extract_text() for page in reader.pages)
    assert 'The Glass Harbor' in text
    assert 'A Pocket of Summer' in text
    assert 'Pre-production' in text
    assert 'fictional' in text


@pytest.mark.parametrize('value', ['["Alex Rowan"]', "['Alex Rowan']", ['Alex Rowan']])
def test_list_columns_accept_json_and_historical_literals(value):
    assert reports.list_value(value) == ['Alex Rowan']


@pytest.mark.parametrize(
    'value', ['__import__("os").system("echo bad")', '{"name": "Alex"}', '"Alex"', '[4]']
)
def test_list_columns_reject_code_and_wrong_shapes(value):
    with pytest.raises(ValueError):
        reports.list_value(value)


def test_report_escapes_every_interpolated_field():
    attack = '<img src="https://example.invalid/private">'
    html = reports.render_html(
        [
            {
                'name': attack,
                'company_name': attack,
                'summary': attack,
                'stars': [attack],
                'producer': [attack],
                'executive_producer': [attack],
                'company_production': [attack],
                'director': attack,
                'status': attack,
            }
        ],
        report_date=date(2026, 1, 1),
    )
    assert '<img' not in html
    assert '&lt;img' in html
    assert 'January 01, 2026' in html


@pytest.mark.parametrize(
    'uri',
    [
        'https://example.invalid/resource',
        'file:///etc/passwd',
        '/tmp/private.png',
        'data:image/png;base64,AAAA',
    ],
)
def test_pdf_resource_callback_rejects_all_resources(uri):
    with pytest.raises(ValueError, match='resource loading is disabled'):
        reports.deny_resource(uri, None)


def test_pdf_render_error_does_not_replace_previous_report(tmp_path, monkeypatch):
    source = write_demo_data(tmp_path / 'movies.csv')
    output = tmp_path / 'report.pdf'
    output.write_bytes(b'previous report')
    monkeypatch.setattr(reports.pisa, 'CreatePDF', lambda *args, **kwargs: SimpleNamespace(err=1))
    with pytest.raises(RuntimeError, match='no report was written'):
        reports.execute(source, output)
    assert output.read_bytes() == b'previous report'


def test_report_validates_required_columns_and_empty_exports(tmp_path):
    source = tmp_path / 'movies.csv'
    pd.DataFrame([{'wrong': 'value'}]).to_csv(source, index=False)
    with pytest.raises(ValueError, match='missing columns: company_name, name'):
        reports.execute(source, tmp_path / 'report.pdf')
    source.write_text('name,company_name\n')
    with pytest.raises(ValueError, match='no rows'):
        reports.execute(source, tmp_path / 'report.pdf')


def test_bad_list_reports_its_row_number():
    with pytest.raises(ValueError, match='Report row 2:'):
        reports.prepare_data([{'name': 'A'}, {'name': 'B', 'stars': '{invalid}'}])


def test_missing_and_unsupported_source_errors_are_readable(tmp_path):
    with pytest.raises(ValueError, match='does not exist'):
        reports.execute(tmp_path / 'missing.csv', tmp_path / 'report.pdf')
    source = tmp_path / 'movies.txt'
    source.write_text('movie')
    with pytest.raises(ValueError, match='Only CSV and XLSX'):
        reports.execute(source, tmp_path / 'report.pdf')
