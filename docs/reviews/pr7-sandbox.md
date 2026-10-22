# PR #7: bounded sandbox execution

Student output is limited while pipes are read (256 KiB total), not after allocating it. Overflow, wall time and CPU limits fail safely; the exact container is removed in `finally`. The host captures at most 8 MiB of JSON transport, independently of student limits.

The output directory is now an 8 MiB container tmpfs, with no writable host output mount. At most 16 requested artifacts and 1 MiB aggregate artifact bytes may cross the boundary. Descriptor-relative, no-follow opens reject traversal, absolute paths, symlinks, hard links and nonregular files, including path replacement races. Reads remain bounded if files grow. Windows host fallback does not attempt an unsafe check-then-open implementation.

Greg's host-side grader and wrapper staging remain intact. The container receives no reference solutions. Structured results are bounded and validated before grading. The opt-in legacy runner now bounds pipes too, but is still insecure and unsuitable for untrusted submissions.

Unrelated CORS, classifier, logging, seed and global fixture changes were removed. CI builds a disposable Docker image and executes real container output, artifact, wall/CPU, confinement and cleanup tests. Validation results are recorded after execution; a test count without real Docker is not acceptance evidence.
