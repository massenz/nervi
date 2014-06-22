# Copyright AlertAvert.com (c) 2013. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Standard imports
import argparse
import datetime
import logging
import os

# Flask imports
import uuid
from flask import (
    Flask,
    make_response,
    jsonify,
    render_template,
    request)

from utils import choose, SaneBool

# TODO: move all logging configuration into its own logging.conf file
FORMAT = '%(asctime)-15s [%(levelname)s] %(message)s'
DATE_FMT = '%m/%d/%Y %H:%M:%S'

#: Flask App, must be global
application = Flask(__name__)


# TODO: read from config.yaml instead
MAX_RETRIES = 30
RETRY_INTERVAL = 1
DEFAULT_NAME = 'migration_logs'

SENSITIVE_KEYS = ('SESSION_COOKIE_DOMAIN', 'SESSION_COOKIE_PATH', 'RUNNING_AS', 'SECRET_KEY')


class ResponseError(Exception):
    status_code = 400

    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['message'] = self.message
        return rv


class NotAuthorized(ResponseError):
    status_code = 401


class UuidNotValid(ResponseError):
    status_code = 406


class FileNotFound(ResponseError):
    status_code = 404


def get_workdir():
    workdir = application.config.get('WORKDIR')
    if not workdir or not os.path.isabs(workdir):
        raise ResponseError('{0} not an absolute path'.format(workdir))
    return workdir


def build_fname(migration_id, ext):
    workdir = get_workdir()
    timestamp = datetime.datetime.now().isoformat()
    # Remove msec part and replace colons with dots (just to avoid Windows stupidity)
    prefix = timestamp.rsplit('.')[0].replace(':', '.')
    return os.path.join(workdir, migration_id, '{prefix}_{name}.{ext}'.format(
        prefix=prefix, name=DEFAULT_NAME, ext=ext))


def find_most_recent(migration_id, ext):
    """ Returns the most recent file matching the given extension, for the Migration ID

    :param migration_id: the unique ID of the migration for the logs
    :param ext: the file extension
    :return: the most recent filename that matches the ID and extension
    :raises: FileNotFound if the file does not exist
    """
    workdir = os.path.join(get_workdir(), migration_id)
    files = [f for f in os.listdir(workdir) if os.path.isfile(os.path.join(workdir, f))]
    files.sort(reverse=True)
    for fname in files:
        # TODO: should match the pattern, beyond the simple extension matching
        if fname.endswith('.{ext}'.format(ext=ext)):
            return os.path.join(workdir, fname)
    raise FileNotFound("Could not find logs for {id}".format(id=migration_id))


def get_data(fname):
    if not os.path.exists(fname):
        raise FileNotFound("Could not find log files for {name}".format(name=fname))
    with open(fname, 'r') as logs_data:
        return logs_data.read()


#
# Views
#
@application.route('/')
def home():
    return render_template('index.html', workdir=get_workdir())


@application.route('/healthz')
def health():
    """ A simple health-chek endpoint (can be used as a heartbeat too).

    :return: a 200 OK status (and the string "ok")
    """
    return 'ok'


@application.route('/configz')
def get_configs():
    """ Configuration values

    :return: a JSON response with the currently configured application values
    """
    configz = {'health': health()}
    is_debug = application.config.get('DEBUG')
    for key in application.config.keys():
        # In a non-debug session, sensitive config values are masked
        # TODO: it would be probably better to hash them (with a secure hash such as SHA-256)
        # using the application.config['SECRET_KEY']
        if not is_debug and key in SENSITIVE_KEYS:
            varz = "*******"
        else:
            varz = application.config.get(key)
        # Basic types can be sent back as they are, others need to be converted to strings
        if varz is not None and not (isinstance(varz, bool) or isinstance(varz, int)):
            varz = str(varz)
        configz[key.lower()] = varz
    return make_response(jsonify(configz))


@application.route('/api/v1/<migration_id>', methods=['GET', 'HEAD'])
def download_data(migration_id):
    """ Retrieves the log files for a Migration

        If there are more than one set of log files with the given extension for the same ID,
        it will return the most recent.

    :param migration_id: the unique ID for the migration logs we want to retrieve
    :type migration_id: ```uuid.UUID```
    :return: a response that will direct the client to download the file (instead of displaying
        it in the browser), by using the "Content-Disposition" header
    """
    try:
        as_uuid = uuid.UUID(migration_id)
    except ValueError:
        raise UuidNotValid("Could not convert {0} to a valid UUID".format(migration_id))
    logging.info('Downloading logs data for {0}'.format(as_uuid))
    # TODO: use a query arg for the file name extension, or even the full name
    file_type = request.args.get('type', 'zip')
    fname = find_most_recent(migration_id, ext=file_type)
    response = make_response()
    response.headers["Content-Disposition"] = "attachment; filename={name}".format(
        name=os.path.basename(fname))
    response.data = get_data(fname)
    return response


@application.route('/api/v1/<migration_id>', methods=['POST'])
def upload_data(migration_id):
    try:
        as_uuid = uuid.UUID(migration_id)
    except ValueError:
        raise UuidNotValid("Could not convert {0} to a valid UUID".format(migration_id))
    logging.info('Uploading compressed logs data for {0}'.format(as_uuid))
    file_type = request.args.get('type', 'zip')
    fname = build_fname(migration_id, ext=file_type)
    if not os.path.exists(os.path.dirname(fname)):
        os.makedirs(os.path.dirname(fname), 0775)
    with open(fname, 'w') as file_out:
        file_out.write(request.data)
    resp_data = {
        'filename': fname,
        'saved': True,
        'file_size': os.path.getsize(fname)
    }
    logging.info('File {filename} saved, size {file_size} bytes'.format(**resp_data))
    return make_response(jsonify(resp_data))


@application.errorhandler(ResponseError)
def handle_invalid_usage(error):
    logging.error(error.message)
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response


@application.before_first_request
def config_app():
    prepare_env()


def prepare_env(config=None):
    """ Initializes the application configuration

    Must take into account that it may be started locally (via a command-line options) or
    remotely via AWS Beanstalk (in which case only the OS Env variables will be available).

    :param config: an optional L{Namespace} object, obtained from parsing the options
    :type config: argparse.Namespace or None
    """
    if not application.config.get('INITIALIZED'):
        # app_config['RUNNING_AS'] = choose('USER', '', config)
        verbose = SaneBool(choose('FLASK_DEBUG', False, config, 'verbose'))

        # Loggin configuration
        # TODO: move to a loogin.yaml configuration with proper handlers and loggers configuration
        loglevel = logging.DEBUG if verbose else logging.INFO
        logging.basicConfig(format=FORMAT, datefmt=DATE_FMT, level=loglevel)

        # Flask application configuration
        application.config['DEBUG'] = SaneBool(choose('FLASK_DEBUG', False, config, 'debug'))
        application.config['TESTING'] = choose('FLASK_TESTING', False)
        application.config['SECRET_KEY'] = choose('FLASK_SECRET_KEY', 'd0n7useth15', config,
                                                  'secret_key')
        application.config['WORKDIR'] = choose('FLASK_WORKDIR', '/tmp', config, 'workdir')

        application.config['INITIALIZED'] = True






