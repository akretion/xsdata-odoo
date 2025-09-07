import os
import re
from collections import OrderedDict
from typing import Any, Dict, List, Optional

from jinja2 import Environment
from xsdata.codegen.models import Attr, Class
from xsdata.formats.dataclass.filters import Filters
from xsdata.logger import logger
from xsdata.models.config import GeneratorConfig, ObjectType
from xsdata.utils import namespaces

from .text_utils import extract_string_and_help, wrap_text

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
DATE_TYPES = ("date", "TData")
DATETIME_TYPES = ("dateTime", "TDateTimeUTC")
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
    "^RSAKeyValue$",
    "^TRSAKeyValueType$",
]


class OdooFilters(Filters):
    __slots__ = (
        "files_to_etree",
        "all_simple_types",
        "all_complex_types",
        "registry_names",
        "implicit_many2ones",
        "schema",
        "version",
        "python_inherit_model",
        "inherit_model",
        "xsd_extra_info",
        "relative_imports",
    )

    def __init__(
        self,
        config: GeneratorConfig,
        all_simple_types: List[Class],
        all_complex_types: List[Class],
        registry_names: Dict,
        implicit_many2ones: Dict,
        schema: str = "spec",
        version: str = "10",
        python_inherit_model: str = "models.AbstractModel",
        inherit_model=None,
    ):
        super().__init__(config)
        self.all_simple_types = all_simple_types
        self.all_complex_types = all_complex_types
        self.registry_names = registry_names
        self.implicit_many2ones = implicit_many2ones
        self.files_to_etree: Dict[str, Any] = {}
        self.schema = schema
        self.version = version
        self.python_inherit_model = python_inherit_model
        if inherit_model is None:
            inherit_model = f"spec.mixin.{schema}"
        self.inherit_model = inherit_model
        self.xsd_extra_info: Dict[str, Any] = {}
        self.relative_imports = True

    def register(self, env: Environment):
        super().register(env)
        env.filters.update(
            {
                "enum_skip": self.enum_skip,
                "pattern_skip": self.pattern_skip,
                "registry_name": self.registry_name,
                "odoo_python_inherit_model": self.odoo_python_inherit_model,
                "odoo_inherit_model": self.odoo_inherit_model,
                "clean_docstring": self.clean_docstring,
                "binding_type": self.binding_type,
                "odoo_class_name": self.odoo_class_name,
                "class_properties": self.class_properties,
                "odoo_class_description": self.odoo_class_description,
                "odoo_field_definition": self.odoo_field_definition,
                "odoo_implicit_many2ones": self.odoo_implicit_many2ones,
                "import_class": self.import_class,
                "enum_docstring": self.enum_docstring,
            }
        )

    def enum_skip(self, obj: Class, name: str) -> bool:
        """
        Avoids Postgres errors with fields.Selection
        by disabling case insensitive duplicates.
        For instance:
        TENDEREMI_XPAIS = [
            ("Brasil", "Brasil"),
        # ("BRASIL", "BRASIL"),
        ]
        """
        lower_vals = set()
        allowed_vals = set()
        for attr in obj.attrs:
            if attr.default.lower() not in lower_vals:
                lower_vals.add(attr.default.lower())
                allowed_vals.add(attr.default)
        if name in allowed_vals:
            return False
        else:
            return True

    def pattern_skip(self, name: str, parents: Optional[List[Class]] = None) -> bool:
        """Should class or field be skipped?"""
        if parents is None:
            parents = []
        class_skip = SIGNATURE_CLASS_SKIP.copy()
        if os.environ.get("XSDATA_SKIP"):
            class_skip += os.environ["XSDATA_SKIP"].split("|")
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
            return """textwrap.dedent(f"    {__doc__}")"""
        else:
            # TODO some inner classes have no obj.help
            # but we can read the XML annotations. Ex: "TretEnviNfe.InfRec", "Tnfe.InfNfe"...
            return f'"{obj.name}"'

    def enum_docstring(self, obj: Class) -> str:
        """Also format enum items. Works well for Brazilian fiscal xsd, may need adaptations for
        your xsd."""
        separators = (" - ", "-", " – ", "–")
        if "_" in obj.name:
            type_qname = obj.qname.split("_")[0]
            field_name = obj.name.split("_")[1]
            for klass in self.all_complex_types:
                if klass.qname == type_qname:
                    for idx, item in enumerate(obj.attrs):
                        for field in klass.attrs:
                            if field.name != field_name or not field.help:
                                continue
                            item_help = False
                            for separator in separators:
                                split = field.help.split(f"{item.default}{separator}")
                                if len(split) > 1:
                                    # TODO sometimes the line may continue
                                    # until the next value or may end at next value...
                                    item_help = split[1].splitlines()[0].split(";")[0]
                                    break

                            if item_help:
                                item.help = item_help
                                if idx == 0 and len(split) > 1:
                                    obj.help, _help_trash = extract_string_and_help(
                                        obj.name,
                                        field.name,
                                        split[0],
                                        set(),
                                        1024,
                                    )
                            else:
                                item.help = item.default
                            if (
                                idx == 0
                                and not obj.help
                                and not field.help.startswith(item.default)
                            ):
                                obj.help = (
                                    field.help.strip()
                                )  # no split but better than no docstring

        for item in obj.attrs:  # (it also apply to simple_types)
            if not item.help:
                item.help = f'"{item.default}"'
                continue
            item.help = item.help.replace("\n", "").replace('"', "'").strip()
            if len(item.help) > 78:
                lines = [
                    f'"{line.strip()} "'.replace('- "', '-"')
                    for line in wrap_text(item.help, 8, 78)
                    .replace('"""', "")
                    .splitlines()
                ]
                lines[-1] = lines[-1].replace(' "', '"')
                lines_str = "\n     ".join(lines)
                item.help = f"\n    ({lines_str})"
            else:
                item.help = f'"{item.help}"'

        if obj.help:
            return "# " + "\n# ".join(
                wrap_text(obj.help.strip(), 0, 78).replace('"', "").splitlines()
            )
        else:
            return ""

    def odoo_class_name(self, obj: Class, parents: List[Class] = []):
        """
        Same as class_name with the --unnest-classes option but without the
        option side effects.
        """
        full_name = ".".join([self.class_name(c.name) for c in parents])
        return self.registry_names[full_name].replace(".", "")

    def registry_name(
        self,
        name: str = "",
        parents: List[Class] = [],
        type_names: List[str] = [],
    ) -> str:
        if parents:
            full_name = ".".join([self.class_name(c.name) for c in parents])
        else:
            if type_names:
                full_name = ".".join(type_names)
            else:
                full_name = self.class_name(name)
        # NOTE we cannot use the class ref as a key because only type names
        # are provided by xsdata for fields
        unique_name = self.registry_names[full_name].replace(".", "_")
        return f"{self.schema}.{self.version}.{unique_name.lower()}"

    def odoo_inherit_model(self, obj: Class) -> str:
        return self.inherit_model

    def odoo_python_inherit_model(self, obj: Class) -> str:
        return self.python_inherit_model

    def registry_comodel(self, type_name: str):
        # NOTE: we take only the last part of inner Types with .split(".")[-1]
        # but if that were to create Type duplicates we could change that.
        clean_type_names = type_name.replace('"', "").split(".")
        return self.registry_name(clean_type_names[-1], type_names=clean_type_names)

    def clean_docstring(self, string: Optional[str], escape: bool = True) -> str:
        """Prepare string for docstring generation."""
        if not string:
            return ""  # TODO read from parent field if any
        return "\n    {}".format(wrap_text(string.strip(), 4, 79))

    def class_properties(
        self,
        obj: Class,
        parents: List[Class],
    ) -> str:
        """Return the name of the xsdata class for a given Odoo model."""
        if os.environ.get("XSDATA_GENDS"):
            return (
                f'_binding_type = "{self.binding_type(obj, parents)}"\n'
                f'    _generateds_type = "{self.generateds_type(obj, parents)}"'
            )
        else:
            return f'_binding_type = "{self.binding_type(obj, parents)}"\n'

    def binding_type(
        self,
        obj: Class,
        parents: List[Class],
    ) -> str:
        """Return the name of the xsdata class for a given Odoo model."""
        return ".".join([self.class_name(p.name) for p in parents])

    def generateds_type(
        self,
        obj: Class,
        parents: List[Class],
    ) -> str:
        """
        DEPRECATED!
        Return the name of the GenerateDS class for a given Odoo model.
        This is for backward compatibility: it allows to use Odoo mixins
        generated with xsdata along with legacy GenerateDS Python bindings.
        """
        if len(parents) > 1:
            return obj.qname.split("}")[1] + "Type"
        else:
            return obj.qname.split("}")[1]

    def odoo_implicit_many2ones(self, obj: Class, parents: List[Class]) -> str:
        """The m2o fields for the o2m keys."""
        fields = []
        implicit_many2ones = self.implicit_many2ones.get(
            self.binding_type(obj, parents).lower(),
            [],
            # NOTE: strangely lower is required (Brazilian CTe)
        )
        for implicit_many2one_data in implicit_many2ones:
            kwargs = OrderedDict()
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
        """Like xsdata but you can enforce the prefix or safe_name
        conversion."""
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

    def odoo_field_definition(
        self,
        attr: Attr,
        parents: List[Class],
    ) -> str:
        """Return the Odoo field definition."""

        # 1st some checks inspired from xsdata Filters:
        obj = parents[-1]
        type_names = self._field_type_names(obj, attr)
        # collections.unique_sequence(
        #    self._field_type_name(x, [p.name for p in parents]) for x in attr.types
        # )
        if len(attr.types) > 1:
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

        kwargs = self._extract_field_attributes(parents, attr)

        if attr.types[0].datatype:  # simple field
            return self._simple_field_definition(obj, attr, type_names, kwargs)

        else:  # relational field
            field = self._try_one2many_field_definition(obj, attr, type_names, kwargs)
            if field is None:
                field = self._try_selection_field_definition(
                    obj, attr, type_names, kwargs
                )
                if field is None:
                    field = self._try_many2one_field_definition(
                        obj, attr, type_names, kwargs
                    )

            if field is not None:
                return field

            message = f"Missing class {attr.types[0]}! class: {obj.name} attr: {attr}"
            logger.warning(message)
            return message

    def _extract_field_attributes(
        self, parents: List[Class], attr: Attr
    ) -> OrderedDict[str, Any]:
        obj = parents[-1]
        kwargs: OrderedDict[str, Any] = OrderedDict()
        if not hasattr(obj, "unique_labels"):
            obj.unique_labels = set()  # will avoid repeating field labels
        string, help_attr = extract_string_and_help(
            obj.name, attr.name, attr.help, obj.unique_labels
        )
        kwargs["string"] = string

        metadata = self.field_metadata(obj, attr, None)
        if metadata.get("required"):
            # we choose not to put required=True (required in database) to avoid
            # messing with existing Odoo modules.
            kwargs["xsd_required"] = True

        kwargs.update(self.xsd_extra_info.get(f"{obj.name}#{attr.name}", {}))
        if help_attr and not kwargs.get("help"):
            kwargs["help"] = help_attr  # (help as the last attribute)

        return kwargs

    def _extract_number_attrs(
        self, obj: Class, attr: Attr, kwargs: OrderedDict[str, Any]
    ):
        """
        Monetary vs Float field detection.

        Detection tends to be brittle but in general it doesn't impact
        XML serialization/desrialization as both types are floats and we
        usually take the xsd_type into account.

        You can somewhat customize the default behavior with ENV VARs:
        XSDATA_MONETARY_TYPE: xsd type to force fields.Monetary
        XSDATA_NUM_TYPE: xsd type for fields.Float or fields.Monetary eventually
        you can use a prefix followed by brackets to indicate where to take the
        floor part and the decimal part like Prefix[in_start:int_stop.dec_start:dec_stop]
        """
        python_type = attr.types[0].datatype.code
        if python_type in FLOAT_TYPES or python_type in CHAR_TYPES:
            xsd_type = kwargs.get("xsd_type", "")

            monetary_type = os.environ.get("XSDATA_MONETARY_TYPE")

            num_type_complete = os.environ.get("XSDATA_NUM_TYPE", "TDec_[5:7.7:9]")
            if "[" in num_type_complete:
                int_part = num_type_complete.split("[")[1].split(".")[0]
                int_start = int(int_part.split(":")[0])
                int_stop = int(int_part.split(":")[1])
                dec_part = num_type_complete.split(".")[1].split("]")[0]
                dec_start = int(dec_part.split(":")[0])
                dec_stop = int(dec_part.split(":")[1])
                num_type = num_type_complete.split("[")[0]
                conditional_monetary = True
            else:
                num_type = num_type_complete
                conditional_monetary = False

            if monetary_type and xsd_type.startswith(monetary_type):
                kwargs["currency_field"] = "brl_currency_id"  # TODO use spec_curreny_id
            elif xsd_type.startswith(num_type):
                if conditional_monetary:
                    if int(
                        xsd_type.replace("03v", "03")[dec_start:dec_stop]
                    ) != MONETARY_DIGITS or (
                        # for Brazilian edocs, pSomething means percentualSomething ->Float
                        attr.name[0] == "p" and attr.name[1].isupper()
                    ):
                        kwargs["digits"] = (
                            int(xsd_type.replace("03v", "03")[int_start:int_stop]),
                            int(xsd_type.replace("03v", "03")[dec_start:dec_stop]),
                        )
                    else:
                        kwargs["currency_field"] = (
                            "brl_currency_id"  # TODO use spec_curreny_id
                        )
                else:
                    kwargs["digits"] = (16, 4)

    def _simple_field_definition(
        self, obj: Class, attr: Attr, type_names: str, kwargs: OrderedDict
    ):
        self._extract_number_attrs(obj, attr, kwargs)
        if kwargs.get("help"):
            kwargs.move_to_end("help", last=True)
        python_type = attr.types[0].datatype.code
        if python_type in DATE_TYPES or kwargs.get("xsd_type") in DATE_TYPES:
            return f"fields.Date({self.format_arguments(kwargs, 4)})"
        elif python_type in DATETIME_TYPES or kwargs.get("xsd_type") in DATETIME_TYPES:
            return f"fields.Datetime({self.format_arguments(kwargs, 4)})"
        elif python_type in INTEGER_TYPES:
            return f"fields.Integer({self.format_arguments(kwargs, 4)})"
        if kwargs.get("currency_field"):
            return f"fields.Monetary({self.format_arguments(kwargs, 4)})"
        elif python_type in FLOAT_TYPES or kwargs.get("digits"):
            return f"fields.Float({self.format_arguments(kwargs, 4)})"
        elif python_type in CHAR_TYPES:
            return f"fields.Char({self.format_arguments(kwargs, 4)})"
        elif python_type in BOOLEAN_TYPES:
            return f"fields.Boolean({self.format_arguments(kwargs, 4)})"
        else:
            logger.warning(
                f"{python_type} {attr.types[0].datatype} not implemented yet! class: {obj.name} attr: {attr}"
            )
            return ""

    def _try_one2many_field_definition(
        self, obj: Class, attr: Attr, type_names: str, kwargs: OrderedDict
    ):
        if attr.is_list:
            if self.pattern_skip(attr.types[0].name):
                return ""
            comodel_key = self.field_name(f"{attr.name}_{obj.name}_id", obj.name)
            if type_names.split(".")[-1].lower().replace('"', "") not in [
                t.name.lower() for t in self.all_complex_types
            ]:
                logger.warning(
                    f"no complex type found for {type_names}; skipping attr {attr.name} in class {obj.name}!"
                )
                # example cte40_cInfManu in Brazilian CTe. Seems like a o2m to a simple type/Enum. Not implemented yet.
                return ""
            return f"""fields.One2many("{self.registry_comodel(type_names)}", "{comodel_key}",{self.format_arguments(kwargs, 4)})"""

    def _try_selection_field_definition(
        self, obj: Class, attr: Attr, type_names: str, kwargs: OrderedDict
    ):
        for klass in self.all_simple_types:
            if attr.types[0].qname == klass.qname:
                if self.pattern_skip(klass.name.upper()):
                    return ""

                return f"fields.Selection({klass.name.upper()},{self.format_arguments(kwargs, 4)})"

    def _try_many2one_field_definition(
        self, obj: Class, attr: Attr, type_names: str, kwargs: OrderedDict
    ):
        for klass in self.all_complex_types:
            if attr.types[0].qname == klass.qname:
                if self.pattern_skip(attr.types[0].name):
                    return ""
                # Many2one
                kwargs["comodel_name"] = self.registry_comodel(type_names)
                kwargs.move_to_end("comodel_name", last=False)
                return f"fields.Many2one({self.format_arguments(kwargs, 4)})"

    def import_class(self, name: str, alias: Optional[str]) -> str:
        """Convert import class name with alias support."""
        if alias:
            return f"{self.class_name(name)} as {self.class_name(alias)}"
        if name in [klass.name for klass in self.all_simple_types]:
            return name.upper()  # const are upcase in Odoo
        else:
            return self.class_name(name)
