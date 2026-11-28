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
| src/hatch\_rest\_api/rest\_baby.py                 |      155 |       99 |       58 |        0 |     26% |55-102, 163-169, 173-174, 178-180, 191-193, 200-202, 211-213, 222-240, 264-286, 311-312, 330-331, 335-352, 379-408 |
| src/hatch\_rest\_api/rest\_iot.py                  |      162 |       79 |       60 |        2 |     40% |56-103, 170-176, 180-181, 188-190, 216-218, 224-225, 259-281, 304-305, 334-\>exit, 378-407 |
| src/hatch\_rest\_api/rest\_mini.py                 |       36 |       16 |       12 |        0 |     42% |39-50, 59, 71-81 |
| src/hatch\_rest\_api/rest\_plus.py                 |       62 |       33 |       26 |        0 |     33% |39-73, 102, 112, 122, 136 |
| src/hatch\_rest\_api/restore.py                    |      394 |       19 |      100 |       26 |     91% |135, 138-139, 152, 193-194, 293-\>299, 380, 387, 506, 511-\>510, 513, 518-\>517, 520, 539-\>542, 542-\>544, 560-\>562, 574, 579-\>578, 581, 593-\>596, 598-\>exit, 634-\>636, 636-\>638, 638-\>exit, 755, 768, 884-\>887, 888-\>890, 925-926, 957-958 |
| src/hatch\_rest\_api/restore\_iot.py               |      105 |       56 |       36 |        0 |     35% |50-84, 137-138, 149-155, 159-160, 171-172, 181-183, 187-188, 192-209, 236-265 |
| src/hatch\_rest\_api/restore\_v4.py                |        2 |        0 |        0 |        0 |    100% |           |
| src/hatch\_rest\_api/restore\_v5.py                |      191 |      101 |       70 |        0 |     37% |58-107, 169, 173-174, 185-191, 204-211, 222-228, 309-311, 320-342, 359-360, 364-381, 408-437, 456-466, 472-481 |
| src/hatch\_rest\_api/scheduled\_routine.py         |      234 |       40 |       96 |       26 |     78% |81, 123, 174, 202, 249, 251, 253, 268, 276, 290-291, 336, 340, 344, 375, 388, 390, 392, 479-480, 482, 492, 509-534, 552-553, 555, 568, 582, 587 |
| src/hatch\_rest\_api/shadow\_client\_subscriber.py |       81 |        5 |       18 |        8 |     87% |44, 80-\>82, 82-\>84, 165-171, 172-\>exit, 180, 181-\>exit, 183, 185-\>exit |
| src/hatch\_rest\_api/types.py                      |        3 |        0 |        0 |        0 |    100% |           |
| src/hatch\_rest\_api/util.py                       |       48 |        3 |       22 |        2 |     93% |33, 75, 102 |
| src/hatch\_rest\_api/util\_bootstrap.py            |      221 |       46 |       62 |       17 |     77% |112-113, 116, 121-\>123, 168, 233-235, 240, 245, 250, 255, 262, 288, 300, 312, 324, 360-363, 379-382, 454-467, 478-483, 485-528 |
| src/hatch\_rest\_api/util\_http.py                 |       27 |        4 |        4 |        1 |     84% | 31, 43-45 |
| **TOTAL**                                          | **2162** |  **608** |  **602** |   **88** | **65%** |           |


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