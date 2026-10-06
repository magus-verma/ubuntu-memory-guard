# Roadmap

These are proposed validation and engineering tasks, not promised delivery dates.

- Add controlled VM reclaim integration tests on supported kernels.
- Measure desktop latency and swap-in behavior with hot versus cold working sets.
- Validate additional distributions, x86_64 systems, and compressed swap setups.
- Evaluate a backoff policy when repeated reclaim makes little progress.
- Consider distribution packaging after compatibility evidence is broader.

Keep runtime dependencies small, preserve reversible installation, and expand
support claims only when backed by reproducible measurements.
