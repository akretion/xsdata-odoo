# Odoo Abstract Model Generator from XSD Schemas

[![codecov](https://codecov.io/gh/akretion/xsdata-odoo/branch/master/graph/badge.svg)](https://codecov.io/gh/akretion/xsdata-odoo)
[![PyPI pyversions](https://img.shields.io/pypi/pyversions/xsdata-odoo.svg)](https://pypi.org/pypi/xsdata-odoo/)
[![PyPI version](https://img.shields.io/pypi/v/xsdata-odoo.svg)](https://pypi.org/pypi/xsdata-odoo/)

Generate Odoo abstract models (mixins) from XSD schemas using
[xsdata](https://xsdata.readthedocs.io/). Heavily inspired by
[xsdata-plantuml](https://github.com/tefra/xsdata-plantuml).

**Video Tutorial:**
[YouTube - xsdata-odoo Overview](https://www.youtube.com/watch?v=6gFOe7Wh8uA)

---

## Table of Contents

- [Install](#install)
- [Quick Start](#quick-start)
- [Real-World Usage](#real-world-usage)
- [Architecture Pattern](#architecture-pattern)
- [Configuration](#configuration)
- [Advanced Examples](#advanced-examples)
- [Field Prefixing Strategy](#field-prefixing-strategy)
- [Custom Filters](#custom-filters)
- [Troubleshooting](#troubleshooting)

---

## Install

```console
$ pip install xsdata[cli]
$ pip install git+https://github.com/akretion/xsdata-odoo
```

---

## Quick Start

### Microsoft Purchase Order Demo

```console
$ xsdata generate tests/fixtures/po/po.xsd --output=odoo
Parsing schema po.xsd
Compiling schema po.xsd
Builder: 6 main and 1 inner classes
Analyzer input: 6 main and 1 inner classes
Analyzer output: 5 main and 1 inner classes
Generating package: generated.po
```

### Brazilian NF-e (Electronic Invoice)

```console
$ export XSDATA_SCHEMA=nfe
$ export XSDATA_VERSION=40
$ export XSDATA_SKIP="^ICMS.ICMS\d+|^ICMS.ICMSSN\d+"
$ export XSDATA_LANG="portuguese"

$ xsdata generate nfelib/nfe/schemas/v4_0 \
    --package nfelib.nfe.odoo.v4_0 \
    --output=odoo
```

---

## Real-World Usage

xsdata-odoo is used in production by the **OCA Brazilian Localization** (l10n-brazil) to
generate models for complex fiscal documents:

### Brazilian Electronic Fiscal Documents

| Document                          | Fields   | Model | Version | OCA Module          |
| --------------------------------- | -------- | ----- | ------- | ------------------- |
| **NF-e** (Nota Fiscal Eletrônica) | 800+     | 55/65 | 4.0     | `l10n_br_nfe_spec`  |
| **CT-e** (Transport Document)     | 1000+    | 57    | 4.0     | `l10n_br_cte_spec`  |
| **MDF-e** (Manifest)              | 500+     | 58    | 3.0     | `l10n_br_mdfe_spec` |
| **SPED** (Fiscal Reports)         | Variable | -     | -       | `l10n_br_sped_*`    |

- **NF-e**: 800+ fields across multiple hierarchical structures (identification, items,
  taxes, transport, payment)
- **CT-e**: Multiple transport modes (road, air, waterway, rail, pipeline, multimodal)
  with specific fields each
- **MDF-e**: Aggregation of multiple NF-e/CT-e documents with municipal grouping
- **SPED**: Complex register hierarchies with parent-child relationships

Integration with nfelib: xsdata-odoo generates **Odoo models**, while
[nfelib](https://github.com/akretion/nfelib) handles **XML serialization**. Both use the
same XSD schemas for consistency.

## Architecture Pattern

### Two-Layer Architecture

The OCA l10n-brazil uses a proven two-layer architecture:

#### 1. Spec Modules (`l10n_br_*_spec`)

- **100% generated** from XSD schemas
- Abstract models (mixins) with field definitions
- No business logic
- Versioned per schema version (nfe40, cte40, mdfe30)

#### 2. Implementation Modules (`l10n_br_nfe`, etc.)

- Inherits from spec modules
- Maps to Odoo fiscal documents (`l10n_br_fiscal.document`)
- Business rules and validations
- Web service communication (SEFAZ)
- User interface

### Benefits

- **Schema Updates**: Regenerate spec modules without touching business logic
- **Version Migration**: Different schema versions coexist (nfe40 vs nfe50)
- **Testing**: Business logic tested separately from generated code
- **Maintainability**: Clear separation of concerns

---

## Configuration

### Environment Variables

| Variable                | Description                             | Default          |
| ----------------------- | --------------------------------------- | ---------------- |
| `XSDATA_SCHEMA`         | Schema name                             | `spec`           |
| `XSDATA_VERSION`        | Schema version                          | `10`             |
| `XSDATA_SKIP`           | Regex patterns to skip (pipe-separated) | `[]`             |
| `XSDATA_LANG`           | Language for text processing            | `""`             |
| `XSDATA_MONETARY_TYPE`  | XSD type to force `fields.Monetary`     | `""`             |
| `XSDATA_NUM_TYPE`       | XSD type for numeric detection          | `TDec_[5:7.7:9]` |
| `XSDATA_CURRENCY_FIELD` | Currency field name                     | `currency_id`    |
| `XSDATA_GENDS`          | GenerateDS compatibility mode           | `false`          |

### Python API

```python
from xsdata_odoo import get_config

config = get_config()
print(config.schema)              # "spec"
print(config.version)             # "10"
print(config.field_safe_prefix)   # "spec10_"
print(config.inherit_model)       # "spec.mixin.spec"
```

---

## Advanced Examples

### Brazilian NF-e with ICMS Handling

The NF-e schema defines ICMS taxes with multiple groups (ICMS00, ICMS10, ICMS40, etc.)
that share field names. Skip them to avoid conflicts:

```bash
export XSDATA_SCHEMA=nfe
export XSDATA_VERSION=40
export XSDATA_SKIP="^ICMS.ICMS\d+|^ICMS.ICMSSN\d+"
export XSDATA_LANG="portuguese"
export XSDATA_CURRENCY_FIELD="brl_currency_id"

xsdata generate nfelib/nfe/schemas/v4_0 \
  --package nfelib.nfe.odoo.v4_0 \
  --output=odoo

# Move generated files to your module
mv nfelib/odoo/nfe/v4_0/* your_addon/models/v4_0/
```

### CT-e (Transport Document)

```bash
export XSDATA_SCHEMA=cte
export XSDATA_VERSION=40
export XSDATA_SKIP="^ICMS\d+|^ICMSSN+|ICMSOutraUF|ICMSUFFim|INFESPECIE_TPESPECIE"
export XSDATA_LANG="portuguese"

xsdata generate nfelib/cte/schemas/v4_0 \
  --package nfelib.cte.odoo.v4_0 \
  --output=odoo
```

### MDF-e (Manifest Document)

```bash
export XSDATA_SCHEMA=mdfe
export XSDATA_VERSION=30
export XSDATA_LANG="portuguese"

xsdata generate nfelib/mdfe/schemas/v3_0 \
  --package nfelib.mdfe.odoo.v3_0 \
  --output=odoo
```

### SPED Fiscal Reports (Advanced)

For complex non-XML fiscal reports with register hierarchies:

```python
from xsdata_odoo.generator import OdooGenerator
from xsdata_odoo.filters import OdooFilters

class SpedFilters(OdooFilters):
    def registry_name(self, name="", parents=[], type_names=[]):
        # Custom naming: schema.version.register_code
        name = self.class_name(name)
        return f"{self.schema}.{self.version}.{name[-4:].lower()}"

    def class_properties(self, obj, parents):
        # Add custom metadata
        register = lookup_register(obj.name)
        return f"_sped_level = {register['level']}"
```

---

## Field Prefixing Strategy

### Problem

With 800+ fields in NF-e alone, plus thousands of OCA modules, field name collisions are
a real risk. Additionally, schemas evolve (3.0 → 4.0 → 5.0).

### Solution

Each field gets a prefix combining **schema name** + **version digits**:

- NF-e v4.0: `nfe40_` prefix → `nfe40_vBC`, `nfe40_vICMS`
- CT-e v4.0: `cte40_` prefix → `cte40_vTPrest`
- MDF-e v3.0: `mdfe30_` prefix → `mdfe30_qNFe`

### Versioning Strategy

| Scenario                       | Example                    | Database Impact                                |
| ------------------------------ | -------------------------- | ---------------------------------------------- |
| **Minor update** (4.00 → 4.01) | Same `nfe40_` prefix       | Fields updated in place, `--update` sufficient |
| **Major update** (3.0 → 4.0)   | `nfe30_` → `nfe40_` prefix | New fields/tables, data migration needed       |

### Automatic Prefix Generation

```python
from xsdata_odoo import get_config

config = get_config()
config.schema = "nfe"
config.version = "40"

print(config.field_safe_prefix)  # "nfe40_"
```

---

## Custom Filters

Extend `OdooFilters` for specialized use cases:

```python
from xsdata_odoo.filters import OdooFilters
from collections import OrderedDict

class MyCustomFilters(OdooFilters):
    def registry_name(self, name="", parents=[], type_names=[]):
        # Custom model naming logic
        return f"my_module.{self.version}.{name.lower()}"

    def _extract_field_attributes(self, parents, attr):
        # Add custom field attributes
        kwargs = super()._extract_field_attributes(parents, attr)

        # Add custom metadata
        kwargs["my_custom_attr"] = True

        return kwargs

# Use custom filters
generator = OdooGenerator(config)
generator.filters = MyCustomFilters(
    config,
    all_simple_types=[],
    all_complex_types=[],
    registry_names={},
    implicit_many2ones={},
)
generator.filters.register(generator.env)
```

---

## Field Name Conflicts

**Problem**: XSD defines multiple groups with same field names (e.g., ICMS00.vBC,
ICMS10.vBC).

**Solution**: Use `XSDATA_SKIP` to skip conflicting classes:

```bash
export XSDATA_SKIP="^ICMS.ICMS\d+|^ICMS.ICMSSN\d+"
```

Then implement business logic in your implementation module to handle the different ICMS
groups.

## Currency Fields

**Problem**: Monetary fields reference non-existent currency field.

**Solution**: Set `XSDATA_CURRENCY_FIELD` to match your Odoo module's currency field:

```bash
export XSDATA_CURRENCY_FIELD="company_currency_id"  # or "currency_id", "brl_currency_id"
```

## Language-Specific Text Processing

**Problem**: Field labels not extracted properly from XSD documentation.

**Solution**: Set `XSDATA_LANG` for stopword processing:

```bash
export XSDATA_LANG="portuguese"  # or "english", "spanish", etc.
```

---

## Links

- [GitHub - xsdata-odoo](https://github.com/akretion/xsdata-odoo)
- [GitHub - nfelib](https://github.com/akretion/nfelib)
- [OCA l10n-brazil](https://github.com/OCA/l10n-brazil)
- [xsdata Documentation](https://xsdata.readthedocs.io/)

## License

MIT License - See [LICENSE](LICENSE) file for details

## Copyright

2025 Akretion - Raphaël Valyi <raphael.valyi@akretion.com>
