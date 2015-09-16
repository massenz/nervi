#!/usr/bin/env python
#
# Copyright AlertAvert.com (c) 2013. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import print_function

import argparse
import logging
import os
import requests
import time

from utils import SaneBool, choose
from utils.buckets import Buckets
from utils.stress import StressRequestor

STRESS_TEST_CSV = 'stress-test.csv'
#: File name for the response data, raw, as obtained during the test.

STRESS_TEST_BUCKETS_CSV = 'stress-test-buckets.csv'
# File name for the actual data, distributed over a number of "buckets"

MIN_DATA_SIZE = 10
#: Minimum size for data sample to be considered valid

__author__ = 'marco'


FORMAT = '%(asctime)-15s [%(levelname)s] %(message)s'
DATE_FMT = '%m/%d/%Y %H:%M:%S'
MAX_RETRIES = 30
RETRY_INTERVAL = 1


def parse_args():
    """ Parse command line arguments and returns a configuration object
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--buckets', '-b', type=int, default=20,
                        help="Number of buckets to distribute response data over")
    parser.add_argument('--duration', '-d', type=int, default=30,
                        help="Duration of the test, in seconds")
    parser.add_argument('--endpoint', help='The URL for Marathon REST endpoint to hit',
                        default='/v2/tasks')
    parser.add_argument('--insecure', action='store_false',
                        help="Whether to use HTTP instead of HTTPS")
    parser.add_argument('--interval', type=float, default=0.5,
                        help="Interval, in seconds, between requests (will be assumed to be "
                             "the mean value, if used in conjunction with --randomize")
    parser.add_argument('--pool-size', type=int, default=20,
                        help="Size of thread pool to hit the server")
    parser.add_argument('-p', '--port', help="The port for the server to listen on", type=int,
                        default=80)
    parser.add_argument('--randomize', action='store_true',
                        help="Whether to randomize the interval between requests")
    parser.add_argument('--stddev', type=float, default=0.1,
                        help="If randomize is defined, will be the stddev for the random interval "
                             "distribution in seconds")
    parser.add_argument('--timeout', '-t', type=int, default=5,
                        help="Max allowed timeout from the server, before considering it dead")
    parser.add_argument('-v', '--verbose', action='store_true', help='Enables debug logging')
    parser.add_argument('--workdir', help="Where to store files, must be an absolute path",
                        default='/var/lib/migration-logs')
    parser.add_argument('ip', help="The server's IP address",
                        default="localhost")
    return parser.parse_args()


def prepare():
    """ Starts the server, after configuring some application values.
        This is **not** executed by the Beanstalk framework

    :return:
    """
    cfg = parse_args()
    verbose = SaneBool(choose('MARATHON_DOS_DEBUG', False, cfg, 'verbose'))

    loglevel = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(format=FORMAT, datefmt=DATE_FMT, level=loglevel)
    return cfg


def make_uri(cfg):
    """ Builds a complete URI from user-supplied configuration

    :rtype : str
    """
    scheme = 'http' if cfg.insecure else 'https'
    return "{scheme}://{cfg.ip}:{cfg.port}{cfg.endpoint}".format(scheme=scheme, cfg=cfg)


def run_test(conf):

    stressor = StressRequestor(url=make_uri(conf), count=conf.pool_size, interval=conf.interval,
                               duration=conf.duration, timeout=conf.timeout)
    try:
        stressor.run()
    except KeyboardInterrupt:
        stressor.abort()
        logging.info("Stress test terminated by the user")
        while not stressor.done:
            time.sleep(2)
            if not stressor.done:
                logging.warning("Waiting for threads to complete and exit...")

    return stressor.response_times


def save_data(conf, response_times):
    # TODO(marco): move the data save to a persistence class and allow user to choose format
    # TODO(marco): use the `csv` module instead of this homemade ugliness

    if len(response_times) < MIN_DATA_SIZE:
        logging.error("Not enough data ({}): data will not be saved.".format(response_times))
        return

    data = os.path.join(conf.workdir, STRESS_TEST_CSV)
    with open(data, 'w') as d:
        for val in response_times:
            d.write("{}\n".format(val))
    logging.info("Data saved in: {}".format(data))

    buckets = Buckets(response_times, conf.buckets)
    bucket_data = os.path.join(conf.workdir, STRESS_TEST_BUCKETS_CSV)
    with open(bucket_data, 'w') as d:
        d.write("Min: {b.lower_bound:.3f}, Max: {b.upper_bound:.3f}".format(
            b=buckets))
        x = buckets.lower_bound
        step = buckets.step
        for val in buckets.get_buckets():
            d.write("{:.4f},{:4f}\n".format(x, val))
            x += step
    logging.info("Response distribution saved in: {}".format(bucket_data))


if __name__ == '__main__':
    logging.info("Starting REST API stress tests")

    config = prepare()

    logging.info("Configuration values: {}".format(config))
    logging.info("URL to stress-test: {}".format(make_uri(config)))

    start = time.time()
    response_times = run_test(config)
    logging.info("Run completed in {}".format(time.time() - start))

    save_data(config, response_times)
