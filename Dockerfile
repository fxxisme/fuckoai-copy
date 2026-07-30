FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 检测容器架构
RUN ARCH=$(uname -m); \
    echo "==> 容器架构: ${ARCH}"; \
    if [ "$ARCH" = "x86_64" ]; then \
        echo "==> x86_64 — 可使用默认下载"; \
    elif [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then \
        echo "==> ARM64 — 开始添加 arm64 多层源，某些包可能不够新"; \
        dpkg --add-architecture arm64; \
    fi

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

# 将系统 chromedriver 软链到 undetected_chromedriver 期望的路径，避免自动下载
RUN ARCH=$(uname -m); \
    if [ -f /usr/bin/chromedriver ]; then \
        echo "==> 检测到系统 chromedriver，跳过自动下载"; \
        mkdir -p /root/.local/share/undetected_chromedriver && \
        ln -sf /usr/bin/chromedriver /root/.local/share/undetected_chromedriver/undetected_chromedriver; \
    else \
        echo "==> ⚠️ 系统 chromedriver 未找到，架构=${ARCH}，自带 undetected_chromedriver 自动下载"; \
    fi

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
