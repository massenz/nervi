from __future__ import print_function
import logging

import requests
import threading
import time

__author__ = 'marco'


class StressRequestor(object):
    """
    It will stress test an endpoint, by launching a number of concurrent requests.
    """

    SLEEP_INTERVAL = 0.500

    def __init__(self, url, count, interval, randomize=False, stddev=1.0, timeout=5, duration=30):
        self.url = url
        self.num_threads = count
        self.interval = interval
        self.randomize = randomize
        self.stddev = stddev

        self.timeout = timeout
        self.duration = duration

        self.pool = []
        self.response_times = []
        self.response_times_lock = threading.RLock()

        self.terminate = False
        self.done = False

    def _log(self, msg):
        logging.debug("{} -- {}".format(threading.current_thread().name, msg))

    def make_request(self):
        while not self.terminate:
            try:
                start = time.time()
                r = requests.get(self.url, timeout=self.timeout)
                end = time.time()
                response_time = (end - start) * 1000
                self._log("Request to {} returned {} in {} msec".format(
                    self.url,
                    r.status_code,
                    response_time
                ))
                with self.response_times_lock:
                    self.response_times.append(response_time)
            except requests.exceptions.Timeout:
                self._log("Request timed out, the server probably crashed; exiting")
                return
            except requests.exceptions.ConnectionError:
                self._log("Connection Error - the server probably crashed and cannot respond")
                return

            time.sleep(self.interval)

    def run(self):
        logging.info("Running Stressor with {} threads".format(self.num_threads))
        for num in xrange(self.num_threads):
            t = threading.Thread(target=self.make_request)
            t.start()
            self.pool.append(t)

        logging.info("Threads all started, waiting to complete...")

        # TODO(marco): use shorter intervals, and every so often check that there are still
        # active threads; no point in waiting the entirety of `duration` if all threads have quit
        # early (eg, the server is unreachable).
        sleep_until = time.time() + self.duration
        while time.time() < sleep_until and not self.terminate:
            time.sleep(StressRequestor.SLEEP_INTERVAL)
            for t in self.pool:
                if t.isAlive():
                    break  # breaks from the inner for; continues to wait
            else:
                break  # for-else: breaks out of the while and terminates the test
        self.terminate = True

        for t in self.pool:
            t.join()
        logging.info("Run complete, exiting")
        self.done = True

    def abort(self):
        self.terminate = True
