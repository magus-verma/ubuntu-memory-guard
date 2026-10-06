# Releasing

1. Run `make test` and `make lint`; review compatibility and validation claims.
2. Update `VERSION` and the changelog for a new version.
3. Push `main` and wait for all GitHub CI jobs to pass for that exact commit.
4. Create and push an annotated version tag.
5. Build a reproducible source archive from that tag and publish its SHA-256 checksum.

For v0.1.0:

```bash
mkdir -p dist
git archive --format=tar --prefix=ubuntu-memory-guard-0.1.0/ v0.1.0 \
  | gzip -n > dist/ubuntu-memory-guard-0.1.0.tar.gz
(cd dist && sha256sum ubuntu-memory-guard-0.1.0.tar.gz > SHA256SUMS)
```

Archives contain tracked source only. `gzip -n` omits variable timestamp/name
metadata. Checksums detect corruption; they are not a signing or provenance
guarantee. Compare assets with the tagged source before privileged installation.
