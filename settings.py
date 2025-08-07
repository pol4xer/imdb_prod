import yaml

secret_key = ''
CONFIG_FILE_PATH = 'config.yml'
UPLOAD_FOLDER = 'uploads/'
DATA_FOLDER = 'data/'
FILE_TYPES = ['csv', 'xlsx']
MOVIE_STATUSES = []


def open_config():
    with open(CONFIG_FILE_PATH) as config_file:
        config = yaml.safe_load(config_file)
    return config


def get_full_source_parse_file_name(with_folder=True):
    config = open_config()['parse_stage']
    if not config['source_filename']:
        return None
    return (UPLOAD_FOLDER if with_folder else '') + config['source_filename']


def get_full_output_parse_file_name(with_folder=True):
    config = open_config()['parse_stage']
    if not config['output_filename']:
        return None
    return (
        (DATA_FOLDER if with_folder else '')
        + config['output_filename']
        + f'.{config["file_type"]}'
    )


def get_full_source_pdf_file_name(with_folder=True):
    return get_full_output_parse_file_name(with_folder)


def get_full_output_pdf_file_name(with_folder=True):
    config = open_config()['pdf_stage']
    if not config['output_filename']:
        return None
    return (DATA_FOLDER if with_folder else '') + config['output_filename'] + '.pdf'
