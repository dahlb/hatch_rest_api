old way
python setup.py install
twine upload dist/*


new way
python3 -m pip install --upgrade build
python3 -m build
python3 -m twine upload dist/*
