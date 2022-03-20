from pathlib import Path
from typing import Iterator
from typing import List

from jinja2 import Environment
from jinja2 import FileSystemLoader
from xsdata.codegen.models import Class
from xsdata.formats.dataclass.generator import DataclassGenerator
from xsdata.formats.mixins import GeneratorResult
from xsdata.models.config import GeneratorConfig

from .filters import OdooFilters
from .codegen.resolver import OdooDependenciesResolver


# TODO why is nfe40_IPI in Imposto class a One2many. Should be Many2one. May be because of <xs:element name="IPI" type="TIpi" minOccurs="0"/>
# for now it works thanks to my patch https://github.com/tefra/xsdata/pull/667
# TODO Enum labels
# TODO FIX nfe40_protNFe field in TnfeProc class
# TODO base model as a filter
# pluggable filters (test with UBL and cbc: => simpleType + UBL simple types mapping)
# TODO define m2o of the o2m fields. see #1 of https://github.com/akretion/generateds-odoo/issues/10
# in fact it seems what we do sort of work but we can have only 1 o2m to a given class in a class
# and also it the keys changed compared to generateDS and we also need to write the key in the o2m.


class OdooGenerator(DataclassGenerator):
    """Odoo generator."""

    def __init__(self, config: GeneratorConfig):
        super().__init__(config)
        self.all_simple_types: List[Class] = []
        self.all_complex_types: List[Class] = []
        tpl_dir = Path(__file__).parent.joinpath("templates")
        self.env = Environment(loader=FileSystemLoader(str(tpl_dir)), autoescape=False)
        self.filters = OdooFilters(
            config, self.all_simple_types, self.all_complex_types
        )
        self.filters.register(self.env)

    def render(self, classes: List[Class]) -> Iterator[GeneratorResult]:
        """Return a iterator of the generated results."""
        packages = {obj.qname: obj.target_module for obj in classes}
        resolver = OdooDependenciesResolver(packages=packages)

        # Generate packages
        for path, cluster in self.group_by_package(classes).items():
            module = ".".join(path.relative_to(Path.cwd()).parts)
            yield from self.ensure_packages(path.parent)

        # Generate modules
        for path, cluster in self.group_by_module(classes).items():

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

                if klass.is_enumeration and klass not in self.all_simple_types:
                    self.all_simple_types.append(
                        klass
                    )  # TODO add module name/path for import?
                elif (
                    klass not in self.all_complex_types
                ):  # FIXME uselss cause hierarchy
                    self.all_complex_types.append(klass)

                # TODO would be an option to repeat missing types from included xsd files
                # instead of using imports, specially for simple_types.
                # activating this crashes the title=cluster[0].target_module (file_name)
                # and it also conflicts with the initial import statements
                # for attr in klass.attrs:
                #     if attr.types and not attr.types[0].datatype:
                #         if attr.types[0].qname not in [k.qname for k in all_file_classes]:
                #             for k in self.all_simple_types:
                #                 if (attr.types[0].qname == k.qname) and (k.qname not in [k.qname for k in cluster]):
                #                     pass
                #                     # TODO FIXME
                #                     #cluster.append(k)
                #             for k in self.all_complex_types:
                #                 if (attr.types[0].qname == k.qname) and (k.qname not in [k.qname for k in cluster]):
                #                     pass
                #                     # TODO FIMXE
                #                     #cluster.append(k)

            yield GeneratorResult(
                path=path.with_suffix(".py"),
                title=cluster[0].target_module,
                source=self.render_module(resolver, cluster),
            )
