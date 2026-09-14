"""Explicit opt-in shared by the preserved live extractor experiments."""

import os


def require_live():
    if os.environ.get('IMDB_ENABLE_LIVE', '').lower() != 'true':
        raise ValueError(
            'Live extraction is disabled. Use the offline demo or explicitly set IMDB_ENABLE_LIVE=true.'
        )
