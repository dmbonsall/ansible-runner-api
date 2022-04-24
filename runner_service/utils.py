import os
import shlex
import shutil
import socket
import sys
import getpass

from subprocess import Popen, PIPE
from threading import Timer


from runner_service import configuration

import logging
logger = logging.getLogger(__name__)


class RunnerServiceError(Exception):
    pass


def create_directory(dir_path):
    """ Create directory if it doesn't exist """
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)


def fread(file_path):
    """ return the contents of the given file """
    with open(file_path, 'r') as file_fd:
        return file_fd.read().strip()


def rm_r(path):
    if not os.path.exists(path):
        return
    if os.path.isfile(path) or os.path.islink(path):
        os.unlink(path)
    else:
        shutil.rmtree(path)


if sys.version_info[0] == 2:
    class ConnectionError(OSError):
        pass

    class ConnectionRefusedError(ConnectionError):
        pass


class HostNotFound(Exception):
    pass


class SSHNotAccessible(Exception):
    pass


class SSHTimeout(Exception):
    pass


class SSHIdentityFailure(Exception):
    pass


class SSHAuthFailure(Exception):
    pass


class SSHUnknownError(Exception):
    pass


class SSHClient(object):
    def __init__(self, user, host, identity, timeout=1, port=22):
        self.user = user
        self.port = port
        self.host = host
        self.timeout = timeout
        self.identity_file = identity

    def connect(self):

        def timeout_handler():
            proc.kill()
            raise SSHTimeout

        socket.setdefaulttimeout(self.timeout)
        try:
            family, *_, sockaddr = socket.getaddrinfo(self.host, self.port, 0, socket.SOCK_STREAM, socket.SOL_TCP)[0]
        except socket.gaierror:
            raise HostNotFound

        with socket.socket(family, socket.SOCK_STREAM, socket.SOL_TCP) as s:
            try:
                s.connect(sockaddr)
            except ConnectionRefusedError:
                raise SSHNotAccessible
            except socket.timeout:
                raise SSHTimeout
            else:
                s.shutdown(socket.SHUT_RDWR)

        # Now try and use the identity file to passwordless ssh
        cmd = ('ssh -o "StrictHostKeyChecking=no" '
               '-o "IdentitiesOnly=yes" '
               ' -o "PasswordAuthentication=no" '
               ' -i {} '
               '{}@{} python --version'.format(self.identity_file, self.user, self.host))

        proc = Popen(shlex.split(cmd), stdout=PIPE, stderr=PIPE)
        timer = Timer(self.timeout, timeout_handler)
        try:
            timer.start()
            stdout, stderr = proc.communicate()
        except Exception as e:
            raise SSHUnknownError(e)
        else:
            if 'permission denied' in stderr.decode().lower():
                raise SSHAuthFailure(stderr)
        finally:
            timer.cancel()


def ssh_connect_ok(host, user=None, port=None):

    if not user:
        if configuration.settings.target_user:
            user = configuration.settings.target_user
        else:
            user = getpass.getuser()

    priv_key = os.path.join(configuration.settings.ssh_private_key)

    if not os.path.exists(priv_key):
        return False, "FAILED:SSH key(s) missing from ansible-runner-service"

    target = SSHClient(
        user=user,
        host=host,
        identity=priv_key,
        timeout=configuration.settings.ssh_timeout,
        port=22 if port is None else port,
    )

    try:
        target.connect()
    except HostNotFound:
        return False, "NOCONN:SSH error - '{}' not found; check DNS or " \
                "/etc/hosts".format(host)
    except SSHNotAccessible:
        return False, "NOCONN:SSH target '{}' not contactable; host offline" \
                      ", port 22 blocked, sshd running?".format(host)
    except SSHTimeout:
        return False, "TIMEOUT:SSH timeout waiting for response from " \
                      "'{}'".format(host)
    except SSHAuthFailure:
        return False, "NOAUTH:SSH auth error - passwordless ssh not " \
            "configured for '{}'".format(host)
    else:
        return True, "OK:SSH connection check to {} successful".format(host)
