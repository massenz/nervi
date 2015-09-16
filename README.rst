maarathon-dos
=============

Stress-testing Marathon via a pool of threads executing repeated requests and measuring
response times.


Arguments
---------

The most up-to-date list of available CLI arguments, can be found running ``run_stress.py`` with
the ``--help`` option::

    $ ./run_stress.py --help
    usage: run_stress.py [-h] [--buckets BUCKETS] [--duration DURATION]
                         [--endpoint ENDPOINT] [--insecure] [--interval INTERVAL]
                         [--pool-size POOL_SIZE] [-p PORT] [--randomize]
                         [--stddev STDDEV] [--timeout TIMEOUT] [-v]
                         [--workdir WORKDIR]
                         ip

    positional arguments:
      ip                    The server's IP address

    optional arguments:
      -h, --help            show this help message and exit
      --buckets BUCKETS, -b BUCKETS
                            Number of buckets to distribute response data over
      --duration DURATION, -d DURATION
                            Duration of the test, in seconds
      --endpoint ENDPOINT   The URL for Marathon REST endpoint to hit
      --insecure            Whether to use HTTP instead of HTTPS
      --interval INTERVAL   Interval, in seconds, between requests (will be
                            assumed to be the mean value, if used in conjunction
                            with --randomize
      --pool-size POOL_SIZE
                            Size of thread pool to hit the server
      -p PORT, --port PORT  The port for the server to listen on
      --randomize           Whether to randomize the interval between requests
      --stddev STDDEV       If randomize is defined, will be the stddev for the
                            random interval distribution in seconds
      --timeout TIMEOUT, -t TIMEOUT
                            Max allowed timeout from the server, before
                            considering it dead
      -v, --verbose         Enables debug logging
      --workdir WORKDIR     Where to store files, must be an absolute path

A typical invocation looks something like::

    ./run_stress.py -p 8080 --workdir=/tmp/data --interval 5.00 \
        --duration 180 --timeout 15 --pool-size 200 130.211.173.235

this will create a pool of 200 threads each executing a ``GET`` every 5 seconds to the given IP
address, on port 8080, and hitting the default ``/v2/tasks`` endpoint.

The stress test will last approx 3 minutes (``duration`` is 180 seconds), after which the main
thread will wait for the pool of threads to complete and will exit orderly.


Output
------

Each ``GET`` request measures the time (in msec) that it takes the server to respond (any
response code will be accepted, including 404's and 5xx's) waiting at most ``timeout`` seconds
before considering the server unresponsive and exiting.

The response times are all recorded in a shared list (in a thread-safe manner, using a Lock) and
are also, post-processed into "buckets" (configurable via the ``buckets`` option; 20 by
default).

Thanks to the use of an exclusive lock, we can be reasonably confident that no data is lost;
however, due to the race among threads, the order of response times may be slightly inaccurate
(even though, at later times in the test, this issue should be alleviated;
see `Current Limitations`_ below).

Both lists are saved (in CSV format) in two files in ``workdir`` (in the example above, that
would be ``/tmp/data``)::

    $ ll data
    total 72
    -rw-r--r--@ 1 marco  staff   442B Sep 15 18:08 stress-test-buckets.csv
    -rw-r--r--@ 1 marco  staff    27K Sep 15 18:08 stress-test.csv


Current Limitations
-------------------

We currently start all the threads approximately at the exact same time; this means that at the
outset, the server is being immediately hit with the highest load; later on, however, due to the
random nature of the response times (and the fact that we wait ``interval`` seconds **from** the
time we receive the response, before issuing a new request, in each thread) the arrival times of
requests is spread out.

This obviously skews the results; further, it also means that any test that would require the
requests to be sent *exactly* every ``interval`` seconds, is currently not possible (the
modification to enable that is not too complex and could be added at a later time).

Also, we can currently hit only **one** endpoint; it would be nice if each thread were to
randomly hit different endpoints, chosen from a limited set (again, this change is pretty trivial
 too).

 Finally, we collect a limited subset of all possible network and server response metric, and we
 do not even attempt at making a statistical analysis of the data.
