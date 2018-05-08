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
	RM := "rm" -rf
	FIND := "C:\Program Files\Git\usr\bin\find.exe"
else
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
	pyenv uninstall -f godzillops
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
	pylint godzillops tests

test:
	python setup.py test

coverage:
	coverage run --branch --source godzillops setup.py test
	coverage report -m
	coverage html
	$(BROWSER) htmlcov/index.html

docs:
	$(RM) godzillops.rst
	$(RM) docs/modules.rst
	sphinx-apidoc -o docs godzillops
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
	pyenv virtualenv 3.6.5 godzillops
	python setup.py install
	python -m nltk.downloader brown

install-dev: install
	pip install --upgrade -r requirements_dev.txt
