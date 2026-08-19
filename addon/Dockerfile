# Debian-Basis wie hofbuch/hofrechnung – gemeinsame Ebenen auf derselben
# Instanz. Bewusst ohne Vorgabe für BUILD_FROM: welches Image genommen wird,
# steht je Architektur in build.yaml und wird vom Supervisor übergeben.
ARG BUILD_FROM
FROM ${BUILD_FROM}

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# tzdata, damit Zeitstempel in Ortszeit stehen. Python + venv für den Bot.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
        tzdata \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/fuetterungsabruf

COPY requirements.txt ./
RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
 && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt
ENV PATH="/opt/venv/bin:${PATH}"

COPY app ./app
COPY run.sh /run.sh
RUN chmod a+x /run.sh

LABEL io.hass.name="fuetterungsabruf" \
      io.hass.type="addon"

CMD ["/run.sh"]
