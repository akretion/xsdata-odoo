import os

from typing import List

from xsdata.codegen.mixins import HandlerInterface
from xsdata.codegen.models import Attr
from xsdata.codegen.models import Class
from xsdata.codegen.utils import ClassUtils
from xsdata.utils import collections

from xsdata.codegen.writer import CodeWriter
from xsdata.codegen.handlers.merge_attributes import MergeAttributes

from xsdata_odoo.generator import OdooGenerator


@classmethod
def process(cls, target: Class):
    """
    Detect same type attributes in order to merge them together with their
    restrictions.

    Two attributes are considered equal if they have the same name,
    tag and namespace.
    """
    result: List[Attr] = []
    for attr in target.attrs:
        pos = collections.find(result, attr)
        existing = result[pos] if pos > -1 else None

        if not existing:
            result.append(attr)
        elif not (attr.is_attribute or attr.is_enumeration):
            existing.help = existing.help or attr.help

            e_res = existing.restrictions
            a_res = attr.restrictions

            min_occurs = e_res.min_occurs or 0
            max_occurs = e_res.max_occurs or 1
            attr_min_occurs = a_res.min_occurs or 0
            attr_max_occurs = a_res.max_occurs or 1

            e_res.min_occurs = min(min_occurs, attr_min_occurs)
            e_res.max_occurs = min(max_occurs, attr_max_occurs)  # this is the patch
            e_res.sequential = a_res.sequential or e_res.sequential
            existing.fixed = False
            existing.types.extend(attr.types)

    target.attrs = result
    ClassUtils.cleanup_class(target)


@classmethod
def merge_duplicate_attrs(self, target: Class):
    result: List[Attr] = []
    for attr in target.attrs:
        pos = collections.find(result, attr)
        existing = result[pos] if pos > -1 else None

        if not existing:
            result.append(attr)
        elif not (attr.is_attribute or attr.is_enumeration):
            existing.help = existing.help or attr.help

            e_res = existing.restrictions
            a_res = attr.restrictions

            min_occurs = e_res.min_occurs or 0
            max_occurs = e_res.max_occurs or 1
            attr_min_occurs = a_res.min_occurs or 0
            attr_max_occurs = a_res.max_occurs or 1

            e_res.min_occurs = min(min_occurs, attr_min_occurs)
            e_res.max_occurs = min(max_occurs, attr_max_occurs)  # this is the patch

            if a_res.sequence is not None:
                e_res.sequence = a_res.sequence

            existing.fixed = False
            existing.types.extend(attr.types)

    target.attrs = result
    ClassUtils.cleanup_class(target)


if os.environ.get("XSDATA_SCHEMA") in ("nfe",):
    # workaround for the Brazilian NFe https://github.com/akretion/nfelib/issues/40
    # another option would be to use the --compound-fields option but that would
    # force us to rework a bit the spec_driven_model module logic a bit.
    # see https://github.com/akretion/nfelib/issues/40
    if hasattr(MergeAttributes, "merge_duplicate_attrs"):
        # xsdata > 22.12
        merge_duplicate_attrs._original_method = MergeAttributes.merge_duplicate_attrs
        MergeAttributes.merge_duplicate_attrs = merge_duplicate_attrs
    else:
        process._original_method = MergeAttributes.process
        MergeAttributes.process = process


CodeWriter.register_generator("odoo", OdooGenerator)
