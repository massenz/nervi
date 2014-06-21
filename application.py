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
    redirect,
    request,
    url_for)


# Constants for program execution - non-configurable
FORMAT = '%(asctime)-15s [%(levelname)s] %(message)s'
DATE_FMT = '%m/%d/%Y %H:%M:%S'

#: Flask App, must be global
application = Flask(__name__)

#: When deployed on Beanstalk, ``application.config`` seems to be unavailable; using this instead
app_config = {}

# TODO: read from config.yaml instead
MAX_RETRIES = 30
RETRY_INTERVAL = 1
DEFAULT_NAME = 'migration_logs'

# TODO: Move to a configuration method, values retrieved from config.yaml and parse_args()
application.config['SECRET_KEY'] = 'ur7b3xfapm'

CONFIG_VARZ = ('DEBUG', 'TESTING', 'WORKDIR', 'SESSION_COOKIE_DOMAIN', 'SESSION_COOKIE_PATH',
               'RUNNING_AS')


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


def get_workdir():
    workdir = app_config.get('WORKDIR')
    if not workdir or not os.path.isabs(workdir):
        raise ValueError('{0} not an absolute path'.format(workdir))
    return workdir


def build_fname(migration_id, ext):
    workdir = get_workdir()
    timestamp = datetime.datetime.now().isoformat()
    # Remove msec part and replace colons with dots (just to avoid Windows stupidity)
    prefix = timestamp.rsplit('.')[0].replace(':', '.')
    return os.path.join(workdir, migration_id, '{prefix}_{name}.{ext}'.format(
        prefix=prefix, name=DEFAULT_NAME, ext=ext))


# Views
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
    for key in CONFIG_VARZ:
        varz = application.config.get(key) or app_config.get(key)
        if varz:
            configz[key.lower()] = str(varz)
    return make_response(jsonify(configz))


@application.route('/api/v1/<migration_id>', methods=['POST'])
def upload_data(migration_id):
    try:
        as_uuid = uuid.UUID(migration_id)
    except ValueError:
        raise UuidNotValid("Could not convert {0} to a valid UUID".format(migration_id))
    logging.info('Uploading binary data for {0}'.format(as_uuid))
    # TODO: use a query arg for the file name extension, or even the full name
    file_type = request.args.get('type', 'zip')
    fname = build_fname(migration_id, ext=file_type)
    if not os.path.exists(os.path.dirname(fname)):
        os.makedirs(os.path.dirname(fname), 2775)
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
    logging.basicConfig(format=FORMAT, datefmt=DATE_FMT, level=logging.DEBUG)
    prepare_env()


def prepare_env(config=None):
    """ Initializes the application configuration

    Must take into account that it may be started locally (via a command-line options) or
    remotely via AWS Beanstalk (in which case only the OS Env variables will be available).

    :param config: an optional L{Namespace} object, obtained from parsing the options
    :type config: argparse.Namespace or None
    """
    if not app_config.get('INITIALIZED'):
        application.config['DEBUG'] = os.getenv('FLASK_DEBUG', True) if not config else config.debug
        application.config['TESTING'] = os.getenv('FLASK_TESTING', True)
        app_config['WORKDIR'] = os.getenv('FLASK_WORKDIR', '/tmp') if not config else config.work_dir
        app_config['RUNNING_AS'] = os.getenv('USER', '')
        app_config['INITIALIZED'] = True


def parse_args():
    """ Parse command line arguments and returns a configuration object
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--port', help="The port for the server to listen on", type=int,
                        default=5050)
    parser.add_argument('-v', '--verbose', action='store_true', help='Enables debug logging')
    parser.add_argument('--debug', action='store_true', help="Turns on debugging/testing mode and "
                                                             "disables authentication")
    parser.add_argument('--work-dir', help="Where to store files, must be an absolute path",
                        default='/var/lib/migration-logs')
    return parser.parse_args()


def run_server():
    """ Starts the server, after configuring some application values.
        This is **not** executed by the Beanstalk framework

    :return:
    """
    config = parse_args()
    loglevel = logging.DEBUG if config.verbose else logging.INFO
    logging.basicConfig(format=FORMAT, datefmt=DATE_FMT, level=loglevel)
    prepare_env(config)
    application.run(host='0.0.0.0', debug=config.debug, port=config.port)


if __name__ == '__main__':
    run_server()
