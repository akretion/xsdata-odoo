import os
import re
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Dict
from typing import Iterator
from typing import List
from typing import Optional

from jinja2 import Environment
from jinja2 import FileSystemLoader
from lxml import etree
from xsdata.codegen.models import Attr
from xsdata.codegen.models import Class
from xsdata.codegen.resolver import DependenciesResolver
from xsdata.formats.dataclass.filters import Filters
from xsdata.formats.mixins import AbstractGenerator
from xsdata.formats.mixins import GeneratorResult
from xsdata.logger import logger
from xsdata.models.config import GeneratorConfig
from xsdata.utils import collections
from xsdata.utils import namespaces

from .wrap_text import extract_string_and_help
from .wrap_text import wrap_text


INTEGER_TYPES = ("integer", "positiveInteger")
FLOAT_TYPES = ("float",)
DECIMAL_TYPES = ("decimal",)
CHAR_TYPES = (
    "string",
    "NMTOKEN",
    "ID",
    "IDREF",
    "IDREFS",
    "anyURI",
    "base64Binary",
    "normalizedString",
)
DATE_TYPES = ("date",)
BOOLEAN_TYPES = "boolean"

# generally it's not interresting to generate mixins for signature
SIGNATURE_CLASS_SKIP = [
    "^Signature$",
    "^SignatureValue$",
    "^SignedInfo$",
    "^Reference$",
    "^DigestMethod$",
    "^Transforms$",
    "^Transform$",
    "^KeyInfo$",
    "^X509Data$",
    "^CanonicalizationMethod$",
    "^SignatureMethod$",
]


# TODO enums from included files like TAMB are generated in other files (tiposBasico_v4/00.py)
# see in render method for option to repeat these enums (or import)
# TODO extract enums and fields docstring using lxml
# TODO define m2o of the o2m fields. see #1 of https://github.com/akretion/generateds-odoo/issues/10
# in fact it seems what we do sort of work but we can have only 1 o2m to a given class in a class
# and also it the keys changed compared to generateDS and we also need to write the key in the o2m.
# TODO use the simple type to convert to fields.Monetary
# TODO extract float digits when possible



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
                "pattern_skip": self.pattern_skip,
                "class_name": self.class_name,
                "registry_name": self.registry_name,
                "clean_docstring": self.clean_docstring,
                "binding_type": self.binding_type,
                "parent_many2one": self.parent_many2one,
                "odoo_field_definition": self.odoo_field_definition,
                "field_name": self.field_name,
            }
        )
        self.class_case: Callable = config.conventions.class_name.case
        self.class_safe_prefix: str = config.conventions.class_name.safe_prefix
        self.files_to_etree: Dict[str, Any] = {}

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

        def render_class(obj: Class) -> str:
            """Render class or enumeration."""
            template = "enum.jinja2" if obj.is_enumeration else "class.jinja2"
            return load(template).render(obj=obj).strip()

        output = "\n\n".join(map(render_class, classes))
        return f"\n{output}\n"

    # jinja2 filters:

    def pattern_skip(self, name: str, parents: List[Class]) -> bool:
        """Should class or field be skipped?"""
        class_skip = SIGNATURE_CLASS_SKIP
        if os.environ.get("SKIP"):
            class_skip += os.environ["SKIP"].split("|")
        for pattern in class_skip:
            # do we have a simple match? (no scoping can be risky)
            if re.search(pattern, name):
                return True
            part_count = pattern.count(".") + 1
            if part_count > 1:
                # eventually we search for the class with its parents scope
                parent_pattern = ".".join(
                    [namespaces.local_name(c.qname) for c in parents[-part_count:]]
                )
                if re.search(pattern, parent_pattern):
                    return True
                # we now search for the field_name with its parents scope
                field_parent_pattern = ".".join(
                    [namespaces.local_name(c.qname) for c in parents[-part_count + 1 :]]
                    + [name]
                )
                if re.search(pattern, field_parent_pattern):
                    return True

        return False

    def class_name(self, name: str, replace_type: bool = True) -> str:
        """Convert the given string to a class name according to the selected
        conventions or use an existing alias."""
        # print(name, self.class_safe_prefix, self.class_case)
        class_name = self.filters.safe_name(
            name, self.class_safe_prefix, self.class_case
        )
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
        """Prepare string for docstring generation."""
        if not string:
            return ""  # TODO read from parent field if any

        # taken from https://github.com/akretion/generateds-odoo
        return "\n    {}".format(wrap_text(string, 4, 79))

    def binding_type(
        self,
        obj: Class,
        parents: List[Class],
    ) -> str:
        """Return the name of the xsdata class for a given Odoo model."""
        return ".".join([self.class_name(p.name, False) for p in parents])

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

    def parent_many2one(self, obj: Class, parents: List[Class]) -> str:
        """
        Nested XML tags become one2many or one2one in Odoo.

        So inner classes need a many2one relationship to their parent.
        (these inner classes can eventually be denormalized in their
        parent when using spec_driven_model.models.StackedModel).
        """
        if len(parents) > 1:
            parent = parents[-2]
            fname = self.field_name(parent.name)
            kwargs = {
                "comodel": self.registry_comodel([parent.name]),
                "required": True,
                "ondelete": "cascade",
            }
            return f"{fname}_id = fields.Many2one({self.filters.format_arguments(kwargs, 4)})"
        else:
            return ""

    def odoo_field_definition(
        self,
        attr: Attr,
        parents: List[Class],
    ) -> str:
        """Return the Odoo field definition."""

        # 1st some checks inspired from Filters.field_type:
        type_names = collections.unique_sequence(
            self.filters.field_type_name(x, [p.name for p in parents])
            for x in attr.types
        )

        if len(type_names) > 1:
            logger.warning(
                f"len(type_names) > 1 (Union) not implemented yet! class: {parents[-1].name} attr: {attr}"
            )

        if attr.is_tokens:
            logger.warning(
                f"attr.is_tokens not implemented yet! class: {parents[-1].name} attr: {attr}"
            )

        if attr.is_dict:
            logger.warning(
                f"attr.is_dict not implemented yet! class: {parents[-1].name} attr: {attr}"
            )

        # if attr.is_nillable or (
        #     attr.default is None and (attr.is_optional or not self.format.kw_only)
        # ):
        #     return f"Optional[{result}]"

        # default_value = self.filters.field_default_value(attr, {})
        metadata = self.filters.field_metadata(attr, {}, [p.name for p in parents])
        if not self.files_to_etree.get(parents[-1].location):
            xsd_tree = etree.parse(parents[-1].location)
            self.files_to_etree[parents[-1].location] = xsd_tree
        else:
            xsd_tree = self.files_to_etree[parents[-1].location]

        type_lookups = (
            f"//xs:element[@name='{parents[-1].name}']//xs:element[@name='{attr.name}']",
            f"//xs:element[@name='{parents[-1].name}']//xs:attribute[@name='{attr.name}']",
            f"//xs:complexType[@name='{parents[-1].name}']//xs:element[@name='{attr.name}']",
            f"//xs:complexType[@name='{parents[-1].name}']//xs:attribute[@name='{attr.name}']",
        )
        xsd_type = None
        for lookup in type_lookups:
            xpath_matches = xsd_tree.getroot().xpath(
                lookup,
                namespaces={
                    "xs": "http://www.w3.org/2001/XMLSchema",
                },
            )
            if xpath_matches:
                xsd_type = xpath_matches[0].get("type")
                break

        kwargs = {}
        if xsd_type:
            kwargs["xsd_type"] = xsd_type

        if metadata.get("required"):
            # we choose not to put required=True to avoid
            # messing with existing Odoo modules.
            kwargs["xsd_required"] = True

        if not hasattr(parents[-1], "unique_labels"):
            parents[-1].unique_labels = set()  # will avoid repeating field labels
        string, help_attr = extract_string_and_help(
            attr.name, attr.help, parents[-1].unique_labels
        )
        if string != attr.name:
            kwargs["string"] = string
        if help_attr and help_attr != string:
            kwargs["help"] = help_attr

        if attr.is_list:
            kwargs["comodel"] = self.registry_comodel(type_names)
            return f"fields.One2many({self.filters.format_arguments(kwargs, 4)})"
        elif attr.types[0].datatype:
            python_type = attr.types[0].datatype.code
            if python_type in INTEGER_TYPES:
                return f"fields.Integer({self.filters.format_arguments(kwargs, 4)})"
            if python_type in FLOAT_TYPES:
                return f"fields.Float({self.filters.format_arguments(kwargs, 4)})"
            elif python_type in DECIMAL_TYPES:
                return f"fields.Monetary({self.filters.format_arguments(kwargs, 4)})"
            elif python_type in CHAR_TYPES:
                return f"fields.Char({self.filters.format_arguments(kwargs, 4)})"
            elif python_type in DATE_TYPES:
                return f"fields.Date({self.filters.format_arguments(kwargs, 4)})"
            elif python_type in BOOLEAN_TYPES:
                return f"fields.Boolean({self.filters.format_arguments(kwargs, 4)})"
            else:
                logger.warning(
                    f"{python_type} {attr.types[0].datatype} not implemented yet! class: {parents[-1].name} attr: {attr}"
                )
                return ""
        else:  # Many2one
            kwargs["comodel"] = self.registry_comodel(type_names)
            # print(f"--- {parents[-1].name} {attr.name} {self.registry_comodel(type_names)}")
            # TODO it can be a fields.Selection! then see the type name
            # cause it's different from obj.name|upper we print for enums now
            return f"fields.Many2one({self.filters.format_arguments(kwargs, 4)})"
