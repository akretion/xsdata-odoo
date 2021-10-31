import os
import re
import textwrap
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Iterator
from typing import List
from typing import Optional

from jinja2 import Environment
from jinja2 import FileSystemLoader
from .wrap_text import wrap_text
from xsdata.codegen.models import Attr
from xsdata.codegen.models import AttrType
from xsdata.codegen.models import Class
from xsdata.codegen.resolver import DependenciesResolver
from xsdata.formats.dataclass.filters import Filters
from xsdata.formats.mixins import AbstractGenerator
from xsdata.formats.mixins import GeneratorResult
from xsdata.models.config import GeneratorConfig
from xsdata.utils import collections
from xsdata.utils import text


INTEGER_TYPES = ("integer", "positiveInteger")
FLOAT_TYPES = (float,)
DECIMAL_TYPES = ("decimal",)
CHAR_TYPES = ("string", "NMTOKEN")
DATE_TYPES = ("date",)


# TODO collect the m2o of the o2m
# TODO collect xsd_type using lxml
# TODO use the simple type to convert to fields.Monetary
# TODO extract float digits when possible
# TODO extract field string attrs
# TODO extract enums and fields docstring using lxml

class OdooGenerator(AbstractGenerator):
    """Odoo generator."""

    @classmethod
    def init_filters(cls, config: GeneratorConfig) -> Filters:
        return Filters(config)

    def __init__(self, config: GeneratorConfig):
        super().__init__(config)
        tpl_dir = Path(__file__).parent.joinpath("templates")
        self.env = Environment(loader=FileSystemLoader(str(tpl_dir)), autoescape=False)
        self.filters = self.init_filters(config)
        self.filters.register(self.env)
        self.env.filters.update(
            {
                "class_name": self.class_name,
                "registry_name": self.registry_name,
                "clean_docstring": self.clean_docstring,
                "binding_type": self.binding_type,
                "field_definition": self.field_definition,
                "field_name": self.field_name,
            }
        )
        self.class_case: Callable = config.conventions.class_name.case
        self.class_safe_prefix: str = config.conventions.class_name.safe_prefix

    def render(self, classes: List[Class]) -> Iterator[GeneratorResult]:
        """Return a iterator of the generated results."""
        packages = {obj.qname: obj.target_module for obj in classes}
        resolver = DependenciesResolver(packages=packages)

        for module, cluster in self.group_by_module(classes).items():
            yield GeneratorResult(
                path=module.with_suffix(".py"),
                title=cluster[0].target_module,
                source=self.render_module(resolver, cluster),
            )

    def render_module(
        self, resolver: DependenciesResolver, classes: List[Class]
    ) -> str:
        """Render the source code for the target module of the given class
        list."""
        resolver.process(classes)
        output = self.render_classes(resolver.sorted_classes())
        output = self.env.get_template("module.jinja2").render(output=output)
        return f"{output}\n"

    def render_classes(self, classes: List[Class]) -> str:
        """Render the source code of the classes."""
        load = self.env.get_template
        classes = sorted(classes, key=lambda x: (not x.is_enumeration, x.name))
        # TODO filter signature classes like generateds_odoo
        # TODO collect enum docstrings and labels by reading class fields
        # where they are used.

        def render_class(obj: Class) -> str:
            """Render class or enumeration."""
            template = "enum.jinja2" if obj.is_enumeration else "class.jinja2"
            return load(template).render(obj=obj).strip()

        output = "\n\n".join(map(render_class, classes))
        return f"\n{output}\n"

    # jinja2 filters:

    def class_name(self, name: str, replace_type: bool = True) -> str:
        """Convert the given string to a class name according to the selected
        conventions or use an existing alias."""
        # print(name, self.class_safe_prefix, self.class_case)
        class_name = self.filters.safe_name(name, self.class_safe_prefix, self.class_case)
        if replace_type:
            return class_name.rpartition("Type")[0] or class_name
        else:
            return class_name

    def registry_name(self, name: str) -> str:
        schema = os.environ.get("SCHEMA", "spec")
        version = os.environ.get("VERSION", "10")
        name = self.class_name(name)
        return f"{schema}.{version}.{name.lower()}"

    def registry_comodel(self, type_names: List[str]):
        # NOTE: we take only the last part of inner Types with .split(".")[-1]
        # but if that were to create Type duplicates we could change that.
        return self.registry_name(type_names[-1].split(".")[-1])

    @classmethod
    def clean_docstring(cls, string: Optional[str], escape: bool = True) -> str:
        """
        Prepare string for docstring generation.

        - Strip whitespace from each line
        - Replace triple double quotes with single quotes
        - Escape backslashes
        :param string: input value
        :param escape: skip backslashes escape, if string is going to
            pass through formatting.
        """
        if not string:
            return ""

        # taken from https://github.com/akretion/generateds-odoo
        return "\n    {}".format(wrap_text(string, 4, 79))

        # def _clean(txt: str) -> str:
        #     if escape:
        #         txt = txt.replace("\\", "\\\\")

        #     return txt.replace('"""', "'''").strip()

        # return "\n".join(_clean(line) for line in string.splitlines() if line.strip())

    def binding_type(
        self,
        obj: Class,
        parents: List[str],
    ) -> str:
        """Return the name of the xsdata class for a given Odoo model"""
        return ".".join([self.class_name(p, False) for p in parents])

    def field_name(self, name: str) -> str:
        """
        field_name with schema and version prefix.

        We could have used a 'safe_name' like xsdata does for the Python
        bindings. But having this prefix it's already safe. It's also
        backward compatible with the models we generated with
        GenerateDS. And finally it's good to use some digits of the
        schema version in the field prefix, so minor schema updates are
        mapped to the same Odoo fields and --update should take care of
        it while major schema updates get different fields and possibly
        different classes/tables.
        """
        schema = os.environ.get("SCHEMA", "spec")
        version = os.environ.get("VERSION", "10")
        field_prefix = f"{schema}{version}_"
        if name.startswith("@"):
            name = name[1:100]
        return f"{field_prefix}{name}"

    def field_definition(
        self,
        attr: Attr,
        parents: List[str],
    ) -> str:
        """Return the Odoo field definition."""


        # 1st some checks inspired from Filters.field_type:
        type_names = collections.unique_sequence(
            self.filters.field_type_name(x, parents) for x in attr.types
        )

        if len(type_names) > 1:
            raise TypeError("Union of type not implemented yet!")

        if attr.is_tokens:
            raise TypeError("is_tokens not implemented yet!")

        if attr.is_dict:
            raise TypeError("Dict case not implemented yet!")

        # if attr.is_nillable or (
        #     attr.default is None and (attr.is_optional or not self.format.kw_only)
        # ):
        #     return f"Optional[{result}]"


        default_value = self.filters.field_default_value(attr, {})
        metadata = self.filters.field_metadata(attr, {}, parents)
        kwargs = {}
        # xsd_type = TODO

        if metadata.get("required"):
            # we choose not to put required=True to avoid
            # messing with existing Odoo modules.
            kwargs["xsd_required"] = True

        if attr.help:
            kwargs["help"] = attr.help

        if attr.is_list:
            kwargs = {"comodel": self.registry_comodel(type_names)}
            return f"fields.One2many({self.filters.format_arguments(kwargs, 4)})"
        elif attr.types[0].datatype:
            python_type = attr.types[0].datatype.code
            #print("----", attr.name, type(attr.types[0].datatype.code), type(attr.types[0].datatype.type))
            if python_type in INTEGER_TYPES:
                return f"fields.Integer()"
            if python_type in FLOAT_TYPES:
                return f"fields.Float()"
            elif python_type in DECIMAL_TYPES:
                return f"fields.Monetary()"
            elif python_type in CHAR_TYPES:
                # return f"fields.Char()"
                return f"fields.Char({self.filters.format_arguments(kwargs, 4)})"
            elif python_type in DATE_TYPES:
                return f"fields.Date()"
            else:
                return f"fields.{python_type}()"
        else: # Many2one
            print("--", attr.name, type_names, self.registry_comodel(type_names))
            kwargs = {"comodel": self.registry_comodel(type_names)}
            # TODO it can be a fields.Selection! then see the type name
            # cause it's different from obj.name|upper we print for enums now
            return f"fields.Many2one({self.filters.format_arguments(kwargs, 4)})"


        # TODO get xsd simpleType with xpath on original etree like:
        # >>> t.getroot().xpath("//xs:element[@name='ICMSTot']//xs:element[@name='vProd']", namespaces={'xs': 'http://www.w3.org/2001/XMLSchema',})[0].get('type')
        # 'TDec_1302'