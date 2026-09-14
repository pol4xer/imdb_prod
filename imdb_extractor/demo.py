"""Generate a report from fictional local data without cookies or network access."""

import argparse
from pathlib import Path

from imdb_extractor.movie_to_pdf_converter import execute
from imdb_extractor.tabular import read_table, write_table

FIXTURE_PATH = Path(__file__).resolve().parents[1] / 'examples' / 'movies.csv'


def write_demo_data(output_path):
    return write_table(read_table(FIXTURE_PATH), output_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('data/demo'))
    args = parser.parse_args()
    source = write_demo_data(args.output_dir / 'demo_movies.csv')
    report = execute(source, args.output_dir / 'demo_report.pdf')
    print(f'Fictional movie export: {source}')
    print(f'PDF report: {report}')


if __name__ == '__main__':
    main()
