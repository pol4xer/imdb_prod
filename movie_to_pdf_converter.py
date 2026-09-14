"""Compatibility entry point for the original local report command."""

import runpy

if __name__ == '__main__':
    runpy.run_module('imdb_extractor.movie_to_pdf_converter', run_name='__main__')
