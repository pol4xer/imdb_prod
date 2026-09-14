"""Validated configuration and local runtime paths shared by the CLI and web UI."""

import copy
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

FILE_TYPES = ['csv', 'xlsx']
MOVIE_STATUSES = ['', 'Development', 'Pre-production', 'Production', 'Post-production', 'Completed']
DEFAULT_CONFIG = {
    'parse_stage': {
        'source_filename': '',
        'output_filename': 'demo_movies',
        'file_type': 'csv',
        'movie_status': '',
        'with_cast': False,
    },
    'pdf_stage': {'output_filename': 'demo_report'},
}


@dataclass(frozen=True)
class RuntimePaths:
    """Keep uploads, exports and user settings outside the source checkout."""

    root: Path | str | None = None

    def __post_init__(self):
        root = self.root or os.environ.get('IMDB_ROOT')
        if root is None:
            root = Path.home() / '.local' / 'share' / 'imdb-portfolio'
        object.__setattr__(self, 'root', Path(root).expanduser().resolve())

    @property
    def config_file(self):
        return self.root / 'config.yml'

    @property
    def uploads(self):
        return self.root / 'uploads'

    @property
    def data(self):
        return self.root / 'data'

    def ensure(self):
        for directory in (self.root, self.uploads, self.data):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)


def validate_filename(value, *, stem=False):
    """Reject paths rather than silently rewriting a user's destination."""
    pattern = r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}' if stem else r'[A-Za-z0-9][A-Za-z0-9._-]{0,119}'
    if not isinstance(value, str) or not re.fullmatch(pattern, value) or '..' in value:
        raise ValueError(
            'Use a filename with letters, numbers, hyphens or underscores; paths are not allowed.'
        )
    return value


def local_file(directory, filename):
    """Do not follow an existing symlink outside its runtime directory."""
    validate_filename(filename)
    directory = Path(directory).resolve()
    candidate = directory / filename
    if candidate.resolve().parent != directory or candidate.is_symlink():
        raise ValueError('The file must stay inside its local runtime directory.')
    return candidate


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError('Configuration must be a YAML mapping.')
    result = copy.deepcopy(DEFAULT_CONFIG)
    for section in result:
        supplied = config.get(section, {})
        if not isinstance(supplied, dict):
            raise ValueError(f'{section} must be a YAML mapping.')
        for key in result[section]:
            if key in supplied:
                result[section][key] = supplied[key]
    parse = result['parse_stage']
    if parse['source_filename']:
        validate_filename(parse['source_filename'])
        if Path(parse['source_filename']).suffix.lower() not in {'.csv', '.xlsx'}:
            raise ValueError('The company source must be a CSV or XLSX file.')
    elif parse['source_filename'] != '':
        raise ValueError('The source filename must be text.')
    validate_filename(parse['output_filename'], stem=True)
    validate_filename(result['pdf_stage']['output_filename'], stem=True)
    if parse['file_type'] not in FILE_TYPES:
        raise ValueError('Choose CSV or XLSX for the data export.')
    if parse['movie_status'] not in MOVIE_STATUSES:
        raise ValueError('Choose a supported movie status.')
    if not isinstance(parse['with_cast'], bool):
        raise ValueError('Include cast must be true or false.')
    return result


def open_config(paths=None):
    paths = paths or RuntimePaths()
    if not paths.config_file.exists():
        return copy.deepcopy(DEFAULT_CONFIG)
    with paths.config_file.open(encoding='utf-8') as config_file:
        try:
            return validate_config(yaml.safe_load(config_file))
        except yaml.YAMLError as error:
            raise ValueError('The local configuration is not valid YAML.') from error


def save_config(config, paths=None):
    paths = paths or RuntimePaths()
    config = validate_config(config)
    paths.ensure()
    # Write atomically so the CLI never reads a partially saved configuration.
    fd, name = tempfile.mkstemp(prefix='.config-', dir=paths.root)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as config_file:
            yaml.safe_dump(config, config_file, sort_keys=False)
        Path(name).replace(paths.config_file)
    finally:
        Path(name).unlink(missing_ok=True)
    return config


def get_full_source_parse_file_name(with_folder=True, paths=None):
    paths = paths or RuntimePaths()
    filename = open_config(paths)['parse_stage']['source_filename']
    if not filename:
        return None
    return str(local_file(paths.uploads, filename)) if with_folder else filename


def get_full_output_parse_file_name(with_folder=True, paths=None):
    paths = paths or RuntimePaths()
    config = open_config(paths)['parse_stage']
    filename = f'{config["output_filename"]}.{config["file_type"]}'
    return str(local_file(paths.data, filename)) if with_folder else filename


def get_full_source_pdf_file_name(with_folder=True, paths=None):
    return get_full_output_parse_file_name(with_folder, paths)


def get_full_output_pdf_file_name(with_folder=True, paths=None):
    paths = paths or RuntimePaths()
    filename = open_config(paths)['pdf_stage']['output_filename'] + '.pdf'
    return str(local_file(paths.data, filename)) if with_folder else filename


# Legacy import names remain path-compatible; new code should use RuntimePaths.
CONFIG_FILE_PATH = str(RuntimePaths().config_file)
UPLOAD_FOLDER = str(RuntimePaths().uploads) + os.sep
DATA_FOLDER = str(RuntimePaths().data) + os.sep
