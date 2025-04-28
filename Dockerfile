# TODO: find a better alternative than recycling the web shell image...
FROM keppel.eu-de-1.cloud.sap/ccloud/ccloud-shell:latest
LABEL MAINTAINER="Stefan Hipfel <stefan.hipfel@sap.com>"
LABEL source_repository="https://github.com/sapcc/seeder-ccloud"

ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

WORKDIR /operator
COPY seeder_ccloud/ ./seeder_ccloud/
COPY setup.py .

ARG CUSTOM_PYPI_URL
RUN [ $CUSTOM_PYPI_URL != "" ] || { echo -e "\n\nCUSTOM_PYPI_URL must be set!\n\n"; exit 1; } && \
    apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates && \
    update-ca-certificates && \
    pip3 install --no-cache-dir --only-binary :all: --no-compile --extra-index-url ${CUSTOM_PYPI_URL} kubernetes-entrypoint && \
    pip3 install --no-cache-dir . && \
    apt-get purge -y --auto-remove build-essential && \
    rm -rf /var/lib/apt/lists/* build/ /root/.bash_aliases

CMD ["seeder_ccloud"]
