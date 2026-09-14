import io
import subprocess
from pathlib import Path

import pytest

from flask_app import create_app
from settings import get_full_output_parse_file_name, get_full_output_pdf_file_name, open_config


@pytest.fixture
def app(tmp_path):
    return create_app(
        {
            'TESTING': True,
            'IMDB_ROOT': str(tmp_path / 'runtime'),
            'IMDB_RUN_SYNCHRONOUS': True,
            'IMDB_ENABLE_LIVE': False,
        }
    )


@pytest.fixture
def client(app):
    return app.test_client()


def csrf(client):
    client.get('/')
    with client.session_transaction() as session:
        return {'X-CSRF-Token': session['csrf_token']}


def form(**changes):
    result = {
        'parse_stage_output_filename': 'demo_movies',
        'file_type': 'csv',
        'parse_stage_movie_status': '',
        'pdf_stage_output_filename': 'demo_report',
    }
    result.update(changes)
    return result


def save_source(client):
    response = client.post(
        '/',
        headers=csrf(client),
        data=form(
            parse_stage_source_filename=(
                io.BytesIO(b'name,link\nSample,https://pro.imdb.com/company/co0000001/\n'),
                'companies.csv',
            )
        ),
    )
    assert response.status_code == 302


def test_first_page_is_local_english_and_has_no_cdn(client):
    response = client.get('/')
    assert response.status_code == 200
    assert b'Load demo dataset' in response.data
    assert b'<html lang="en">' in response.data
    assert b'socket.io' not in response.data
    assert b'cdn' not in response.data
    assert client.get('/download_parse_data').status_code == 404
    assert client.get('/download_pdf_data').status_code == 404


@pytest.mark.parametrize('url', ['/', '/load_demo', '/run_parse', '/run_pdf'])
def test_mutations_require_csrf(client, url):
    assert client.post(url).status_code == 400


def test_non_ascii_csrf_is_rejected_without_server_error(client):
    csrf(client)
    assert client.post('/load_demo', headers={'X-CSRF-Token': 'é'}).status_code == 400


def test_untrusted_host_is_rejected(client):
    assert client.get('/', headers={'Host': 'untrusted.example'}).status_code == 400


def test_no_secrets_are_needed_for_demo_and_pdf(client, app, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError('The demo must not launch the live scraper')

    monkeypatch.setattr(subprocess, 'run', no_network)
    headers = csrf(client)
    assert client.post('/load_demo', headers=headers).status_code == 202
    status = client.get('/task_status').json
    assert status['status'] == 'completed'
    assert status['data_ready'] and not status['pdf_ready']
    data = client.get('/download_parse_data')
    assert data.status_code == 200
    assert len(data.data.splitlines()) == 4
    assert client.post('/run_pdf', headers=headers).status_code == 202
    status = client.get('/task_status').json
    assert status['status'] == 'completed'
    assert status['pdf_ready']
    assert client.get('/download_pdf_data').data.startswith(b'%PDF')
    assert 'attachment;' in client.get('/download_pdf_data').headers['Content-Disposition']


def test_new_dataset_invalidates_an_existing_report(client, app):
    headers = csrf(client)
    client.post('/load_demo', headers=headers)
    pdf = Path(get_full_output_pdf_file_name(paths=app.extensions['runtime_paths']))
    pdf.write_bytes(b'%PDF old report')
    assert client.get('/task_status').json['pdf_ready']
    client.post('/load_demo', headers=headers)
    assert not client.get('/task_status').json['pdf_ready']
    assert client.get('/download_pdf_data').status_code == 404


@pytest.mark.parametrize(
    'filename', ['../escape.csv', '/tmp/escape.csv', r'..\escape.csv', 'script.py']
)
def test_unsafe_upload_does_not_write_or_change_config(client, app, filename):
    response = client.post(
        '/',
        headers=csrf(client),
        data=form(parse_stage_source_filename=(io.BytesIO(b'private'), filename)),
        follow_redirects=True,
    )
    assert response.status_code == 200
    paths = app.extensions['runtime_paths']
    assert open_config(paths)['parse_stage']['source_filename'] == ''
    assert not paths.uploads.exists()


def test_output_path_traversal_and_missing_fields_show_errors(client, app):
    headers = csrf(client)
    response = client.post(
        '/',
        headers=headers,
        data=form(pdf_stage_output_filename='../escape'),
        follow_redirects=True,
    )
    assert b'paths are not allowed' in response.data
    response = client.post('/', headers=headers, data={}, follow_redirects=True)
    assert b'Complete all export settings' in response.data
    assert not app.extensions['runtime_paths'].config_file.exists()


def test_save_persists_upload_and_invalidates_data_when_options_change(client, app):
    headers = csrf(client)
    client.post('/load_demo', headers=headers)
    save_source(client)
    paths = app.extensions['runtime_paths']
    assert (paths.uploads / 'companies.csv').is_file()
    assert open_config(paths)['parse_stage']['source_filename'] == 'companies.csv'
    assert not client.get('/task_status').json['data_ready']
    response = client.post('/', headers=headers, data=form(file_type='xlsx'), follow_redirects=True)
    assert b'Your local settings have been saved' in response.data
    assert open_config(paths)['parse_stage']['file_type'] == 'xlsx'


def test_missing_inputs_and_disabled_live_do_not_start_jobs(client, app):
    headers = csrf(client)
    assert client.post('/run_pdf', headers=headers).status_code == 400
    assert client.post('/run_parse', headers=headers).status_code == 403
    app.config['IMDB_ENABLE_LIVE'] = True
    assert client.post('/run_parse', headers=headers).status_code == 400
    assert client.get('/task_status').json['status'] == 'idle'


def test_failed_subprocess_never_reports_success_or_serves_partial_data(client, app, monkeypatch):
    save_source(client)
    app.config['IMDB_ENABLE_LIVE'] = True
    destination = Path(get_full_output_parse_file_name(paths=app.extensions['runtime_paths']))

    def failed_run(command, **kwargs):
        assert command[1:] == ['-m', 'imdb_extractor.movie_info_extractor']
        assert kwargs['capture_output'] is True
        assert kwargs['env']['IMDB_ROOT'] == str(app.extensions['runtime_paths'].root)
        destination.write_text('partial data')
        return subprocess.CompletedProcess(command, 1, b'', b'private diagnostic content')

    monkeypatch.setattr(subprocess, 'run', failed_run)
    assert client.post('/run_parse', headers=csrf(client)).status_code == 202
    status = client.get('/task_status').json
    assert status['status'] == 'failed'
    assert not status['data_ready']
    assert 'private' not in status['message']
    assert client.get('/download_parse_data').status_code == 404


def test_zero_exit_without_an_output_is_failure(client, app, monkeypatch):
    save_source(client)
    app.config['IMDB_ENABLE_LIVE'] = True
    monkeypatch.setattr(
        subprocess, 'run', lambda command, **kwargs: subprocess.CompletedProcess(command, 0)
    )
    client.post('/run_parse', headers=csrf(client))
    assert client.get('/task_status').json['status'] == 'failed'


def test_active_task_prevents_another_task_and_config_changes(client, app):
    headers = csrf(client)
    app.extensions['task_state'].update(status='running', kind='demo')
    assert client.post('/load_demo', headers=headers).status_code == 409
    response = client.post('/', headers=headers, data=form(), follow_redirects=True)
    assert b'Wait for the current task' in response.data
    assert not app.extensions['runtime_paths'].config_file.exists()
