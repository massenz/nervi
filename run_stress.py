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

__author__ = 'marco'


FORMAT = '%(asctime)-15s [%(levelname)s] %(message)s'
DATE_FMT = '%m/%d/%Y %H:%M:%S'
MAX_RETRIES = 30
RETRY_INTERVAL = 1


def parse_args():
    """ Parse command line arguments and returns a configuration object
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--port', help="The port for the server to listen on", type=int,
                        default=8080)
    parser.add_argument('-v', '--verbose', action='store_true', help='Enables debug logging')
    parser.add_argument('--debug', action='store_true', help="Turns on debugging/testing mode and "
                                                             "disables authentication")
    parser.add_argument('--workdir', help="Where to store files, must be an absolute path",
                        default='/var/lib/migration-logs')
    parser.add_argument('--endpoint', help='The URL for Marathon REST endpoint to hit',
                        default='/v2/tasks')
    parser.add_argument('--ip', help="The Marathon server's IP address",
                        default="localhost")
    parser.add_argument('--insecure', action='store_false',
                        help="Whether to use HTTP instead of HTTPS")
    parser.add_argument('--pool-size', type=int, default=20,
                        help="Size of thread pool to hit the server")
    parser.add_argument('--randomize', action='store_true',
                        help="Whether to randomize the interval between requests")
    parser.add_argument('--interval', type=float, default=0.5,
                        help="Interval, in seconds, between requests (will be assumed to be "
                             "the mean value, if used in conjunction with --randomize")
    parser.add_argument('--stddev', type=float, default=0.1,
                        help="If randomize is defined, will be the stddev for the random interval "
                             "distribution in seconds")
    parser.add_argument('--duration', '-d', type=int, default=30,
                        help="Duration of the test, in seconds")
    parser.add_argument('--timeout', '-t', type=int, default=5,
                        help="Max allowed timeout from the server, before considering it dead")
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
    scheme = 'http' if cfg.insecure else 'https'
    return "{scheme}://{cfg.ip}:{cfg.port}{cfg.endpoint}".format(scheme=scheme, cfg=cfg)


def main(conf):
    start = time.time()
    logging.info("Starting Marathon REST API stress tests")
    logging.info("Configuration values: {}".format(conf))
    logging.info("URL to stress-test: {}".format(make_uri(conf)))

    stressor = StressRequestor(url=make_uri(conf), count=conf.pool_size, interval=conf.interval,
                               duration=conf.duration, timeout=conf.timeout)
    stressor.run()

    response_times = stressor.response_times
    data = os.path.join(conf.workdir, 'stress-test.csv')
    with open(data, 'w') as d:
        for val in response_times:
            d.write("{}\n".format(val))
    logging.info("Data saved in: {}".format(data))
    logging.info("Finished in {}".format(time.time() - start))

    buckets = Buckets(response_times, 20)
    bucket_data = os.path.join(conf.workdir, 'stress-test-buckets.csv')
    with open(bucket_data, 'w') as d:
        d.write("Min: {b.lowever_bound}, Max: {b.upper_bound}, Buckets: {b.buckets}".format(
            b=buckets))
        for val in buckets.get_buckets():
            d.write("{}\n".format(val))
    logging.info("Response distribution saved in: {}".format(bucket_data))


if __name__ == '__main__':
    config = prepare()
    main(config)
