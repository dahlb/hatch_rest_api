# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/dahlb/hatch_rest_api/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                               |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|--------------------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| src/hatch\_rest\_api/\_\_init\_\_.py               |       16 |        0 |        0 |        0 |    100% |           |
| src/hatch\_rest\_api/aws\_http.py                  |       25 |       12 |        2 |        0 |     48% |21-24, 28, 34, 52-68 |
| src/hatch\_rest\_api/callbacks.py                  |       20 |        4 |        8 |        1 |     75% | 21, 26-28 |
| src/hatch\_rest\_api/const.py                      |      155 |        0 |        0 |        0 |    100% |           |
| src/hatch\_rest\_api/contentful.py                 |       46 |       34 |        8 |        0 |     22% |23, 27, 51-104 |
| src/hatch\_rest\_api/errors.py                     |        5 |        0 |        0 |        0 |    100% |           |
| src/hatch\_rest\_api/hatch.py                      |      174 |       57 |       20 |        5 |     67% |48-49, 53-63, 90, 97, 115-\>117, 137-139, 143-149, 177-183, 187-195, 199-207, 304-\>330, 313-\>330, 315-322, 474-499 |
| src/hatch\_rest\_api/rest\_baby.py                 |      157 |      105 |       58 |        0 |     24% |55-102, 106, 136, 141, 146, 151, 156, 167-173, 177-178, 182-184, 195-197, 204-206, 215-217, 226-244, 268-290, 315-316, 334-335, 339-356, 383-412 |
| src/hatch\_rest\_api/rest\_iot.py                  |      164 |       84 |       60 |        2 |     38% |56-103, 107, 138, 143, 158, 163, 174-180, 184-185, 192-194, 220-222, 228-229, 263-285, 308-309, 338-\>exit, 382-411 |
| src/hatch\_rest\_api/rest\_mini.py                 |       38 |       19 |       12 |        0 |     38% |26, 40, 43-54, 59, 63, 75-85 |
| src/hatch\_rest\_api/rest\_plus.py                 |       64 |       35 |       26 |        0 |     32% |39-73, 82, 102, 106, 116, 126, 140 |
| src/hatch\_rest\_api/restore.py                    |      396 |       19 |      100 |       26 |     91% |135, 138-139, 152, 193-194, 293-\>299, 384, 391, 510, 515-\>514, 517, 522-\>521, 524, 543-\>546, 546-\>548, 564-\>566, 578, 583-\>582, 585, 597-\>600, 602-\>exit, 638-\>640, 640-\>642, 642-\>exit, 759, 772, 888-\>891, 892-\>894, 929-930, 961-962 |
| src/hatch\_rest\_api/restore\_iot.py               |      107 |       63 |       36 |        0 |     31% |50-84, 88, 112, 117, 122, 127, 132, 137, 141-142, 153-159, 163-164, 175-176, 185-187, 191-192, 196-213, 240-269 |
| src/hatch\_rest\_api/restore\_v4.py                |        2 |        0 |        0 |        0 |    100% |           |
| src/hatch\_rest\_api/restore\_v5.py                |      193 |      108 |       70 |        0 |     35% |58-107, 111, 143, 148, 153, 158, 163, 168, 173, 177-178, 189-195, 208-215, 226-232, 313-315, 324-346, 363-364, 368-385, 412-441, 460-470, 476-485 |
| src/hatch\_rest\_api/scheduled\_routine.py         |      234 |       40 |       96 |       26 |     78% |81, 123, 174, 202, 249, 251, 253, 268, 276, 290-291, 336, 340, 344, 375, 388, 390, 392, 479-480, 482, 492, 509-534, 552-553, 555, 568, 582, 587 |
| src/hatch\_rest\_api/shadow\_client\_subscriber.py |       73 |        4 |       18 |        8 |     87% |58-\>60, 60-\>62, 143-149, 150-\>exit, 158, 159-\>exit, 161, 163-\>exit |
| src/hatch\_rest\_api/types.py                      |        3 |        0 |        0 |        0 |    100% |           |
| src/hatch\_rest\_api/util.py                       |       48 |        3 |       22 |        2 |     93% |33, 75, 102 |
| src/hatch\_rest\_api/util\_bootstrap.py            |      221 |       46 |       62 |       17 |     77% |112-113, 116, 121-\>123, 168, 233-235, 240, 245, 250, 255, 262, 288, 300, 312, 324, 360-363, 379-382, 454-467, 478-483, 485-528 |
| src/hatch\_rest\_api/util\_http.py                 |       27 |        4 |        4 |        1 |     84% | 31, 43-45 |
| **TOTAL**                                          | **2168** |  **637** |  **602** |   **88** | **64%** |           |


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