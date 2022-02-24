# Contributing

Everybody is invited and welcome to contribute to this project.

The process is straight-forward.

 - Read [How to get faster PR reviews](https://github.com/kubernetes/community/blob/master/contributors/guide/pull-requests.md#best-practices-for-faster-reviews) by Kubernetes (but skip step 0 and 1)
 - Fork the [git repository](hhttps://github.com/dahlb/kia_hyundai_api).
   - Add a new method try to keep its signature as similar to other region/brands as possible.
   - Add example responses
     - modify a stub file
     - run ```python src/kia_hyundai_api/us_hyundai_stub.py```
     - add the logging from the console to the source code being sure to remove PII like lat/long and VIN numbers
 - Create a Pull Request against the [**master**](https://github.com/dahlb/kia_hyundai_api/master) branch.

## Issues (Features/Bugs)

If you want to suggest a new feature or found a problem using the API, please open a ticket in [Issues](https://github.com/dahlb/ha_kia_hyundai/issues).
