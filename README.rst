Odoo abstract model generator from xsd schemas using xsdata
======================================

.. image:: https://codecov.io/gh/akretion/xsdata-odoo/branch/master/graph/badge.svg
    :target: https://codecov.io/gh/akretion/xsdata-odoo

.. image:: https://img.shields.io/pypi/pyversions/xsdata-odoo.svg
    :target: https://pypi.org/pypi/xsdata-odoo/

.. image:: https://img.shields.io/pypi/v/xsdata-odoo.svg
    :target: https://pypi.org/pypi/xsdata-odoo/

- [xsdata](https://xsdata.readthedocs.io) based replacement of https://github.com/akretion/generateds-odoo
- heavily inspired by https://github.com/akretion/xsdata-plantuml

Install
=======

.. code:: console

    $ # Install with cli support
    $ pip install xsdata[cli]
    $ pip install git+https://github.com/akretion/xsdata-odoo


Generate Models
===============

Odoo Models for the Microsoft Purchase Order demo schema:

.. code:: console

    $ # Generate Odoo models
    $ xsdata generate tests/fixtures/po/po.xsd --output=odoo
    Parsing schema po.xsd
    Compiling schema po.xsd
    Builder: 6 main and 1 inner classes
    Analyzer input: 6 main and 1 inner classes
    Analyzer output: 5 main and 1 inner classes
    Generating package: generated.po
    
    
Odoo Models for the Brazilian Electronic Invoices:

.. code:: console

    $ # Generate Odoo models
    $ export XSDATA_SCHEMA=nfe; export XSDATA_VERSION=40; export XSDATA_SKIP="^ICMS.ICMS\d+|^ICMS.ICMSSN\d+"
    $ # assuming you are in an akretion/nfelib clone or you downloaded the NFe schemas in nfelib/schemas/nfe/v4_0:
    $ xsdata generate nfelib/schemas/nfe/v4_0 --package nfelib.odoo.nfe.v4_0 --output=odoo
    Generating package: init
    Generating package: nfelib.odoo.nfe.v4_0.tipos_basico_v4_00
    Generating package: nfelib.odoo.nfe.v4_0.leiaute_cons_stat_serv_v4_00
    Generating package: nfelib.odoo.nfe.v4_0.leiaute_nfe_v4_00
    Generating package: nfelib.odoo.nfe.v4_0.leiaute_cons_sit_nfe_v4_00
    Generating package: nfelib.odoo.nfe.v4_0.ret_cons_reci_nfe_v4_00
    Generating package: nfelib.odoo.nfe.v4_0.cons_stat_serv_v4_00
    Generating package: nfelib.odoo.nfe.v4_0.proc_nfe_v4_00
    Generating package: nfelib.odoo.nfe.v4_0.leiaute_inut_nfe_v4_00
    Generating package: nfelib.odoo.nfe.v4_0.ret_inut_nfe_v4_00
    Generating package: nfelib.odoo.nfe.v4_0.proc_inut_nfe_v4_00
    Generating package: nfelib.odoo.nfe.v4_0.nfe_v4_00
    Generating package: nfelib.odoo.nfe.v4_0.cons_reci_nfe_v4_00
    Generating package: nfelib.odoo.nfe.v4_0.envi_nfe_v4_00
    Generating package: nfelib.odoo.nfe.v4_0.inut_nfe_v4_00
    Generating package: nfelib.odoo.nfe.v4_0.ret_envi_nfe_v4_00
    Generating package: nfelib.odoo.nfe.v4_0.cons_sit_nfe_v4_00
    Generating package: nfelib.odoo.nfe.v4_0.ret_cons_stat_serv_v4_00
    Generating package: nfelib.odoo.nfe.v4_0.ret_cons_sit_nfe_v4_00
