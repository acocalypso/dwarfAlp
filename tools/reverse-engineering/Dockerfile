# syntax=docker/dockerfile:1.7
FROM ubuntu:24.04@sha256:33ceb71981b602c1a7443a53469e4dba065f7503eab3078a2d7a57a2ab987517

ARG DEBIAN_FRONTEND=noninteractive
ARG JADX_VERSION=1.5.6
ARG JADX_SHA256=545ea2be9c242511bc145755cf4bda2485ade42966e096f8b4d3da2a230e8974
ARG APKTOOL_VERSION=3.0.3
ARG APKTOOL_SHA256=dbf930b076c6b9be08d57c449cacefc3bdd6b71ebd59b3066fc0e1f5b14f9423
ARG GHIDRA_VERSION=12.1.3
ARG GHIDRA_BUILD_DATE=20260817
ARG GHIDRA_SHA256=93a5d11a9ad510622acaaf908c556a7b9b764d338e78a7567f3689bf5081fd54

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
        binutils \
        ca-certificates \
        curl \
        device-tree-compiler \
        file \
        jq \
        openjdk-21-jdk-headless \
        protobuf-compiler \
        python3 \
        ripgrep \
        sqlite3 \
        unzip \
        xz-utils \
        zip

RUN set -eux; \
    curl --fail --location --retry 5 \
      "https://github.com/skylot/jadx/releases/download/v${JADX_VERSION}/jadx-${JADX_VERSION}.zip" \
      --output /tmp/jadx.zip; \
    echo "${JADX_SHA256}  /tmp/jadx.zip" | sha256sum --check --strict; \
    unzip -q /tmp/jadx.zip -d /opt/jadx; \
    rm /tmp/jadx.zip; \
    curl --fail --location --retry 5 \
      "https://github.com/iBotPeaches/Apktool/releases/download/v${APKTOOL_VERSION}/apktool_${APKTOOL_VERSION}.jar" \
      --output /opt/apktool.jar; \
    echo "${APKTOOL_SHA256}  /opt/apktool.jar" | sha256sum --check --strict; \
    curl --fail --location --retry 5 \
      "https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_${GHIDRA_VERSION}_build/ghidra_${GHIDRA_VERSION}_PUBLIC_${GHIDRA_BUILD_DATE}.zip" \
      --output /tmp/ghidra.zip; \
    echo "${GHIDRA_SHA256}  /tmp/ghidra.zip" | sha256sum --check --strict; \
    unzip -q /tmp/ghidra.zip -d /opt; \
    mv "/opt/ghidra_${GHIDRA_VERSION}_PUBLIC" /opt/ghidra; \
    rm /tmp/ghidra.zip; \
    printf '#!/bin/sh\nexec java -jar /opt/apktool.jar "$@"\n' > /usr/local/bin/apktool; \
    chmod 0755 /usr/local/bin/apktool; \
    ln -s /opt/jadx/bin/jadx /usr/local/bin/jadx; \
    ln -s /opt/ghidra/support/analyzeHeadless /usr/local/bin/analyzeHeadless

RUN groupadd --gid 10001 analyst \
    && useradd --uid 10001 --gid analyst --create-home --shell /bin/bash analyst \
    && mkdir -p /workspace /output /opt/re-tools/ghidra_scripts \
    && chown -R analyst:analyst /workspace /output /home/analyst

COPY --chmod=0755 tools/reverse-engineering/run-analysis.sh /opt/re-tools/run-analysis.sh
COPY --chmod=0644 tools/reverse-engineering/ghidra_scripts/ExportDecompilation.java \
    /opt/re-tools/ghidra_scripts/ExportDecompilation.java
COPY --chmod=0644 tools/reverse-engineering/ghidra_scripts/ExportKeywordXrefs.java \
    /opt/re-tools/ghidra_scripts/ExportKeywordXrefs.java

ENV HOME=/home/analyst \
    JAVA_TOOL_OPTIONS=-Djava.awt.headless=true \
    PATH=/opt/jadx/bin:/opt/ghidra/support:${PATH}

USER analyst
WORKDIR /workspace
ENTRYPOINT ["/opt/re-tools/run-analysis.sh"]
CMD ["help"]
