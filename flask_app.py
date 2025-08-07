import os
import subprocess
from pathlib import Path
from threading import Thread

import yaml
from flask import Flask, render_template, request, redirect, url_for, flash
from flask import send_from_directory, jsonify
from flask_socketio import SocketIO

from imdb_extractor.movie_to_pdf_converter import execute
from settings import (
    secret_key,
    CONFIG_FILE_PATH,
    DATA_FOLDER,
    UPLOAD_FOLDER,
    get_full_output_parse_file_name,
    get_full_output_pdf_file_name,
    get_full_source_parse_file_name,
    FILE_TYPES,
    MOVIE_STATUSES,
)

app = Flask(__name__)
socketio = SocketIO(app)
app.secret_key = secret_key
app.config['DATA_FOLDER'] = DATA_FOLDER
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
LAST_COLLECTED_DATA_PATH = None


@app.context_processor
def handle_context():
    return dict(os=os)


@app.route('/', methods=['GET', 'POST'])
def edit_config():
    if request.method == 'POST':
        with open(CONFIG_FILE_PATH, 'r') as config_file:
            config = yaml.safe_load(config_file)

        # Handle file upload
        if 'parse_stage_source_filename' in request.files:
            file = request.files['parse_stage_source_filename']
            if file.filename != '':
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
                file.save(file_path)
                config['parse_stage']['source_filename'] = (
                    file.filename
                )  # Save filename in the config

        # Handle other form fields
        parse_stage_output_filename = request.form['parse_stage_output_filename']
        parse_stage_movie_status = request.form['parse_stage_movie_status']
        parse_stage_file_type = request.form['file_type']
        parse_stage_with_cast = (
            True if request.form.get('parse_stage_with_cast') == 'on' else False
        )
        pdf_stage_output_filename = request.form['pdf_stage_output_filename']

        # Save form data into the YAML config file
        config['parse_stage']['output_filename'] = parse_stage_output_filename
        config['parse_stage']['movie_status'] = parse_stage_movie_status
        config['parse_stage']['file_type'] = parse_stage_file_type
        config['parse_stage']['with_cast'] = parse_stage_with_cast
        config['pdf_stage']['output_filename'] = pdf_stage_output_filename

        with open(CONFIG_FILE_PATH, 'w') as config_file:
            yaml.dump(config, config_file)

        flash('Configuration saved successfully!', 'success')
        return redirect(url_for('edit_config'))

    with open(CONFIG_FILE_PATH, 'r') as config_file:
        config = yaml.safe_load(config_file)

    i_parse_name = get_full_source_parse_file_name()
    o_parse_name = get_full_output_parse_file_name()
    o_pdf_name = get_full_output_pdf_file_name()

    return render_template(
        'config_form.html',
        config=config,
        input_parse_name=i_parse_name,
        output_parse_name=o_parse_name,
        output_pdf_name=o_pdf_name,
        file_types=FILE_TYPES,
        movie_statuses=MOVIE_STATUSES,
    )


@app.route('/check_parsed_file', methods=['GET'])
def check_parsed_file():
    if os.path.exists(get_full_output_parse_file_name()):
        return jsonify({'file_exists': True})
    else:
        return jsonify({'file_exists': False})


@app.route('/check_pdf_file', methods=['GET'])
def check_pdf_file():
    if os.path.exists(get_full_output_pdf_file_name()):
        return jsonify({'file_exists': True})
    else:
        return jsonify({'file_exists': False})


def run_spider():
    """Run the Scrapy spider and emit output to the client."""
    check_if_the_file_exists_and_delete(get_full_output_parse_file_name())

    command = ['scrapy', 'runspider', 'movie_info_extractor.py']
    # command = ['scrapy', 'runspider', 'scraper.py']
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    while True:
        output = process.stdout.readline()
        if output == b'' and process.poll() is not None:
            break

    # Emit a final message when done
    socketio.emit('parse_output', {'data': 'Scraping completed!'})


@app.route('/run_parse', methods=['POST'])
def run_parse():
    thread = Thread(target=run_spider)
    thread.start()
    return redirect(url_for('edit_config'))


@socketio.on('connect')
def handle_connect():
    print('Client connected')


@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')


@app.route('/run_pdf', methods=['POST'])
def run_pdf():
    check_if_the_file_exists_and_delete(get_full_output_pdf_file_name())
    execute()
    flash('PDF creation completed!', 'success')
    return redirect(url_for('edit_config'))


@app.route('/download_parse_data', methods=['GET'])
def download_parse_data():
    return send_from_directory(
        app.config['DATA_FOLDER'],
        get_full_output_parse_file_name(False),
        as_attachment=True,
    )


@app.route('/download_pdf_data', methods=['GET'])
def download_pdf_data():
    return send_from_directory(
        app.config['DATA_FOLDER'],
        get_full_output_pdf_file_name(False),
        as_attachment=True,
    )


def check_if_the_file_exists_and_delete(path):
    file_path = Path(path)
    if file_path.exists():
        file_path.unlink()


if __name__ == '__main__':
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    app.run(port=8000, debug=True)
