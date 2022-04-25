FROM alpine:latest

# Install packages
RUN apk add --no-cache python3 python3-dev build-base libffi-dev openssh-client rsync && \
    python3 -m ensurepip && \
    python3 -m pip install -U pip setuptools wheel && \
    python3 -m pip install ansible && \

    mkdir -p /api /ansible && \

    # Enable ssh to use rsa keys
    echo "PubkeyAcceptedKeyTypes +ssh-rsa" >> /etc/ssh/ssh_config

# Install the python deps (this can take a while....)
COPY requirements.txt /api/requirements.txt
RUN python3 -m pip install -r /api/requirements.txt && \
    apk del --no-cache build-base libffi-dev

COPY runner_service/ /api/runner_service
COPY logging.yaml /api/logging.yaml
COPY docker-config.yaml /api/config.yaml
COPY ansible_runner_service.py /api/ansible_runner_service.py

WORKDIR /api
ENV PYTHONPATH="/api"

CMD python3 ansible_runner_service.py
