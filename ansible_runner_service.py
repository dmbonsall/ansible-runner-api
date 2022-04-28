#!/usr/bin/env python

# python2 or python3 compatible

import datetime
import logging
import logging.config
import os
import sched
import shutil
import signal
import sys
import threading
import time

import yaml

import runner_service.configuration as configuration
from runner_service.app import create_app
from runner_service.utils import fread

def signal_stop(*args):
    """
    Handle SIGTERM when running in the background
    """
    print("Shutting ansible-runner-service down - service stopped by admin")
    sys.exit(0)


def setup_logging():
    """ Setup logging """

    logging_config = configuration.settings.logging_conf
    pfx = configuration.settings.log_path

    if os.path.exists(logging_config):

        try:
            config = yaml.safe_load(fread(logging_config))
        except yaml.YAMLError as _e:
            print("ERROR: logging configuration error: {}".format(_e))
            sys.exit(12)

        fname = config.get('handlers').get('file_handler')['filename']

        full_path = os.path.join(pfx, fname)

        config.get('handlers').get('file_handler')['filename'] = full_path

        logging.config.dictConfig(config)
        logging.info("Loaded logging configuration from "
                     "{}".format(logging_config))
    else:
        logging.basicConfig(level=logging.DEBUG)
        logging.warning("Logging configuration file ({}) not found, using "
                        "basic logging".format(logging_config))


def setup_common_environment():

    setup_logging()
    logging.info("Run mode is: {}".format(configuration.settings.mode))


def remove_artifacts(scheduler, frequency):
    # Clean artifacts older than artifacts_remove_age days.
    artifacts_dir = os.path.join(configuration.settings.playbooks_root_dir, "artifacts")
    if os.path.exists(artifacts_dir):
        dir_list = os.listdir(artifacts_dir)
        time_now = time.mktime(time.localtime())
        for artifacts in dir_list:
            mtime = os.path.getmtime(os.path.join(artifacts_dir, artifacts))
            time_difference = datetime.timedelta(seconds=time_now - mtime)
            if time_difference.days >= configuration.settings.artifacts_remove_age:
                shutil.rmtree(os.path.join(artifacts_dir, artifacts))

    # Reschedule next self-execution:
    scheduler.enter(frequency, 0, remove_artifacts, (scheduler, frequency))
    scheduler.run()


def remove_artifacts_thread_proc(frequency):
    scheduler = sched.scheduler()
    # Schedule first execution immediately.
    scheduler.enter(0, 0, remove_artifacts, (scheduler, frequency))
    scheduler.run()


def remove_artifacts_init():
    remove_artifacts_thread = threading.Thread(
        target=remove_artifacts_thread_proc,
        args=(datetime.timedelta(days=configuration.settings.artifacts_remove_frequency).total_seconds(),),
        daemon=True
    )
    remove_artifacts_thread.start()


def main(test_mode=False):
    # Setup log and ssh and other things present in all the environments
    setup_common_environment()

    app = create_app()

    if test_mode:
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        return app.test_client()

    if configuration.settings.artifacts_remove_enabled and configuration.settings.artifacts_remove_age > 0:
        remove_artifacts_init()

    # Start the API server
    app.run(host=configuration.settings.ip_address,
            port=configuration.settings.port,
            threaded=True,
            debug=configuration.settings.debug,
            use_reloader=False)


if __name__ == "__main__":

    # setup signal handler for a kill/sigterm request (background mode)
    signal.signal(signal.SIGTERM, signal_stop)

    print("Starting ansible-runner-service")
    configuration.init()

    main()
