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
from wrap_text import wrap_text
from xsdata.codegen.models import Attr
from xsdata.codegen.models import Class
from xsdata.codegen.resolver import DependenciesResolver
from xsdata.formats.mixins import AbstractGenerator
from xsdata.formats.mixins import GeneratorResult
from xsdata.models.config import GeneratorConfig
from xsdata.utils import text

# from typing import Dict
# from typing import Iterable
# from typing import List
# from typing import Tuple
# from typing import Type


class OdooGenerator(AbstractGenerator):
    """Odoo generator."""

    def __init__(self, config: GeneratorConfig):
        super().__init__(config)
        tpl_dir = Path(__file__).parent.joinpath("templates")
        self.env = Environment(loader=FileSystemLoader(str(tpl_dir)), autoescape=False)
        self.env.filters.update(
            {
                "class_name": self.class_name,
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
        classes = sorted(classes, key=lambda x: x.name)
        # TODO filter signature classes like generateds_odoo

        def render_class(obj: Class) -> str:
            """Render class or enumeration."""
            template = "enum.jinja2" if obj.is_enumeration else "class.jinja2"
            return load(template).render(obj=obj).strip()

        output = "\n\n".join(map(render_class, classes))
        return f"\n{output}\n"

    # jinja2 filters:

    def class_name(self, name: str) -> str:
        """Convert the given string to a class name according to the selected
        conventions or use an existing alias."""
        # print(name, self.class_safe_prefix, self.class_case)
        return self.safe_name(name, self.class_safe_prefix, self.class_case)

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
        return "    {}".format(wrap_text(cls.__doc__, 4, 79))

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
        print(parents)
        return ".".join([self.class_name(p) for p in parents])

    def field_definition(
        self,
        attr: Attr,
        parents: List[str],
    ) -> str:
        """Return the field definition with any extra metadata."""
        return ""
        # default_value = self.field_default_value(attr, ns_map)
        # metadata = self.field_metadata(attr, parent_namespace, parents)

        # kwargs: Dict[str, Any] = {}
        # if attr.fixed:
        #     kwargs["init"] = False

        # if default_value is not False:
        #     key = self.FACTORY_KEY if attr.is_factory else self.DEFAULT_KEY
        #     kwargs[key] = default_value

        # if metadata:
        #     kwargs["metadata"] = metadata

        # return f"field({self.format_arguments(kwargs, 4)})"

    def field_name(self, name: str) -> str:
        """
        field_name with schema and version prefix.

        we could have used a 'safe_name' like xsdata does for the Python
        bindings. But having this prefix it's already safe. It's also
        backward compatible with the models we generated with
        GenerateDS. And finally it's good to use some digits of the
        schema version in the field prefix, so minor schema updates are
        mapped to the same Odoo fields and --update should take care of
        it while major schema updates get different fields and possibly
        different classes/tables.
        """
        schema = os.environ.get("SCHEMA", "")
        if schema:
            version = os.environ.get("VERSION", "")
            field_prefix = f"{schema}{version}_"
        else:
            field_prefix = ""
        return f"{field_prefix}{name}"

    def safe_name(
        self, name: str, prefix: str, name_case: Callable, **kwargs: Any
    ) -> str:
        """
        Sanitize names for safe generation.

        copied from xsdata/formats/dataclass/filters.py
        """
        if not name:
            return self.safe_name(prefix, prefix, name_case, **kwargs)

        if re.match(r"^-\d*\.?\d+$", name):
            return self.safe_name(f"{prefix}_minus_{name}", prefix, name_case, **kwargs)

        slug = text.alnum(name)
        print("\nslug", name, slug)
        if not slug or not slug[0].isalpha():
            return self.safe_name(f"{prefix}_{name}", prefix, name_case, **kwargs)

        result = name_case(name, **kwargs)
        print("name_case", result, name_case, kwargs)
        if text.is_reserved(result):
            return self.safe_name(f"{name}_{prefix}", prefix, name_case, **kwargs)

        return result
