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

ifeq ($(OS),Windows_NT)
	CREATE_ENV := virtualenv env
	RM := "rm" -rf
	FIND := "C:\Program Files\Git\usr\bin\find.exe"
	ENV := env\Scripts\\
else
	CREATE_ENV := virtualenv --python python3 env
	ENV := env/bin/
	RM := rm -rf
	FIND := find
endif

.PHONY: clean-pyc clean-build docs clean

help:
	@echo "clean - remove all build, test, coverage and Python artifacts"
	@echo "clean-build - remove build artifacts"
	@echo "clean-pyc - remove Python file artifacts"
	@echo "clean-test - remove test and coverage artifacts"
	@echo "lint - check style with pylint"
	@echo "test - run tests quickly with the default Python"
	@echo "coverage - check code coverage quickly with the default Python"
	@echo "docs - generate Sphinx HTML documentation, including API docs"
	@echo "release - package and upload a release"
	@echo "dist - package"
	@echo "install - install the package to the active Python's site-packages"
	@echo "install-dev - install the package to the active Python's site-packages plus debug tools for local development"

clean: clean-build clean-pyc clean-test

clean-build:
	$(RM) env
	$(RM) build
	$(RM) dist
	$(RM) .eggs
	$(FIND) . -name '*.egg-info' -exec rm -fr {} +
	$(FIND) . -name '*.egg' -exec rm -fr {} +

clean-pyc:
	$(FIND) . -name '*.pyc' -exec rm -f {} +
	$(FIND) . -name '*.pyo' -exec rm -f {} +
	$(FIND) . -name '*~' -exec rm -f {} +
	$(FIND) . -name '__pycache__' -exec rm -fr {} +

clean-test:
	$(RM) .coverage
	$(RM) htmlcov

lint:
	$(ENV)pylint godzillops tests

test:
	$(ENV)python setup.py test

coverage:
	$(ENV)coverage run --branch --source godzillops setup.py test
	$(ENV)coverage report -m
	$(ENV)coverage html
	$(BROWSER) htmlcov/index.html

docs:
	$(RM) godzillops.rst
	$(RM) docs/modules.rst
	$(ENV)sphinx-apidoc -o docs godzillops
	$(MAKE) -C docs clean
	$(MAKE) -C docs html
	$(BROWSER) docs/_build/html/index.html

servedocs: docs
	watchmedo shell-command -p '*.rst' -c '$(MAKE) -C docs html' -R -D .

release: clean
	$(ENV)python setup.py sdist upload
	$(ENV)python setup.py bdist_wheel upload

dist: clean
	$(ENV)python setup.py sdist
	$(ENV)python setup.py bdist_wheel
	ls -l dist

install: clean
	$(CREATE_ENV)
	$(ENV)python setup.py install
	$(ENV)python -m nltk.downloader brown

install-dev: install
	$(ENV)pip install --upgrade -r requirements_dev.txt
