from xsdata.codegen.writer import CodeWriter

from xsdata_odoo.generator import OdooGenerator

CodeWriter.register_generator("odoo", OdooGenerator)
