"""Compatibility entry point for the original local script name."""

import runpy

if __name__ == '__main__':
    runpy.run_module('imdb_extractor.movie_info_extractor', run_name='__main__')
