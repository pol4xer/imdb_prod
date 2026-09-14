from pathlib import Path

import pytest

from settings import (
    RuntimePaths,
    get_full_output_parse_file_name,
    get_full_output_pdf_file_name,
    get_full_source_parse_file_name,
    local_file,
    open_config,
    save_config,
    validate_filename,
)


def test_first_run_has_safe_defaults_without_creating_files(tmp_path):
    paths = RuntimePaths(tmp_path / 'runtime')
    assert open_config(paths)['parse_stage']['source_filename'] == ''
    assert get_full_source_parse_file_name(paths=paths) is None
    assert not paths.root.exists()


def test_runtime_root_is_independent_of_working_directory(tmp_path, monkeypatch):
    root = tmp_path / 'local'
    monkeypatch.setenv('IMDB_ROOT', str(root))
    monkeypatch.chdir(tmp_path)
    config = open_config()
    config['parse_stage']['output_filename'] = 'my_movies'
    config['parse_stage']['file_type'] = 'xlsx'
    config['parse_stage']['cookies'] = {'ignored': 'never persisted'}
    save_config(config)
    assert Path(get_full_output_parse_file_name()) == root / 'data' / 'my_movies.xlsx'
    assert get_full_output_pdf_file_name(False) == 'demo_report.pdf'
    assert 'cookies' not in (root / 'config.yml').read_text()
    assert not (tmp_path / 'config.yml').exists()
    assert (root / 'config.yml').stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    'filename', ['../escape', '/tmp/escape', 'a/b', r'a\b', '..', 'a..csv', '']
)
def test_path_names_are_rejected(filename):
    with pytest.raises(ValueError):
        validate_filename(filename)


def test_external_symlink_is_rejected(tmp_path):
    directory = tmp_path / 'data'
    directory.mkdir()
    outside = tmp_path / 'private.csv'
    outside.write_text('private')
    (directory / 'movies.csv').symlink_to(outside)
    with pytest.raises(ValueError):
        local_file(directory, 'movies.csv')
    assert outside.read_text() == 'private'


@pytest.mark.parametrize(
    'section,key,value',
    [
        ('parse_stage', 'output_filename', '../escape'),
        ('parse_stage', 'source_filename', 'input.exe'),
        ('parse_stage', 'source_filename', None),
        ('parse_stage', 'file_type', 'html'),
        ('parse_stage', 'with_cast', 'false'),
        ('parse_stage', 'movie_status', 'unknown'),
        ('pdf_stage', 'output_filename', 'report.pdf'),
    ],
)
def test_bad_config_does_not_replace_saved_config(tmp_path, section, key, value):
    paths = RuntimePaths(tmp_path)
    config = save_config(open_config(paths), paths)
    before = paths.config_file.read_bytes()
    config[section][key] = value
    with pytest.raises(ValueError):
        save_config(config, paths)
    assert paths.config_file.read_bytes() == before


def test_invalid_yaml_has_a_readable_error(tmp_path):
    paths = RuntimePaths(tmp_path)
    paths.config_file.write_text('parse_stage: [unfinished')
    with pytest.raises(ValueError, match='valid YAML'):
        open_config(paths)
