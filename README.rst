Odoo abstract model generator from xsd schemas using xsdata
======================================

.. image:: https://codecov.io/gh/akretion/xsdata-odoo/branch/master/graph/badge.svg
    :target: https://codecov.io/gh/akretion/xsdata-odoo

.. image:: https://img.shields.io/pypi/pyversions/xsdata-odoo.svg
    :target: https://pypi.org/pypi/xsdata-odoo/

.. image:: https://img.shields.io/pypi/v/xsdata-odoo.svg
    :target: https://pypi.org/pypi/xsdata-odoo/


!!WORK IN PROGRESS!!

- [xsdata](https://xsdata.readthedocs.io) based replacement of https://github.com/akretion/generateds-odoo
- heavily inspired by https://github.com/akretion/xsdata-plantuml

Install
=======

.. code:: console

    $ # Install with cli support
    $ pip install xsdata[cli]
    $ pip install xsdata-odoo


Generate Models
===============

.. code:: console

    $ # Generate Odoo models
    $ xsdata generate tests/fixtures/po/po.xsd --output=odoo
    Parsing schema po.xsd
    Compiling schema po.xsd
    Builder: 6 main and 1 inner classes
    Analyzer input: 6 main and 1 inner classes
    Analyzer output: 5 main and 1 inner classes
    Generating package: generated.po
    Generating package: generated.po
