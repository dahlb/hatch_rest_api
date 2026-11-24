# Contributing

Everybody is invited and welcome to contribute to this project.

The process is straight-forward.

 - Read [How to get faster PR reviews](https://github.com/kubernetes/community/blob/master/contributors/guide/pull-requests.md#best-practices-for-faster-reviews) by Kubernetes (but skip step 0 and 1)
 - Fork the [git repository](https://github.com/dahlb/hatch_rest_api).
   - Add a new method try to keep its signature as similar to other device types as possible.
   - Add or update deterministic pytest coverage and fixture data.
   - Run `scripts/live_smoke_test` against a live Hatch account when practical.
   - Update `src/hatch_rest_api/live_smoke_test.py` only when the default smoke-test flow should cover a new reusable live API path.
   - Keep one-off local probe edits out of the final PR, and turn useful live output into stored fixtures or pytest coverage, being sure to remove PII like MAC addresses and serial numbers.
 - Create a Pull Request against the [**main**](https://github.com/dahlb/hatch_rest_api/tree/main) branch.

## Issues (Features/Bugs)

If you want to suggest a new feature or found a problem using the API, please open a ticket in [Issues](https://github.com/dahlb/ha_hatch/issues).
