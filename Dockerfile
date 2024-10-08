FROM keppel.eu-de-1.cloud.sap/ccloud/ccloud-shell:20240911114114
LABEL MAINTAINER="Stefan Hipfel <stefan.hipfel@sap.com>"
LABEL source_repository="https://github.com/sapcc/seeder-ccloud"

ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

RUN echo 'precedence ::ffff:0:0/96  100' >> /etc/gai.conf && \
    apt-get update && \
    apt-get dist-upgrade -y && \
    apt-get install -y --no-install-recommends ca-certificates curl && \
    update-ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* /root/.cache

WORKDIR /operator
COPY seeder_ccloud/ ./seeder_ccloud/
COPY setup.py .

ARG CUSTOM_PYPI_URL
RUN apt-get update && \
    ls && \
    apt-get dist-upgrade -y && \
    apt-get install -y --no-install-recommends build-essential pkg-config git openssl libssl-dev libyaml-dev libffi-dev python3 python3-pip python3-setuptools python3-dev && \
    pip3 install --upgrade wheel && \
    pip3 install --upgrade pip && \
    pip3 install --upgrade setuptools && \
    pip3 install --no-cache-dir --only-binary :all: --no-compile --extra-index-url ${CUSTOM_PYPI_URL} kubernetes-entrypoint && \
    pip3 install . && \
    apt-get purge -y --auto-remove build-essential git libssl-dev libffi-dev libyaml-dev && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* /root/.cache

CMD ["seeder_ccloud"]
