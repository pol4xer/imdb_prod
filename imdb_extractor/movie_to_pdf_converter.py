from collections import defaultdict
from datetime import datetime

import demjson3
import pandas as pd
from jinja2 import Environment, FileSystemLoader
from xhtml2pdf import pisa

from settings import get_full_source_pdf_file_name, get_full_output_pdf_file_name


def execute():
    source_filename = get_full_source_pdf_file_name()
    output_filename = get_full_output_pdf_file_name()

    def prepare_data(items):
        def check_list(d, def_value=None):
            if def_value is None:
                def_value = ['-']
            if not isinstance(d, str):
                return def_value
            return demjson3.decode(d) or def_value

        def check_str(dr, def_value='-'):
            if not isinstance(dr, str):
                return def_value
            return dr or def_value

        result = defaultdict(list)

        for item in items:
            result[item['company_name']].append(
                {
                    'title': item['name'],
                    'logline': check_str(item['summary']),
                    'cast': check_list(item['stars']),
                    'director': check_str(item['director']),
                    'producers': check_list(item['producer']),
                    'executive_producers': check_list(item['executive_producer']),
                    'production_companies': check_list(item['company_production']),
                    'status': item['status'],
                }
            )

        return dict(result)

    template = Environment(loader=FileSystemLoader('../templates')).get_template(
        'imdb_pdf.jinja'
    )

    data = pd.read_csv(source_filename).to_dict('records')
    data_to_render = prepare_data(data)
    output = template.render(
        date=datetime.now().strftime('%B %-d, %Y'), data_to_render=data_to_render
    )

    with open(output_filename, 'wb') as pdf_file:
        pisa.CreatePDF(output, dest=pdf_file)

    return output_filename


if __name__ == '__main__':
    execute()
