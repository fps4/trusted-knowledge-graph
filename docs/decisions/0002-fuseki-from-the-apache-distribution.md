# 2. The store is built from the Apache distribution, not a community tag

Status: accepted · 2026-09-24

## Context

There is no official `apache/jena-fuseki` image. The widely used one is
third-party and its tags do not track Jena releases; the version this lab wanted
did not exist on it at all.

"Who maintains this in 2030" is the question an enterprise IT function actually
asks, and "the Apache Software Foundation" is only a real answer if the artefact
in the image came from the Foundation.

## Decision

A three-instruction Dockerfile on `eclipse-temurin:21-jre-noble` that downloads
the pinned Fuseki distribution from `archive.apache.org` and verifies its
published SHA-512 before unpacking it.

## Consequences

- The version is explicit, and a supply-chain question has a concrete answer.
- `archive.apache.org` rather than a mirror, because mirrors drop old releases and
  a build that stops reproducing in six months is not reproducible.
- The TDB2 location is created at container start, not at image build: the data
  directory is a volume, and an empty volume wins over anything the image put
  there. Fuseki exits rather than creating it, which is the correct behaviour and
  cost one debugging cycle to learn.
