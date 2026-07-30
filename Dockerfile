FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# APT automatically resolves packages for the image's native architecture.
# Do not add a foreign architecture here: it can select an incompatible driver.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        chromium \
        chromium-driver \
        fluxbox \
        novnc \
        procps \
        websockify \
        x11vnc \
        xvfb \
    && rm -rf \
        /var/lib/apt/lists/* \
        /var/cache/apt/* \
        /tmp/* \
        /usr/share/doc/* \
        /usr/share/info/* \
        /usr/share/man/* \
        /usr/share/locale/*

# The Debian package is architecture-specific, so ARM64 images receive an ARM64
# driver and AMD64 images receive an AMD64 driver. Clear any cached UC driver
# before linking it to the verified system driver.
RUN set -eux; \
    container_arch="$(dpkg --print-architecture)"; \
    driver_arch="$(dpkg-query -W -f='${Architecture}' chromium-driver)"; \
    test "$container_arch" = "$driver_arch"; \
    test -x /usr/bin/chromedriver; \
    echo "==> 容器架构: ${container_arch}"; \
    chromium --version; \
    chromedriver --version; \
    rm -rf /root/.local/share/undetected_chromedriver; \
    mkdir -p /root/.local/share/undetected_chromedriver; \
    ln -s /usr/bin/chromedriver /root/.local/share/undetected_chromedriver/undetected_chromedriver

RUN pip install --no-cache-dir --no-compile \
        selenium \
        undetected-chromedriver \
        cryptography \
        curl_cffi

WORKDIR /app
COPY . /app

RUN chmod +x /app/scripts/start_linux_vnc.sh

EXPOSE 3030 5901 6080

CMD ["/app/scripts/start_linux_vnc.sh"]
