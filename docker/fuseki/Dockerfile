# Apache Jena Fuseki, built from the Apache distribution rather than a community
# tag. There is no official apache/jena-fuseki image; the widely used one is
# third-party and unversioned. See docs/decisions/0002-fuseki-from-distribution.md
FROM eclipse-temurin:21-jre-noble

ARG FUSEKI_VERSION=5.3.0
ARG FUSEKI_SHA512=5204eefefb921ec029346139f5cb768fe298c816c8642ab590c9bdcee4f24cfacfb15c4266f7acf020d0d5232eea909e4af876f1d5162231ea4b8f8fe0feb3cf

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL -o /tmp/fuseki.tar.gz \
      "https://archive.apache.org/dist/jena/binaries/apache-jena-fuseki-${FUSEKI_VERSION}.tar.gz" \
 && echo "${FUSEKI_SHA512}  /tmp/fuseki.tar.gz" | sha512sum -c - \
 && mkdir -p /opt/fuseki \
 && tar -xzf /tmp/fuseki.tar.gz -C /opt/fuseki --strip-components=1 \
 && rm /tmp/fuseki.tar.gz

RUN mkdir -p /fuseki/databases && useradd -r -u 10001 fuseki && chown -R fuseki /fuseki
USER fuseki
WORKDIR /fuseki
EXPOSE 3030

HEALTHCHECK --interval=5s --timeout=3s --retries=30 --start-period=10s \
  CMD curl -fsS http://localhost:3030/$/ping || exit 1

# --update so the loader can write; --tdb2 for a persistent quad store
CMD ["sh", "-c", "exec java ${JAVA_OPTIONS:--Xmx2g} -jar /opt/fuseki/fuseki-server.jar --tdb2 --loc=/fuseki/databases/tkg --update /tkg"]
