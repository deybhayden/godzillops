#!/usr/bin/env python
# -*- coding: utf-8 -*-

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

with open('README.rst') as readme_file:
    readme = readme_file.read()

with open('HISTORY.rst') as history_file:
    history = history_file.read()

requirements = ["nltk==3.2.1", "python-dateutil==2.5.2", "google-api-python-client==1.5"]

test_requirements = [
    # TODO: put package test requirements here
]

setup(
    name='godzillops',
    version='0.1.0',
    description="NLP Chat bot capable of performing business operations",
    long_description=readme + '\n\n' + history,
    author="Ben Hayden",
    author_email='ben@statmuse.com',
    # url='https://github.com/statmuse/godzillops',
    packages=[
        'godzillops',
    ],
    package_dir={'godzillops': 'godzillops'},
    package_data={'godzillops': ['tagger.pickle']},
    include_package_data=True,
    install_requires=requirements,
    #license="ISCL",
    zip_safe=False,
    keywords='godzillops',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        #'License :: OSI Approved :: ISC License (ISCL)',
        'Natural Language :: English',
        "Programming Language :: Python :: 2",
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],
    test_suite='tests',
    tests_require=test_requirements)
