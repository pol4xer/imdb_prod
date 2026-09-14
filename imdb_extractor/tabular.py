"""Small, shared CSV/XLSX boundary for local inputs and exports."""

import re
from pathlib import Path
from urllib.parse import urlparse
from zipfile import BadZipFile

import pandas as pd

REPORT_COLUMNS = [
    'name',
    'company_name',
    'summary',
    'stars',
    'director',
    'producer',
    'executive_producer',
    'company_production',
    'company_sales',
    'status',
    'movie_id',
    'agent_id',
    'movie_link',
    'agent_link',
]


def read_table(source_filename, *, header=0):
    if not source_filename:
        raise ValueError('Select a CSV or XLSX source file first.')
    path = Path(source_filename)
    if not path.is_file():
        raise ValueError('The source file does not exist. Upload or generate it first.')
    try:
        if path.suffix.lower() == '.csv':
            return pd.read_csv(path, header=header, keep_default_na=False)
        if path.suffix.lower() == '.xlsx':
            return pd.read_excel(path, header=header, keep_default_na=False)
    except (ValueError, OSError, UnicodeError, BadZipFile, pd.errors.ParserError) as error:
        raise ValueError('Cannot read the source file. Check its contents and format.') from error
    raise ValueError('Only CSV and XLSX source files are supported.')


def write_table(data, output_filename):
    path = Path(output_filename)
    if path.suffix.lower() not in {'.csv', '.xlsx'}:
        raise ValueError('Export format must be CSV or XLSX.')
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    if path.suffix.lower() == '.csv':
        frame.to_csv(path, index=False)
    else:
        frame.to_excel(path, index=False)
    return path


def company_id(link):
    """Accept a company URL, never an arbitrary scrape destination."""
    if not isinstance(link, str):
        return None
    parsed = urlparse(link.strip())
    if parsed.scheme not in {'https', 'http'} or parsed.hostname not in {
        'imdb.com',
        'www.imdb.com',
        'pro.imdb.com',
    }:
        return None
    match = re.fullmatch(r'/company/(co\d+)/?', parsed.path)
    return match.group(1) if match else None


def read_companies(source_filename):
    """Read named columns or the original two-column, headerless input."""
    frame = read_table(source_filename)
    frame.columns = [str(column).strip().lower() for column in frame.columns]
    if not {'name', 'link'}.issubset(frame.columns):
        frame = read_table(source_filename, header=None)
        if len(frame.columns) != 2 or frame.empty or not company_id(frame.iloc[0, 1]):
            raise ValueError('Company input must contain name and link columns.')
        frame.columns = ['name', 'link']
    if frame.empty:
        raise ValueError('The company source contains no rows.')
    result = []
    for index, row in frame.iterrows():
        name = str(row['name']).strip()
        identifier = company_id(row['link'])
        if not name or not identifier:
            raise ValueError(f'Company row {index + 1} needs a name and a valid IMDb company URL.')
        result.append({'name': name, 'link': row['link'], 'id': identifier})
    return result
