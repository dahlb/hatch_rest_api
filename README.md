# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/dahlb/hatch_rest_api/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                               |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|--------------------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| src/hatch\_rest\_api/\_\_init\_\_.py               |       15 |        0 |        0 |        0 |    100% |           |
| src/hatch\_rest\_api/aws\_http.py                  |       24 |       11 |        2 |        0 |     50% |21-24, 28, 34, 52-67 |
| src/hatch\_rest\_api/callbacks.py                  |       20 |       12 |        8 |        0 |     29% |16, 20-22, 26-28, 32-36 |
| src/hatch\_rest\_api/const.py                      |      143 |        0 |        0 |        0 |    100% |           |
| src/hatch\_rest\_api/contentful.py                 |       46 |       34 |        8 |        0 |     22% |23, 27, 51-104 |
| src/hatch\_rest\_api/errors.py                     |        4 |        0 |        0 |        0 |    100% |           |
| src/hatch\_rest\_api/hatch.py                      |      149 |       59 |       20 |        6 |     60% |45-46, 50-60, 81, 88, 106-\>108, 128-129, 133-138, 142-159, 163-168, 172-180, 184-192, 212-\>214, 289-\>315, 298-\>315, 300-307, 393-418 |
| src/hatch\_rest\_api/rest\_baby.py                 |      157 |      105 |       58 |        0 |     24% |55-102, 106, 136, 141, 146, 151, 156, 167-173, 177-178, 182-184, 195-197, 204-206, 215-217, 226-244, 268-290, 315-316, 334-335, 339-356, 383-412 |
| src/hatch\_rest\_api/rest\_iot.py                  |      164 |       94 |       60 |        1 |     33% |56-103, 107, 138, 143, 158, 163, 174-180, 184-185, 192-194, 198-199, 210-211, 220-222, 226-235, 257-279, 302-303, 332-\>exit, 376-405 |
| src/hatch\_rest\_api/rest\_mini.py                 |       38 |       19 |       12 |        0 |     38% |26, 40, 43-54, 59, 63, 75-85 |
| src/hatch\_rest\_api/rest\_plus.py                 |       64 |       36 |       26 |        0 |     31% |39-73, 78, 82, 102, 106, 116, 126, 140 |
| src/hatch\_rest\_api/restore\_iot.py               |      107 |       63 |       36 |        0 |     31% |50-84, 88, 112, 117, 122, 127, 132, 137, 141-142, 153-159, 163-164, 175-176, 185-187, 191-192, 196-213, 240-269 |
| src/hatch\_rest\_api/restore\_v4.py                |        2 |        0 |        0 |        0 |    100% |           |
| src/hatch\_rest\_api/restore\_v5.py                |      164 |      108 |       64 |        0 |     25% |54-103, 107, 139, 144, 149, 154, 159, 164, 169, 173-174, 185-191, 204-211, 222-228, 237-239, 248-270, 287-288, 292-309, 336-365, 384-394, 400-409 |
| src/hatch\_rest\_api/scheduled\_routine.py         |      234 |       40 |       96 |       26 |     78% |81, 123, 174, 202, 249, 251, 253, 268, 276, 290-291, 336, 340, 344, 375, 388, 390, 392, 469-470, 472, 482, 497-515, 533-534, 536, 549, 556, 561 |
| src/hatch\_rest\_api/shadow\_client\_subscriber.py |       73 |       22 |       18 |        2 |     60% |54-\>56, 56-\>58, 70, 88, 137-149, 152-161, 164-171 |
| src/hatch\_rest\_api/types.py                      |        3 |        0 |        0 |        0 |    100% |           |
| src/hatch\_rest\_api/util.py                       |       42 |       16 |       18 |        1 |     62% |33, 46, 56, 72-84 |
| src/hatch\_rest\_api/util\_bootstrap.py            |      186 |       46 |       52 |       17 |     73% |111-112, 115, 120-\>122, 167, 230-232, 237, 242, 247, 252, 259, 268, 280, 292, 304, 340-343, 359-362, 372-385, 396-401, 403-446 |
| src/hatch\_rest\_api/util\_http.py                 |       27 |        4 |        4 |        1 |     84% | 31, 44-46 |
| **TOTAL**                                          | **1662** |  **669** |  **482** |   **54** | **52%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/dahlb/hatch_rest_api/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/dahlb/hatch_rest_api/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/dahlb/hatch_rest_api/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/dahlb/hatch_rest_api/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Fdahlb%2Fhatch_rest_api%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/dahlb/hatch_rest_api/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.