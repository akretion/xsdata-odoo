from typing import List
from xsdata.codegen.models import Class
from xsdata.codegen.resolver import DependenciesResolver


class OdooDependenciesResolver(DependenciesResolver):

    def sorted_classes(self) -> List[Class]:
        """Sorted: Enumerations 1st"""

        result = []
        for name in sorted(self.class_list, key=lambda x: (self.class_map.get(x) is not None and not self.class_map.get(x).is_enumeration)):
            obj = self.class_map.get(name)
            if obj is not None:
                self.apply_aliases(obj)
                result.append(obj)
        return result
