==========
godzillops
==========

.. image:: https://media.giphy.com/media/UsBIRDGtF4nMQ/giphy.gif

NLP Chat bot capable of performing business operations

Features
--------

* Can exchange basic greetings
* Returns random Godzilla gifs when you just say its name - very important
* Create google accounts upon request

Installing
----------

Should run on Windows/Mac/Linux. Makefile uses `pyenv-virtualenv`_ and creates a virtualenv of Python 3.4.2. If running on windows, make sure you have installed `Git for Windows`_ and have added all .exes to your `$PATH`.

::

    $> make install-dev
    $> make test

Credits
---------

This package was created with Cookiecutter_ and the `audreyr/cookiecutter-pypackage`_ project template.

.. _Cookiecutter: https://github.com/audreyr/cookiecutter
.. _`audreyr/cookiecutter-pypackage`: https://github.com/audreyr/cookiecutter-pypackage
.. _Git For Windows: https://git-for-windows.github.io/
.. _pyenv-virtualenv: https://github.com/pyenv/pyenv-virtualenv
