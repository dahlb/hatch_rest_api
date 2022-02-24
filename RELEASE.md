python3 -m build --sdist --wheel --outdir dist/ .
twine upload dist/*
