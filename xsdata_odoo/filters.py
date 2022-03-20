import os
import re
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

from jinja2 import Environment
from lxml import etree
from xsdata.codegen.models import Attr
from xsdata.codegen.models import Class
from xsdata.formats.dataclass.filters import Filters
from xsdata.logger import logger
from xsdata.models.config import GeneratorConfig
from xsdata.utils import collections
from xsdata.utils import namespaces

from .wrap_text import extract_string_and_help
from .wrap_text import wrap_text


INTEGER_TYPES = ("integer", "positiveInteger")
FLOAT_TYPES = ("float",)
DECIMAL_TYPES = ("decimal",)
MONETARY_DIGITS = 2
CHAR_TYPES = (
    "string",
    "NMTOKEN",
    "ID",
    "IDREF",
    "IDREFS",
    "anyURI",
    "base64Binary",
    "normalizedString",
    "language",
)
DATE_TYPES = ("date",)
DATETIME_TYPES = ("dateTime",)
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


class OdooFilters(Filters):

    __slots__ = (
        "files_to_etree",
        "all_simple_types",
        "all_complex_types",
    )

    def __init__(
        self,
        config: GeneratorConfig,
        all_simple_types: List[Class],
        all_complex_types: List[Class],
    ):
        super().__init__(config)
        self.all_simple_types = all_simple_types
        self.all_complex_types = all_complex_types
        self.files_to_etree: Dict[str, Any] = {}
        self.relative_imports = True

    def register(self, env: Environment):
        super().register(env)
        env.filters.update(
            {
                "pattern_skip": self.pattern_skip,
                "registry_name": self.registry_name,
                "clean_docstring": self.clean_docstring,
                "binding_type": self.binding_type,
                "parent_many2one": self.parent_many2one,
                "odoo_field_definition": self.odoo_field_definition,
                "odoo_field_name": self.odoo_field_name,
                "import_contant": self.import_contant,
            }
        )

    def pattern_skip(self, name: str, parents: List[Class] = None) -> bool:
        """Should class or field be skipped?"""
        if parents is None:
            parents = []
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

    def registry_name(self, name: str, replace_type: bool = True) -> str:
        schema = os.environ.get("SCHEMA", "spec")
        version = os.environ.get("VERSION", "10")
        name = self.class_name(name)
        if replace_type:
            name = name.rpartition("Type")[0] or name
        return f"{schema}.{version}.{name.lower()}"

    def registry_comodel(self, type_names: List[str]):
        # NOTE: we take only the last part of inner Types with .split(".")[-1]
        # but if that were to create Type duplicates we could change that.
        return self.registry_name(type_names[-1].split(".")[-1])

    def clean_docstring(self, string: Optional[str], escape: bool = True) -> str:
        """Prepare string for docstring generation."""
        if not string:
            return ""  # TODO read from parent field if any
        return "\n    {}".format(wrap_text(string, 4, 79))

    def binding_type(
        self,
        obj: Class,
        parents: List[Class],
    ) -> str:
        """Return the name of the xsdata class for a given Odoo model."""
        return ".".join([self.class_name(p.name) for p in parents])

    def odoo_field_name(self, name: str) -> str:
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
        TODO THIS IS ALL FUCKED UP. Nested XML tags become one2many or one2one
        in Odoo.

        So inner classes need a many2one relationship to their parent.
        (these inner classes can eventually be denormalized in their
        parent when using spec_driven_model.models.StackedModel).
        """
        if len(parents) > 1:
            parent = parents[-2]
            fname = self.odoo_field_name(parent.name)
            kwargs = {
                "comodel": self.registry_comodel([parent.name]),
                "required": True,
                "ondelete": "cascade",
            }
            return f"{fname}_id = fields.Many2one({self.format_arguments(kwargs, 4)})"
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
            self.field_type_name(x, [p.name for p in parents]) for x in attr.types
        )
        kwargs = {}
        obj = parents[-1]

        if len(type_names) > 1:
            logger.warning(
                f"len(type_names) > 1 (Union) not implemented yet! class: {obj.name} attr: {attr}"
            )

        if attr.is_tokens:
            logger.warning(
                f"attr.is_tokens not implemented yet! class: {obj.name} attr: {attr}"
            )

        if attr.is_dict:
            logger.warning(
                f"attr.is_dict not implemented yet! class: {obj.name} attr: {attr}"
            )

        # if attr.is_nillable or (
        #     attr.default is None and (attr.is_optional or not self.format.kw_only)
        # ):
        #     return f"Optional[{result}]"

        # default_value = self.field_default_value(attr, {})

        schema = os.environ.get("SCHEMA", "spec")
        version = os.environ.get("VERSION", "10")

        xsd_type = self.simple_type_from_xsd(obj, attr.name)
        if xsd_type:
            kwargs["xsd_type"] = xsd_type
            # Monetary field detection for Brazil fiscal docs, TODO make pluggable
            if xsd_type.startswith("TDec_"):
                kwargs["currency_field"] = "brl_currency_id"
                if int(xsd_type[7:9]) != MONETARY_DIGITS:
                    kwargs["digits"] = (int(xsd_type[5:7]), int(xsd_type[7:9]))

        metadata = self.field_metadata(attr, {}, [p.name for p in parents])
        if metadata.get("required"):
            # we choose not to put required=True (required in database) to avoid
            # messing with existing Odoo modules.
            kwargs["xsd_required"] = True

        if not hasattr(obj, "unique_labels"):
            obj.unique_labels = set()  # will avoid repeating field labels
        string, help_attr = extract_string_and_help(
            attr.name, attr.help, obj.unique_labels
        )
        kwargs["string"] = string
        if help_attr and help_attr != string:
            kwargs["help"] = help_attr
        if attr.types[0].datatype:
            python_type = attr.types[0].datatype.code
            if python_type in INTEGER_TYPES:
                return f"fields.Integer({self.format_arguments(kwargs, 4)})"
            if (python_type in FLOAT_TYPES or CHAR_TYPES) and kwargs.get("digits", (0, 2))[1] != MONETARY_DIGITS:
                kwargs["digits"] = kwargs["digits"][1]
                return f"fields.Float({self.format_arguments(kwargs, 4)})"
            elif python_type in DECIMAL_TYPES or kwargs.get("currency_field"):
                return f"fields.Monetary({self.format_arguments(kwargs, 4)})"
            elif python_type in CHAR_TYPES:
                return f"fields.Char({self.format_arguments(kwargs, 4)})"
            elif python_type in DATE_TYPES:
                return f"fields.Date({self.format_arguments(kwargs, 4)})"
            elif python_type in DATETIME_TYPES:
                return f"fields.DateTime({self.format_arguments(kwargs, 4)})"
            elif python_type in BOOLEAN_TYPES:
                return f"fields.Boolean({self.format_arguments(kwargs, 4)})"
            else:
                logger.warning(
                    f"{python_type} {attr.types[0].datatype} not implemented yet! class: {obj.name} attr: {attr}"
                )
                return ""
        else:
            if attr.is_list:
                return f"""fields.One2many("{self.registry_comodel(type_names)}", "{schema}{version}_{attr.name}_{obj.name}_id", {self.format_arguments(kwargs, 4)})"""
            else:

                for klass in self.all_simple_types:
                    if attr.types[0].qname == klass.qname:
                        # Selection
                        return f"fields.Selection({klass.name.upper()}, {self.format_arguments(kwargs, 4)})"
                        # kwargs["selection"] = klass.name.upper()
                        # return f"fields.Selection({self.format_arguments(kwargs, 4)})"
                for klass in self.all_complex_types:
                    if type(attr.types[0]) == str:
                        print(f"\nAAAAAA class: {obj.name} attr: {attr}")
                    if attr.types[0].qname == klass.qname:
                        # Many2one
                        kwargs["comodel"] = self.registry_comodel(type_names)
                        return f"fields.Many2one({self.format_arguments(kwargs, 4)})"

                message = f"Missing class {attr.types[0]}! class: {obj.name} attr: {attr}"
                logger.warning(message)
                return message


    def import_contant(self, name: str, alias: Optional[str]) -> str:
        """Convert import class name with alias support."""
        if alias:
            return f"{self.class_name(name).upper()} as {self.class_name(alias)}"

        return self.class_name(name).upper()

    def simple_type_from_xsd(self, obj: Class, attr_name: str):
        if not self.files_to_etree.get(obj.location):
            xsd_tree = etree.parse(obj.location)
            self.files_to_etree[obj.location] = xsd_tree
        else:
            xsd_tree = self.files_to_etree[obj.location]

        type_lookups = (
            f"//xs:element[@name='{obj.name}']//xs:element[@name='{attr_name}']",
            f"//xs:element[@name='{obj.name}']//xs:attribute[@name='{attr_name}']",
            f"//xs:complexType[@name='{obj.name}']//xs:element[@name='{attr_name}']",
            f"//xs:complexType[@name='{obj.name}']//xs:attribute[@name='{attr_name}']",
        )
        for lookup in type_lookups:
            xpath_matches = xsd_tree.getroot().xpath(
                lookup,
                namespaces={
                    "xs": "http://www.w3.org/2001/XMLSchema",
                },
            )
            if xpath_matches:
                return xpath_matches[0].get("type")
        return None
