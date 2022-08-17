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
from lxml import etree
from jinja2 import FileSystemLoader
from xsdata.codegen.handlers import MergeAttributes
from xsdata.codegen.models import Class
from xsdata.codegen.resolver import DependenciesResolver
from xsdata.formats.dataclass.generator import DataclassGenerator
from xsdata.formats.mixins import GeneratorResult
from xsdata.models.config import GeneratorConfig
from xsdata.utils import collections

from .codegen.resolver import OdooDependenciesResolver
from .filters import OdooFilters
from .filters import SIGNATURE_CLASS_SKIP
from .merge_attributes import MergeAttributes as PatchedMergeAttributes

# only put this header in files with complex types (not in tipos_basico_v4_00.py for instance)
# import textwrap
# from odoo import fields, models

# WISHLIST base model as a filter
# WISHLIST pluggable filters (test with UBL and cbc: => simpleType + UBL simple types mapping)


class OdooGenerator(DataclassGenerator):
    """Odoo generator."""

    def __init__(self, config: GeneratorConfig):
        if not os.environ.get("XSDATA_NO_PATCH"):
            # see the evil detail: https://github.com/tefra/xsdata/issues/666
            # for instance with this patch the Brazilian Invoicing nfe40_IPI
            # in Imposto class is a Many2one as expected
            MergeAttributes.process = PatchedMergeAttributes.process

        schema = os.environ.get("XSDATA_SCHEMA", "spec")
        version = os.environ.get("XSDATA_VERSION", "10")

        # if field prefix is not set via the config (default is "value")
        # then set it with SCHEMA and VERSION env vars
        if config.conventions.field_name.safe_prefix == "value":
            config.conventions.field_name.safe_prefix = f"{schema}{version}_"

        super().__init__(config)
        self.all_simple_types: List[Class] = []
        self.all_complex_types: List[Class] = []
        self.implicit_many2ones: Dict = defaultdict(list)
        tpl_dir = Path(__file__).parent.joinpath("templates")
        self.env = Environment(loader=FileSystemLoader(str(tpl_dir)), autoescape=False)
        self.filters = OdooFilters(
            config,
            self.all_simple_types,
            self.all_complex_types,
            self.implicit_many2ones,
            schema,
            version,
        )
        self.filters.register(self.env)

    def render(self, classes: List[Class]) -> Iterator[GeneratorResult]:
        """Return a iterator of the generated results."""
        packages = {obj.qname: obj.target_module for obj in classes}
        resolver = OdooDependenciesResolver(packages=packages)

        # Generate packages
        for path, cluster in self.group_by_package(classes).items():
            yield from self.ensure_packages(path.parent)

            def dfs(visited, graph, node):
                if node not in visited:
                    visited.append(node)
                    for neighbour in node.inner:  # in graph[node]:
                        dfs(visited, graph, neighbour)

            all_file_classes: List[Class] = []
            for c in cluster:
                dfs(all_file_classes, cluster, c)

            # collect relation dependencies from other files/includes:
            for klass in all_file_classes:
                if (
                    not self.filters.files_to_etree.get(klass.location)
                    and os.path.isfile(klass.location)
                ):
                    xsd_tree = etree.parse(klass.location)
                    self.filters.files_to_etree[klass.location] = xsd_tree

                if klass.is_enumeration and klass not in self.all_simple_types:
                    self.all_simple_types.append(
                        klass
                    )  # TODO add module name/path for import?
                elif klass not in self.all_complex_types:
                    for field in klass.attrs:
                        if not field.types[0].datatype and field.is_list:
                            type_names = collections.unique_sequence(
                                self.filters.field_type_name(x, []) for x in field.types
                            )
                            comodel = self.filters.registry_comodel(type_names)
                            target_field = self.filters.field_name(
                                f"{field.name}_{klass.name}_id",
                                klass.name,
                            )
                            self.implicit_many2ones[comodel].append(
                                (self.filters.registry_name(klass.name), target_field)
                            )

                    self.all_complex_types.append(klass)

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
            res = format_str(res, mode=FileMode())
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
