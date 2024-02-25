import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict
from typing import Iterator
from typing import List
from typing import Optional

from black import FileMode
from black import format_str
from jinja2 import Environment
from jinja2 import FileSystemLoader
from lxml import etree
from xsdata.codegen.models import Class
from xsdata.codegen.resolver import DependenciesResolver
from xsdata.formats.dataclass.generator import DataclassGenerator
from xsdata.formats.mixins import GeneratorResult
from xsdata.models.config import GeneratorConfig
from xsdata.utils import collections

from .codegen.resolver import OdooDependenciesResolver
from .filters import OdooFilters
from .filters import SIGNATURE_CLASS_SKIP

# only put this header in files with complex types (not in tipos_basico_v4_00.py for instance)
# import textwrap
# from odoo import fields, models

# WISHLIST pluggable filters (test with UBL and cbc: => simpleType + UBL simple types mapping)
# (see UBL branch for UBL)


class OdooGenerator(DataclassGenerator):
    """Odoo generator."""

    def __init__(self, config: GeneratorConfig):
        schema = os.environ.get("XSDATA_SCHEMA", "spec")
        version = os.environ.get("XSDATA_VERSION", "10")
        # if field prefix is not set via the config (default is "value")
        # then set it with SCHEMA and VERSION env vars
        if config.conventions.field_name.safe_prefix == "value":
            config.conventions.field_name.safe_prefix = f"{schema}{version}_"

        super().__init__(config)
        self.all_simple_types: List[Class] = []
        self.all_complex_types: List[Class] = []
        self.registry_names: Dict = {}
        self.implicit_many2ones: Dict = defaultdict(list)
        tpl_dir = Path(__file__).parent.joinpath("templates")
        self.env = Environment(loader=FileSystemLoader(str(tpl_dir)), autoescape=False)
        self.filters = OdooFilters(
            config,
            self.all_simple_types,
            self.all_complex_types,
            self.registry_names,
            self.implicit_many2ones,
            schema,
            version,
        )
        self.filters.register(self.env)

    def _find_duplicated_names(self, class_paths):
        duplicates = set()
        names = set()

        for ref, path in class_paths.items():
            path_parts = path.split("|")
            name = path_parts[-1]
            if name in names:
                duplicates.add(name)
            names.add(name)

        return duplicates

    def simplify_name_sets(self, names_dict, class_names):
        """
        Find minimal unique name for class. We use dict keys as an ordered set.
        """
        initial_length = len(names_dict.keys())
        max_positions = max(map(lambda i: len(i.split("|")), names_dict.keys()))
        i = max_positions - 2
        while i >= 0:
            # try to remove each path part while ensuring no path collision (shorter len)
            test = {
                k: ""
                for k in map(
                    lambda path: len(path.split("|")) > i + 1
                    and "|".join(path.split("|")[:i] + path.split("|")[i + 1 :])
                    not in class_names
                    and "|".join(path.split("|")[:i] + path.split("|")[i + 1 :])
                    or path,
                    names_dict.keys(),
                )
            }
            i -= 1
            if len(test.keys()) == initial_length:
                names_dict = test
        return names_dict

    def _find_minimal_unique_name(self, class_paths, path_parts):
        """
        Find minimal unique name for class
        Minimal unique name is found by prepending the first uncommon parent to class name.
        """

        name = path_parts[-1]
        orig_path = "|".join(path_parts)
        duplicates = list()

        for ref, path in class_paths.items():
            if path.endswith("|" + name) and path != orig_path:
                duplicates.append(path)  # .split("|"))

        res = self.simplify_name_sets(
            {k: "" for k in [orig_path] + duplicates}, class_paths.values()
        )
        return list(res.keys())[0].replace("|", ".")

    def _find_minimal_unique_names(self, class_paths, duplicates):
        """
        Find minimal unique names for classes
        """

        class_names = dict()
        for ref, path in class_paths.items():
            path_parts = path.split("|")
            name = path_parts[-1]
            if name in duplicates:
                name = self._find_minimal_unique_name(class_paths, path_parts)

            class_names[ref] = name
        return class_names

    def _generate_unique_class_names(self, class_paths):
        """
        Generate unique class name
        Class names must be unique in the module, so we find the minimum
        unique name for each class using a depth-first search and
        prepending the parent class name.
        """
        duplicates = self._find_duplicated_names(class_paths)
        class_names = self._find_minimal_unique_names(class_paths, duplicates)
        return {
            ".".join([self.filters.class_name(i) for i in v.split("|")]): ".".join(
                [self.filters.class_name(name) for name in class_names[k].split(".")]
            )
            for k, v in class_paths.items()
        }

    def render(self, classes: List[Class]) -> Iterator[GeneratorResult]:
        """Return a iterator of the generated results."""
        registry = {obj.qname: obj.target_module for obj in classes}
        resolver = OdooDependenciesResolver(registry=registry)

        # Generate packages
        for path, cluster in self.group_by_package(classes).items():
            yield from self.ensure_packages(path.parent)

            class_paths = dict()

            def dfs(visited, graph, node, path=""):
                if (node, path) not in visited:
                    visited.append((node, path))
                    if path:
                        path = path + f"|{node.name}"
                    else:
                        path = node.name
                    class_paths[node.ref] = path
                    for neighbour in node.inner:  # in graph[node]:
                        # FIXME is this parent collecting buggy??
                        dfs(visited, graph, neighbour, path)

            all_file_classes: List[(Class, List(Class))] = []
            for c in cluster:
                dfs(all_file_classes, cluster, c)  # , c.name)

            unique_class_names = self._generate_unique_class_names(class_paths)
            for _ref, name in class_paths.items():
                full_name = ".".join(
                    [self.filters.class_name(i) for i in name.split("|")]
                )
                self.registry_names[full_name] = unique_class_names[full_name]

            for klass, path in all_file_classes:
                if not self.filters.files_to_etree.get(
                    klass.location
                ) and os.path.isfile(klass.location):
                    xsd_tree = etree.parse(klass.location)
                    self.filters.files_to_etree[klass.location] = xsd_tree

                if klass.is_enumeration and klass not in self.all_simple_types:
                    self.all_simple_types.append(
                        klass
                    )  # TODO add module name/path for import?
                for field in klass.attrs:
                    if not field.types[0].datatype and field.is_list:
                        if path:
                            parent_names = [
                                self.filters.class_name(i) for i in path.split("|")
                            ] + [self.filters.class_name(klass.name)]
                        else:
                            parent_names = [self.filters.class_name(klass.name)]

                        type_names = collections.unique_sequence(
                            self.filters._field_type_name(x, parent_names)
                            for x in field.types
                        )
                        target_field = self.filters.field_name(
                            f"{field.name}_{klass.name}_id",
                            klass.name,
                        )
                        comodel_type = type_names[0].replace('"', "").lower()
                        # NOTE strangely lower is required (Brazilian CTe)
                        self.implicit_many2ones[comodel_type].append(
                            (
                                self.filters.registry_name(
                                    klass.name, type_names=parent_names
                                ),
                                target_field,
                            )
                        )
                if klass not in self.all_complex_types:
                    self.all_complex_types.append(klass)

            for klass, path in all_file_classes:
                self._collect_extra_data(klass)

        # Generate modules
        for path, cluster in self.group_by_module(classes).items():
            should_skip = False
            for pattern in SIGNATURE_CLASS_SKIP:
                for klass in cluster:
                    if re.search(pattern, klass.name):
                        should_skip = True
                        break
            if should_skip:
                continue

            yield GeneratorResult(
                path=path.with_suffix(".py"),
                title=cluster[0].target_module,
                source=self.render_module(resolver, cluster),
            )

    def render_module(
        self, resolver: DependenciesResolver, classes: List[Class]
    ) -> str:
        res = super().render_module(resolver, classes)

        # for some reason, when generating several files at once,
        # some field can loose their indention, we fix them here:
        field_prefix = self.filters.field_safe_prefix
        res = "\n".join(
            [
                re.sub("^%s" % (field_prefix), "    %s" % (field_prefix), line)
                for line in res.splitlines()
            ]
        )

        # the overall formatting is not too bad but there are a few
        # glitches with line breaks, so we apply Black formatting.
        if not os.environ.get("XSDATA_NO_BLACK"):
            try:
                res = format_str(res, mode=FileMode())
            except Exception as e:
                print(e)
        return res

    def render_classes(
        self, classes: List[Class], module_namespace: Optional[str]
    ) -> str:
        """
        Render the source code of the classes.

        Overriden to control different number of line breaks for enums
        and classes for Odoo.
        """
        load = self.env.get_template

        def render_class(obj: Class) -> str:
            """Render class or enumeration."""
            if [ext.type for ext in obj.extensions]:
                # this is used only to change tag names, no Odoo model is required
                return ""
            if obj.is_enumeration:
                template = load("enum.jinja2")
            elif obj.is_service:
                template = load("service.jinja2")
            else:
                template = load("class.jinja2")

            string = template.render(
                obj=obj,
                module_namespace=module_namespace,
            ).strip()
            if not obj.is_enumeration:
                string = "\n" + string
            return string

        return "\n\n".join(map(render_class, classes)) + "\n"

    def _collect_extra_data(self, obj: Class):
        """Collect extra field data from the xsd file or another file"""

        location = (obj.location or "").replace("file://", "")
        if not os.path.isfile(location):
            return

        if not self.filters.files_to_etree.get(location):  # yes it can still happen
            xsd_tree = etree.parse(location)
            self.filters.files_to_etree[location] = xsd_tree
        else:
            xsd_tree = self.filters.files_to_etree[location]

        # if ComplexType has no description,
        # take it from the element declaration:
        if not obj.help:
            xpath_matches = xsd_tree.getroot().xpath(
                f"//xs:element[@name='{obj.name}']",
                namespaces={
                    "xs": "http://www.w3.org/2001/XMLSchema",
                    "xsd": "http://www.w3.org/2001/XMLSchema",
                },
            )
            if xpath_matches:
                children = xpath_matches[0].getchildren()
                if (
                    len(children) > 0
                    and children[0].tag
                    == "{http://www.w3.org/2001/XMLSchema}annotation"
                ):
                    obj.help = "".join(children[0].itertext())

        # extract fields choice attributes and types using xpath:
        for attr in obj.attrs:
            field_data = {}
            type_lookups = (
                f"//xs:element[@name='{obj.name}']//xs:element[@name='{attr.name}']",
                f"//xs:element[@name='{obj.name}']//xs:attribute[@name='{attr.name}']",
                f"//xs:complexType[@name='{obj.name}']//xs:element[@name='{attr.name}']",
                f"//xs:complexType[@name='{obj.name}']//xs:attribute[@name='{attr.name}']",
            )
            for lookup in type_lookups:
                xpath_matches = xsd_tree.getroot().xpath(
                    lookup,
                    namespaces={
                        "xs": "http://www.w3.org/2001/XMLSchema",
                        "xsd": "http://www.w3.org/2001/XMLSchema",
                    },
                )
                if xpath_matches:
                    xsd_choice_required = None
                    parent = xpath_matches[0].getparent()
                    # (here we don't try to group items by choice, but eventually we could)
                    while parent.tag == "{http://www.w3.org/2001/XMLSchema}sequence":
                        if (
                            parent.get("minOccurs", "1") == "0"
                        ):  # example veicTransp in Brazilian NFe
                            xsd_choice_required = False
                        parent = parent.getparent()
                    if parent.tag == "{http://www.w3.org/2001/XMLSchema}choice":
                        # here we assume only 1 choice per complexType
                        # but evexntually we could count them and number them...
                        field_data[
                            "choice"
                        ] = (
                            obj.name.lower()
                        )  # TODO consider changing choice -> xsd_choice
                        if (
                            parent.get("minOccurs", "1") != "0"
                            and xsd_choice_required is None
                        ):
                            # important feature we had in generateDS:
                            # if the element is part of <choice> tag without minOccurs="0"
                            # then it is required!
                            field_data["xsd_choice_required"] = True
                    xsd_type = xpath_matches[0].get("type")
                    if xsd_type and xsd_type not in [
                        "xsd:string",
                        "xsd:date",
                    ]:
                        field_data["xsd_type"] = xsd_type
                    self.filters.xsd_extra_info[f"{obj.name}#{attr.name}"] = field_data
