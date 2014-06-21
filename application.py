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

# TODO: read from config.yaml instead
MAX_RETRIES = 30
RETRY_INTERVAL = 1
DEFAULT_NAME = 'migration_logs'

# TODO: Move to a configuration method, values retrieved from config.yaml and parse_args()
application.config['DEBUG'] = False
application.config['SECRET_KEY'] = 'ur7b3xfapm'


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
    workdir = application.config['WORKDIR']
    if not os.path.isabs(workdir):
        return 'Not an abs path: ' + workdir
        # raise ValueError('{0} not an absolute path'.format(workdir))
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
    return render_template('index.html', workdir='foobar')

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
        os.mkdir(os.path.dirname(fname))
    with open(fname, 'w') as file_out:
        file_out.write(request.data)
    resp_data = {
        'filename': fname,
        'saved': True,
        'file_size': os.path.getsize(fname)
    }
    logging.info('File {filename} saved, size {file_size} bytes'.format(**resp_data))
    return make_response(jsonify(resp_data))


@application.errorhandler(NotAuthorized)
def handle_invalid_usage(error):
    logging.error(error.message)
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response


def prepare_env():
    application.config['DEBUG'] = os.getenv('FLASK_DEBUG', True)
    application.config['TESTING'] = os.getenv('FLASK_TESTING', True)
    application.config['WORKDIR'] = os.getenv('FLASK_WORKDIR', '/tmp')


def run_server():
    loglevel = logging.DEBUG
    logging.basicConfig(format=FORMAT, datefmt=DATE_FMT, level=loglevel)
    prepare_env()
    application.run(host='0.0.0.0')


if __name__ == '__main__':
    run_server()
