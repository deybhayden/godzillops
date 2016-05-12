.PHONY: clean-pyc clean-build docs clean
define BROWSER_PYSCRIPT
import os, webbrowser, sys
try:
	from urllib import pathname2url
except:
	from urllib.request import pathname2url

webbrowser.open("file://" + pathname2url(os.path.abspath(sys.argv[1])))
endef
export BROWSER_PYSCRIPT
BROWSER := python -c "$$BROWSER_PYSCRIPT"

help:
	@echo "clean - remove all build, test, coverage and Python artifacts"
	@echo "clean-build - remove build artifacts"
	@echo "clean-pyc - remove Python file artifacts"
	@echo "clean-test - remove test and coverage artifacts"
	@echo "lint - check style with flake8"
	@echo "test - run tests quickly with the default Python"
	@echo "coverage - check code coverage quickly with the default Python"
	@echo "docs - generate Sphinx HTML documentation, including API docs"
	@echo "release - package and upload a release"
	@echo "dist - package"
	@echo "install - install the package to the active Python's site-packages"

clean: clean-build clean-pyc clean-test

clean-build:
	rm -fr .venv
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/
	find . -name '*.egg-info' -exec rm -fr {} +
	find . -name '*.egg' -exec rm -fr {} +

clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +

clean-test:
	rm -f .coverage
	rm -fr htmlcov/

lint:
	. .venv/bin/activate && \
	flake8 --max-complexity=10 godzillops tests

test:
	. .venv/bin/activate && \
	python setup.py test

coverage:
	. .venv/bin/activate && \
	coverage run --branch --source godzillops setup.py test
	coverage report -m
	coverage html
	$(BROWSER) htmlcov/index.html

coverage-codeship:
	. .venv/bin/activate && \
	coverage run --branch --source godzillops setup.py test
	coverage report -m --fail-under 100

docs:
	. .venv/bin/activate && \
	rm -f docs/godzillops.rst
	rm -f docs/modules.rst
	sphinx-apidoc -o docs/ godzillops
	$(MAKE) -C docs clean
	$(MAKE) -C docs html
	$(BROWSER) docs/_build/html/index.html

servedocs: docs
	watchmedo shell-command -p '*.rst' -c '$(MAKE) -C docs html' -R -D .

release: clean
	python setup.py sdist upload
	python setup.py bdist_wheel upload

dist: clean
	python setup.py sdist
	python setup.py bdist_wheel
	ls -l dist

install: clean
	virtualenv --python /usr/local/bin/python3 .venv
	. .venv/bin/activate && \
	python setup.py install && \
	python -m nltk.downloader names brown

install-codeship: install
	. .venv/bin/activate && \
	pip install coverage

install-dev: install
	. .venv/bin/activate && \
	pip install --upgrade -r requirements_dev.txt
