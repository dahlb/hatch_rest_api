# Releasing

Releases are fully automated by `.github/workflows/release.yml` on every push to `main`.

1. [semantic-release](https://semantic-release.gitbook.io/) (configured in `.releaserc.json`)
   reads the Conventional Commit messages since the last tag to decide whether a release is
   needed and what the next version is (`fix:` → patch, `feat:` → minor, `!`/`BREAKING CHANGE` → major).
2. The workflow writes the new version into `VERSION` in `src/hatch_rest_api/const.py`.
3. The package is built and checked with `hynek/build-and-inspect-python-package` and
   published to PyPI.
4. The version bump is committed (`[skip ci]`), tagged, pushed, and a GitHub release is created
   with generated notes.

Do not edit `VERSION` by hand. Releases never run from forks.

To build locally for inspection only:

```bash
uv build --out-dir /tmp/hatch_rest_api_dist
```
