"""A local, offline-first workbench for the IMDb extraction prototype."""

import hmac
import os
import secrets
import subprocess
import sys
from pathlib import Path
from threading import Lock, Thread

from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from settings import (
    FILE_TYPES,
    MOVIE_STATUSES,
    RuntimePaths,
    get_full_output_parse_file_name,
    get_full_output_pdf_file_name,
    get_full_source_parse_file_name,
    local_file,
    open_config,
    save_config,
    validate_config,
    validate_filename,
)

PROJECT_ROOT = Path(__file__).resolve().parent


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('IMDB_SECRET_KEY') or secrets.token_hex(32),
        IMDB_ROOT=os.environ.get('IMDB_ROOT'),
        IMDB_ENABLE_LIVE=os.environ.get('IMDB_ENABLE_LIVE', '').lower() == 'true',
        IMDB_RUN_SYNCHRONOUS=False,
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Strict',
        TRUSTED_HOSTS=['localhost', '127.0.0.1', '[::1]'],
    )
    if config:
        app.config.update(config)
    paths = RuntimePaths(app.config['IMDB_ROOT'])
    app.extensions['runtime_paths'] = paths
    state = {'status': 'idle', 'kind': None, 'message': 'Ready for an offline demo.'}
    lock = Lock()
    mutation_lock = Lock()
    app.extensions['task_state'] = state

    def csrf_token():
        if 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_hex(32)
        return session['csrf_token']

    app.jinja_env.globals['csrf_token'] = csrf_token

    @app.before_request
    def protect_local_mutations():
        if request.method == 'POST':
            supplied = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token', '')
            expected = session.get('csrf_token', '')
            if not expected or not hmac.compare_digest(supplied.encode(), expected.encode()):
                abort(400, description='Refresh this page before submitting the form.')
            # Serialize request preparation with saving settings. The background
            # worker is protected by its running state after the request returns.
            mutation_lock.acquire()
            g.holds_mutation_lock = True

    @app.teardown_request
    def release_mutation_lock(error=None):
        if g.pop('holds_mutation_lock', False):
            mutation_lock.release()

    def is_busy():
        with lock:
            return state['status'] == 'running'

    def artifact_path(kind):
        helper = get_full_output_pdf_file_name if kind == 'pdf' else get_full_output_parse_file_name
        return Path(helper(paths=paths))

    def artifact_exists(kind):
        path = artifact_path(kind)
        try:
            return path.is_file() and path.stat().st_size > 0
        except FileNotFoundError:
            return False

    def launch(kind, action):
        with lock:
            if state['status'] == 'running':
                return jsonify(error='Wait for the current task to finish.'), 409
            state.update(status='running', kind=kind, message='Preparing your files…')

        def work():
            try:
                action()
            except Exception as error:
                # Keep subprocess stderr, cookies and machine paths out of the UI.
                app.logger.warning('%s task failed (%s)', kind, type(error).__name__)
                with lock:
                    state.update(
                        status='failed',
                        message='The task failed. No new export was produced. Check your local setup and try again.',
                    )
            else:
                with lock:
                    state.update(
                        status='completed',
                        message={
                            'demo': 'Demo dataset ready: three fictional movie records.',
                            'pdf': 'Your PDF report is ready to download.',
                            'parse': 'Collection completed. Your data export is ready.',
                        }[kind],
                    )

        if app.config['IMDB_RUN_SYNCHRONOUS']:
            work()
        else:
            Thread(target=work, daemon=True).start()
        return jsonify(status='accepted'), 202

    @app.route('/', methods=['GET', 'POST'])
    def edit_config():
        current = open_config(paths)
        if request.method == 'POST':
            if is_busy():
                flash('Wait for the current task before changing its settings.', 'error')
                return redirect(url_for('edit_config'))
            try:
                previous_parse = dict(current['parse_stage'])
                previous_pdf = artifact_path('pdf')
                required = (
                    'parse_stage_output_filename',
                    'file_type',
                    'parse_stage_movie_status',
                    'pdf_stage_output_filename',
                )
                if any(key not in request.form for key in required):
                    raise ValueError('Complete all export settings before saving.')
                current['parse_stage'].update(
                    output_filename=request.form['parse_stage_output_filename'],
                    file_type=request.form['file_type'],
                    movie_status=request.form['parse_stage_movie_status'],
                    with_cast=request.form.get('parse_stage_with_cast') == 'on',
                )
                current['pdf_stage']['output_filename'] = request.form['pdf_stage_output_filename']
                upload = request.files.get('parse_stage_source_filename')
                if upload and upload.filename:
                    filename = validate_filename(upload.filename)
                    current['parse_stage']['source_filename'] = filename
                current = validate_config(current)
                if upload and upload.filename:
                    paths.ensure()
                    upload.save(local_file(paths.uploads, filename))
                save_config(current, paths)
                if current['parse_stage'] != previous_parse or (upload and upload.filename):
                    # Settings and source changes invalidate derived files, so an
                    # earlier export cannot appear to match a new configuration.
                    artifact_path('data').unlink(missing_ok=True)
                    previous_pdf.unlink(missing_ok=True)
                    artifact_path('pdf').unlink(missing_ok=True)
                with lock:
                    state.update(
                        status='idle',
                        kind=None,
                        message='Settings saved. Your next export will use these options.',
                    )
            except ValueError as error:
                flash(str(error), 'error')
                return redirect(url_for('edit_config'))
            flash('Your local settings have been saved.', 'success')
            return redirect(url_for('edit_config'))

        source = get_full_source_parse_file_name(paths=paths)
        return render_template(
            'config_form.html',
            config=current,
            file_types=FILE_TYPES,
            movie_statuses=MOVIE_STATUSES,
            live_enabled=app.config['IMDB_ENABLE_LIVE'],
            source_exists=bool(source and Path(source).is_file()),
            data_exists=artifact_exists('data'),
            pdf_exists=artifact_exists('pdf'),
            task_state=dict(state),
        )

    @app.get('/task_status')
    def task_status():
        with lock:
            response = dict(state)
        response.update(data_ready=artifact_exists('data'), pdf_ready=artifact_exists('pdf'))
        return jsonify(response)

    @app.post('/load_demo')
    def load_demo():
        destination = artifact_path('data')

        def action():
            from imdb_extractor.demo import write_demo_data

            paths.ensure()
            artifact_path('pdf').unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            try:
                write_demo_data(destination)
            except Exception:
                destination.unlink(missing_ok=True)
                raise

        return launch('demo', action)

    @app.post('/run_parse')
    def run_parse():
        if not app.config['IMDB_ENABLE_LIVE']:
            return jsonify(error='Live collection is disabled. Try the offline demo instead.'), 403
        source = get_full_source_parse_file_name(paths=paths)
        if not source or not Path(source).is_file():
            return jsonify(
                error='Upload and save a company CSV or XLSX before collecting data.'
            ), 400
        destination = artifact_path('data')

        def action():
            paths.ensure()
            save_config(open_config(paths), paths)
            artifact_path('pdf').unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            environment = os.environ.copy()
            environment['IMDB_ROOT'] = str(paths.root)
            environment['IMDB_ENABLE_LIVE'] = 'true'
            # run() drains both pipes; stderr cannot deadlock the worker.
            try:
                result = subprocess.run(
                    [sys.executable, '-m', 'imdb_extractor.movie_info_extractor'],
                    cwd=PROJECT_ROOT,
                    env=environment,
                    capture_output=True,
                    timeout=900,
                    check=False,
                )
                if (
                    result.returncode != 0
                    or not destination.is_file()
                    or destination.stat().st_size == 0
                ):
                    raise RuntimeError('Collection did not produce a successful export.')
            except Exception:
                destination.unlink(missing_ok=True)
                raise

        return launch('parse', action)

    @app.post('/run_pdf')
    def run_pdf():
        source = artifact_path('data')
        if not source.is_file() or source.stat().st_size == 0:
            return jsonify(error='Load the demo or collect a dataset before creating a PDF.'), 400
        destination = artifact_path('pdf')

        def action():
            from imdb_extractor.movie_to_pdf_converter import execute

            paths.ensure()
            destination.unlink(missing_ok=True)
            try:
                execute(str(source), str(destination))
                if not destination.is_file() or destination.stat().st_size == 0:
                    raise RuntimeError('PDF creation did not produce an export.')
            except Exception:
                destination.unlink(missing_ok=True)
                raise

        return launch('pdf', action)

    @app.get('/check_parsed_file')
    def check_parsed_file():
        return jsonify(file_exists=artifact_exists('data'))

    @app.get('/check_pdf_file')
    def check_pdf_file():
        return jsonify(file_exists=artifact_exists('pdf'))

    @app.get('/download_parse_data')
    def download_parse_data():
        if not artifact_exists('data'):
            abort(404)
        return send_file(artifact_path('data'), as_attachment=True)

    @app.get('/download_pdf_data')
    def download_pdf_data():
        if not artifact_exists('pdf'):
            abort(404)
        return send_file(artifact_path('pdf'), as_attachment=True)

    return app


if __name__ == '__main__':
    create_app().run(host='127.0.0.1', port=int(os.environ.get('IMDB_PORT', '8000')), debug=False)
