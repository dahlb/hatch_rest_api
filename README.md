# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/dahlb/hatch_rest_api/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                               |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|--------------------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| src/hatch\_rest\_api/\_\_init\_\_.py               |       16 |        0 |        0 |        0 |    100% |           |
| src/hatch\_rest\_api/aws\_http.py                  |       25 |        1 |        2 |        1 |     93% |        22 |
| src/hatch\_rest\_api/callbacks.py                  |       20 |        0 |        8 |        0 |    100% |           |
| src/hatch\_rest\_api/const.py                      |      155 |        0 |        0 |        0 |    100% |           |
| src/hatch\_rest\_api/contentful.py                 |       46 |        2 |        8 |        0 |     96% |     79-80 |
| src/hatch\_rest\_api/errors.py                     |        5 |        0 |        0 |        0 |    100% |           |
| src/hatch\_rest\_api/hatch.py                      |      174 |       57 |       20 |        5 |     67% |48-49, 53-63, 90, 97, 115-\>117, 137-139, 143-149, 177-183, 187-195, 199-207, 304-\>330, 313-\>330, 315-322, 474-499 |
| src/hatch\_rest\_api/rest\_baby.py                 |      155 |        1 |       58 |        3 |     98% |78-\>82, 337-\>351, 352 |
| src/hatch\_rest\_api/rest\_iot.py                  |      162 |        0 |       60 |        2 |     99% |79-\>83, 334-\>exit |
| src/hatch\_rest\_api/rest\_mini.py                 |       36 |        0 |       12 |        1 |     98% |   40-\>42 |
| src/hatch\_rest\_api/rest\_plus.py                 |       62 |        0 |       26 |        6 |     93% |52-\>54, 54-\>56, 56-\>58, 58-\>60, 60-\>62, 62-\>64 |
| src/hatch\_rest\_api/restore.py                    |      394 |       19 |      100 |       26 |     91% |135, 138-139, 152, 193-194, 293-\>299, 380, 387, 506, 511-\>510, 513, 518-\>517, 520, 539-\>542, 542-\>544, 560-\>562, 574, 579-\>578, 581, 593-\>596, 598-\>exit, 634-\>636, 636-\>638, 638-\>exit, 755, 768, 884-\>887, 888-\>890, 925-926, 957-958 |
| src/hatch\_rest\_api/restore\_iot.py               |      105 |        1 |       36 |        1 |     99% |       209 |
| src/hatch\_rest\_api/restore\_v4.py                |        2 |        0 |        0 |        0 |    100% |           |
| src/hatch\_rest\_api/restore\_v5.py                |      191 |        1 |       70 |        1 |     99% |       381 |
| src/hatch\_rest\_api/scheduled\_routine.py         |      234 |       40 |       96 |       26 |     78% |81, 123, 174, 202, 249, 251, 253, 268, 276, 290-291, 336, 340, 344, 375, 388, 390, 392, 479-480, 482, 492, 509-534, 552-553, 555, 568, 582, 587 |
| src/hatch\_rest\_api/shadow\_client\_subscriber.py |       81 |        5 |       18 |        8 |     87% |44, 80-\>82, 82-\>84, 165-171, 172-\>exit, 180, 181-\>exit, 183, 185-\>exit |
| src/hatch\_rest\_api/types.py                      |        3 |        0 |        0 |        0 |    100% |           |
| src/hatch\_rest\_api/util.py                       |       48 |        1 |       22 |        1 |     97% |        33 |
| src/hatch\_rest\_api/util\_bootstrap.py            |      221 |       46 |       62 |       17 |     77% |112-113, 116, 121-\>123, 168, 233-235, 240, 245, 250, 255, 262, 288, 300, 312, 324, 360-363, 379-382, 454-467, 478-483, 485-528 |
| src/hatch\_rest\_api/util\_http.py                 |       27 |        3 |        4 |        0 |     90% |     43-45 |
| **TOTAL**                                          | **2162** |  **177** |  **602** |   **98** | **90%** |           |


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