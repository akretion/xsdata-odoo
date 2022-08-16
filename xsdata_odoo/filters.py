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
from xsdata.models.config import ObjectType
from xsdata.formats.dataclass.filters import Filters
from xsdata.logger import logger
from xsdata.models.config import GeneratorConfig
from xsdata.utils import collections
from xsdata.utils import namespaces

from .wrap_text import extract_string_and_help
from .wrap_text import wrap_text


INTEGER_TYPES = ("integer", "positiveInteger")
FLOAT_TYPES = ("float", "decimal")
# Odoo has no Decimal field and all in all it's better to guess float by default
# and override if required.
# DECIMAL_TYPES = ("decimal",)
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
    "^SignatureType$",
    "^SignatureValueType$",
    "^SignedInfoType$",
    "^ReferenceType$",
    "^DigestMethodType$",
    "^TransformsType$",
    "^TransformType$",
    "^KeyInfoType$",
    "^X509DataType$",
    "^CanonicalizationMethodType$",
    "^SignatureMethodType$",
]


class OdooFilters(Filters):

    __slots__ = (
        "files_to_etree",
        "all_simple_types",
        "all_complex_types",
        "implicit_many2ones",
        "schema",
        "version",
        "python_inherit_model",
        "inherit_model",
    )

    def __init__(
        self,
        config: GeneratorConfig,
        all_simple_types: List[Class],
        all_complex_types: List[Class],
        implicit_many2ones: Dict,
        schema: str = "spec",
        version: str = "10",
        python_inherit_model: str = "models.AbstractModel",
        inherit_model = None,
    ):
        super().__init__(config)
        self.all_simple_types = all_simple_types
        self.all_complex_types = all_complex_types
        self.implicit_many2ones = implicit_many2ones
        self.files_to_etree: Dict[str, Any] = {}
        self.relative_imports = True
        self.schema = schema
        self.version = version
        self.python_inherit_model = python_inherit_model
        if inherit_model is None:
            inherit_model = f"spec.mixin.{schema}"
        self.inherit_model = inherit_model

    def register(self, env: Environment):
        super().register(env)
        env.filters.update(
            {
                "pattern_skip": self.pattern_skip,
                "registry_name": self.registry_name,
                "odoo_python_inherit_model": self.odoo_python_inherit_model,
                "odoo_inherit_model": self.odoo_inherit_model,
                "clean_docstring": self.clean_docstring,
                "binding_type": self.binding_type,
                "odoo_class_description": self.odoo_class_description,
                "odoo_field_definition": self.odoo_field_definition,
                "odoo_implicit_many2ones": self.odoo_implicit_many2ones,
                "import_class": self.import_class,
                "enum_docstring": self.enum_docstring,
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

    def odoo_class_description(self, obj: Class) -> str:
        if obj.help:
            return f"""textwrap.dedent("    %s" % (__doc__,))"""
        else:
            # TODO some inner classes have no obj.help
            # but we can read the XML annotations. Ex: "TretEnviNfe.InfRec", "Tnfe.InfNfe"...
            return f'"{obj.name}"'

    def enum_docstring(self, obj: Class) -> str:
        """Works well for Brazilian fiscal xsd, may need adaptations for your
        xsd."""
        # see https://github.com/akretion/generateds-odoo/blob/465539b46e4216a5b94f1b0dabf39b34e7f4624c/gends_extract_simple_types.py#L385
        # for possible improvement

        if "_" in obj.name:
            type_qname = obj.qname.split("_")[0]
            field_name = obj.name.split("_")[1]

            for klass in self.all_complex_types:
                if klass.qname == type_qname:
                    for idx, item in enumerate(obj.attrs):
                        for field in klass.attrs:
                            if field.name == field_name and field.help:
                                split = field.help.split(f"{item.default} - ")
                                help = False
                                if len(split) > 1:
                                    # TODO sometimes the line may continue
                                    # until the next value or may end at next value...
                                    help = split[1].splitlines()[0].split(";")[0]
                                else:
                                    split = field.help.split(f"{item.default}-")
                                    if len(split) > 1:
                                        help = split[1].splitlines()[0].split(";")[0]
                                if help:
                                    item.help = help
                                    # FIXME it doesn't always work
                                    if idx == 0 and not obj.help and len(split) > 1:
                                        obj.help = split[0]
                                else:
                                    item.help = item.default

        return self.clean_docstring(obj.help)

    def registry_name(self, name: str) -> str:
        name = self.class_name(name)
        return f"{self.schema}.{self.version}.{name.lower()}"

    def odoo_inherit_model(self, obj: Class) -> str:
        return self.inherit_model

    def odoo_python_inherit_model(self, obj: Class) -> str:
        return self.python_inherit_model

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

    def odoo_implicit_many2ones(self, obj: Class) -> str:
        fields = []
        implicit_many2ones = self.implicit_many2ones.get(
            self.registry_name(obj.name), []
        )
        for implicit_many2one_data in implicit_many2ones:
            kwargs = {}
            kwargs["comodel_name"] = implicit_many2one_data[0]
            kwargs["xsd_implicit"] = True
            # kwargs["required"] = True  # FIXME seems it creates ORM issues
            kwargs["ondelete"] = "cascade"
            target_field = implicit_many2one_data[1]
            fields.append(
                f"{target_field} = fields.Many2one({self.format_arguments(kwargs, 4)})"
            )
        return ("\n").join(fields)

    def field_name(self, name: str, class_name: str) -> str:
        prefix = self.field_safe_prefix
        name = self.apply_substitutions(name, ObjectType.FIELD)

        if self.field_safe_prefix in ("", "value"):  # do like standard xsdata
            name = self.safe_name(name, prefix, self.field_case, class_name=class_name)
        if self.field_safe_prefix == "NO_PREFIX_NO_SAFE_NAME":  # keep my field name!
            pass
        elif self.field_safe_prefix.endswith("SAFE_NAME"):  # prefix + python field name
            prefix = prefix.split("SAFE_NAME")[0]
            name = f"{prefix}{name}"
            name = self.safe_name(name, prefix, self.field_case, class_name=class_name)
        else:  # prefix + keep my field name
            name = f"{prefix}{name}"

        return self.apply_substitutions(name, ObjectType.FIELD)

    def odoo_extract_number_attrs(self, kwargs: Dict[str, Dict]):
        """
        Monetary field detection.

        Here adapted for Brazil fiscal schemas
        """
        xsd_type = kwargs.get("xsd_type")
        if xsd_type.startswith("TDec_"):  # TODO make pluggable. ENV?
            if int(xsd_type[7:9]) != MONETARY_DIGITS:
                kwargs["digits"] = (int(xsd_type[5:7]), int(xsd_type[7:9]))
                # TODO or xsd_type[-2:] for "TDec_0302a04" for instance
            else:
                kwargs[
                    "currency_field"
                ] = "brl_currency_id"  # TODO make it customizable!

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

        # default_value = self.field_default_value(attr, {})

        xsd_type = self.field_simple_type_from_xsd(obj, attr.name)
        if xsd_type and xsd_type not in [
            "xsd:string",
            "xsd:date",
        ]:  # (not in trivial types)
            kwargs["xsd_type"] = xsd_type
            self.odoo_extract_number_attrs(kwargs)

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

            if (python_type in FLOAT_TYPES or CHAR_TYPES) and kwargs.get(
                "digits", (0, 2)
            )[1] != MONETARY_DIGITS:
                #                kwargs["digits"] = kwargs["digits"][1]
                return f"fields.Float({self.format_arguments(kwargs, 4)})"
            elif python_type in FLOAT_TYPES or kwargs.get("currency_field"):
                return f"fields.Monetary({self.format_arguments(kwargs, 4)})"

            #            if (python_type in FLOAT_TYPES or CHAR_TYPES):
            #                if kwargs.get("currency_field"):
            #                    return f"fields.Monetary({self.format_arguments(kwargs, 4)})"
            #                else:
            #                    return f"fields.Float({self.format_arguments(kwargs, 4)})"

            elif python_type in CHAR_TYPES:
                return f"fields.Char({self.format_arguments(kwargs, 4)})"
            elif python_type in DATE_TYPES:
                return f"fields.Date({self.format_arguments(kwargs, 4)})"
            elif python_type in DATETIME_TYPES:
                return f"fields.Datetime({self.format_arguments(kwargs, 4)})"
            elif python_type in BOOLEAN_TYPES:
                return f"fields.Boolean({self.format_arguments(kwargs, 4)})"
            else:
                logger.warning(
                    f"{python_type} {attr.types[0].datatype} not implemented yet! class: {obj.name} attr: {attr}"
                )
                return ""
        else:
            if attr.is_list:
                comodel_key = self.field_name(f"{attr.name}_{obj.name}_id", obj.name)
                return f"""fields.One2many("{self.registry_comodel(type_names)}", "{comodel_key}",{self.format_arguments(kwargs, 4)})"""
            else:

                for klass in self.all_simple_types:
                    if attr.types[0].qname == klass.qname:
                        # Selection
                        return f"fields.Selection({klass.name.upper()},{self.format_arguments(kwargs, 4)})"
                        # kwargs["selection"] = klass.name.upper()
                        # return f"fields.Selection({self.format_arguments(kwargs, 4)})"
                for klass in self.all_complex_types:
                    if attr.types[0].qname == klass.qname:
                        # Many2one
                        kwargs["comodel_name"] = self.registry_comodel(type_names)
                        return f"fields.Many2one({self.format_arguments(kwargs, 4)})"

                message = (
                    f"Missing class {attr.types[0]}! class: {obj.name} attr: {attr}"
                )
                logger.warning(message)
                return message

    def import_class(self, name: str, alias: Optional[str]) -> str:
        """Convert import class name with alias support."""
        if alias:
            return f"{self.class_name(name)} as {self.class_name(alias)}"

        if name in [klass.name for klass in self.all_simple_types]:
            return self.class_name(name).upper()  # const are upcase in Odoo
        else:
            return self.class_name(name)

    def field_simple_type_from_xsd(self, obj: Class, attr_name: str):
        location = (obj.location or "").replace("file://", "")
        if not os.path.isfile(location):
            return None
        if not self.files_to_etree.get(location):
            xsd_tree = etree.parse(location)
            self.files_to_etree[location] = xsd_tree
        else:
            xsd_tree = self.files_to_etree[location]

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
