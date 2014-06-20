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
import json
import time
import logging

# Flask imports
from flask import (
    Flask,
    make_response,
    jsonify,
    render_template,
    redirect,
    request,
    url_for)

from flask.ext.login import login_required
from flask.ext.mongoengine import MongoEngine
from flask.ext.security import MongoEngineUserDatastore, Security, UserMixin, RoleMixin

# Third-party
import flask_security
import launchkey


# Constants for program execution - non-configurable
FORMAT = '%(asctime)-15s [%(levelname)s] %(message)s'
DATE_FMT = '%m/%d/%Y %H:%M:%S'

#: Flask App, must be global
app = Flask(__name__)

# TODO: read from config.yaml instead
# secret_key = "r10gohrohsd9o5v5p6vdc4vm9x7rvbek"
MAX_RETRIES = 30
RETRY_INTERVAL = 1

# TODO: Move to a configuration method, values retrieved from config.yaml and parse_args()
app.config['DEBUG'] = False
app.config['SECRET_KEY'] = 'secret'
app.config['MONGODB_DB'] = 'flask-security'
app.config['MONGODB_HOST'] = 'localhost'
app.config['MONGODB_PORT'] = 27017

#: Database connection object
db = MongoEngine(app)


# TODO: refactor into their own 'model' module
class Role(db.Document, RoleMixin):
    name = db.StringField(max_length=80, unique=True)
    description = db.StringField(max_length=255)


class User(db.Document, UserMixin):
    email = db.StringField(max_length=255, unique=True)
    password = db.StringField(max_length=255)
    active = db.BooleanField(default=True)
    confirmed_at = db.DateTimeField()
    roles = db.ListField(db.ReferenceField(Role), default=[])

# Setup Flask-Security
user_datastore = MongoEngineUserDatastore(db, User, Role)


# Create a user to test with
@app.before_first_request
def create_user():
    user_datastore.find_or_create_role('admin')
    user_datastore.find_or_create_role('user')
    if not user_datastore.find_user(email='admin'):
        user_datastore.create_user(email='admin',
                                   password='zekret',
                                   roles=['admin'])
    if not user_datastore.find_user(email='marco'):
        user_datastore.create_user(email='marco',
                                   password='zekret',
                                   roles=['user'])


class NotAuthorized(Exception):
    status_code = 401

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


def parse_args():
    """ Parse command line arguments and returns a configuration object
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--key-file', required=True,
                        help="The file containing the Private Key")
    parser.add_argument('-p', '--port', help="The port for the server to listen on",
                        default=5050)
    parser.add_argument('-v', '--verbose', action='store_true', help='Enables debug logging')
    parser.add_argument('--debug', action='store_true', help="Turns on debugging/testing mode and "
                                                             "disables authentication")
    return parser.parse_args()


# Views
@app.route('/')
@login_required
def home():
    user_id = 'unknown'
    if 'user_id' in request.args:
        user_id = request.args['user_id']
    return render_template('index.html', user_id=user_id)


@app.errorhandler(NotAuthorized)
def handle_invalid_usage(error):
    logging.error(error.message)
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response


def run_server():
    config = parse_args()
    loglevel = logging.DEBUG if config.verbose else logging.INFO
    logging.basicConfig(format=FORMAT, datefmt=DATE_FMT, level=loglevel)
    # Initialize the private key global
    if config.debug:
        logging.warn("Running in TESTING mode: this disables security checks, DO NOT use in "
                     "Production")
        app.config['DEBUG'] = True
        app.config['TESTING'] = True
    security = Security(app, user_datastore)
    app.run(port=config.port, debug=config.verbose)


if __name__ == '__main__':
    run_server()
