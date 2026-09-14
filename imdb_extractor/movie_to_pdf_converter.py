"""Render a local movie export as an escaped, self-contained PDF report."""

import ast
import json
from collections import defaultdict
from datetime import date
from io import BytesIO
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from xhtml2pdf import pisa

from imdb_extractor.tabular import read_table
from settings import get_full_output_pdf_file_name, get_full_source_pdf_file_name

TEMPLATES = Path(__file__).resolve().parents[1] / 'templates'


def text_value(value, default='—'):
    return value.strip() if isinstance(value, str) and value.strip() else default


def list_value(value):
    """Read JSON arrays and historical Python list literals without evaluating code."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return ['—']
    if isinstance(value, str):
        if len(value) > 100_000:
            raise ValueError('A list field exceeds the report size limit.')
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, RecursionError):
            try:
                value = ast.literal_eval(value)
            except (ValueError, SyntaxError, RecursionError) as error:
                raise ValueError(
                    'List fields must be JSON arrays or Python list literals.'
                ) from error
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError('List fields must contain a list of text values.')
    return [item.strip() for item in value if item.strip()] or ['—']


def prepare_data(items):
    result = defaultdict(list)
    for row_number, item in enumerate(items, start=1):
        try:
            result[text_value(item.get('company_name'), 'Unspecified company')].append(
                {
                    'title': text_value(item.get('name')),
                    'logline': text_value(item.get('summary')),
                    'cast': list_value(item.get('stars')),
                    'director': text_value(item.get('director')),
                    'producers': list_value(item.get('producer')),
                    'executive_producers': list_value(item.get('executive_producer')),
                    'production_companies': list_value(item.get('company_production')),
                    'status': text_value(item.get('status')),
                }
            )
        except ValueError as error:
            raise ValueError(f'Report row {row_number}: {error}') from error
    return dict(result)


def render_html(items, report_date=None):
    environment = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=True)
    template = environment.get_template('imdb_pdf.jinja')
    return template.render(
        date=(report_date or date.today()).strftime('%B %d, %Y'),
        data_to_render=prepare_data(items),
    )


def deny_resource(uri, relative_uri):
    # This report uses no images, stylesheets, fonts, or other external assets.
    raise ValueError('External and local resource loading is disabled in PDF reports.')


def execute(source_filename=None, output_filename=None):
    source_filename = source_filename or get_full_source_pdf_file_name()
    output_filename = output_filename or get_full_output_pdf_file_name()
    if not output_filename:
        raise ValueError('Choose a PDF output filename first.')
    output_path = Path(output_filename)
    if output_path.suffix.lower() != '.pdf':
        raise ValueError('The report output must use a .pdf extension.')
    if source_filename and Path(source_filename).resolve() == output_path.resolve():
        raise ValueError('The report output must not replace its source file.')
    data = read_table(source_filename)
    missing = {'name', 'company_name'} - set(data.columns)
    if missing:
        raise ValueError('Movie export is missing columns: ' + ', '.join(sorted(missing)))
    if data.empty:
        raise ValueError('The movie export contains no rows to report.')
    html = render_html(data.to_dict('records'))
    buffer = BytesIO()
    try:
        result = pisa.CreatePDF(html, dest=buffer, encoding='utf-8', link_callback=deny_resource)
    except Exception as error:
        raise RuntimeError('PDF rendering failed; check the report data.') from error
    if result.err:
        raise RuntimeError('PDF rendering failed; no report was written.')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(buffer.getvalue())
    return str(output_path)


if __name__ == '__main__':
    execute()
