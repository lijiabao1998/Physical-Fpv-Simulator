# Public laboratory calibration: completed synthetic and HTTP reports

This reports-only draft publishes the completed local R5 findings. It does not integrate the simulator/model mainline, introduce a new fit, or rerun simulations or GUI checks.

- [Complete scientific report](public-lab-synthetic-report.md):364 fixed cases,224 calculable and140 invalid inputs retained;936,456 original trace rows;18 recorded checks PASS and independent review. The original measured acceptance remains6/8 with two cutoff failures and aggregate **FAIL**.
- [Complete HTTP diagnosis](public-lab-http-lifecycle-report.md):original ten checks pass under the declared localhost condition; historical Win10053 remains **UNRESOLVED**, with no production fix.
- [All364 case results](public-lab-synthetic-evidence/primary-01/results.json), [frozen91 inputs](public-lab-synthetic-evidence/scenarios.json), [numerical checks](public-lab-synthetic-evidence/numerical-verification.json), [independent review](public-lab-synthetic-evidence/independent-review.md), [plot](public-lab-synthetic-evidence/finite-synthetic-ranges.png), and [publication provenance/hashes](publication-manifest.json).

Initial charge, missing history and slow RC are synthetic assumptions. The5A117.9°C endpoint is unvalidated extrapolation, not an operating guarantee. No unseen measured validation, measured uncertainty bound, thrust or flight-endurance validation is established. Existing ORegan30/36 and Chen6/12 failures remain failures.

The source local commits are1bf952b (science) and83b90ee (HTTP); they are provenance IDs, not claims of published remote model commits. Original filenames/hashes are retained in the manifest. Public copies redact private paths and unrelated task names; altered text is not falsely described as byte-identical raw evidence. The28.6MB full trace and redundant bookkeeping files are omitted. Source/dependency/raw-data permissions do not grant a project-wide license; LG M50 dataset attribution remains in the scientific report.

## Publication checks

Before remote write: exact latest-main base, docs-only path allowlist, file sizes, private-path/credential scan,364input/result pairs and status counts, JSON validity, local-link resolution, and original/published SHA256 mapping. No scientific or GUI rerun is part of these checks. The unchanged README from main is preserved.

Historical calibration evidence: [all-case report](public-lab-synthetic-evidence/prior-calibration/result.json), [pre-fit freeze](public-lab-synthetic-evidence/prior-calibration/pre-fit-freeze.json), [optimizer record](public-lab-synthetic-evidence/prior-calibration/optimizer-log.json). These are existing earlier records, not new fitting or acceptance. Embedded original digests remain references to original bytes; public derivative digests are in the publication manifest.
