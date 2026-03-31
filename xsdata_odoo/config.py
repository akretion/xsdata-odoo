"""Configuration management for xsdata-odoo."""

import os
from dataclasses import dataclass, field


@dataclass
class OdooGeneratorConfig:
    """Configuration for the Odoo code generator.

    All settings can be customized via environment variables.

    Example:
        export XSDATA_SCHEMA=nfe
        export XSDATA_VERSION=40
        export XSDATA_SKIP="^ICMS.ICMS\d+|^ICMS.ICMSSN\d+"
        export XSDATA_LANG=portuguese
        export XSDATA_CURRENCY_FIELD=brl_currency_id
    """

    # Schema identification
    schema: str = field(default_factory=lambda: os.environ.get("XSDATA_SCHEMA", "spec"))
    version: str = field(default_factory=lambda: os.environ.get("XSDATA_VERSION", "10"))

    # Pattern filtering (pipe-separated regex patterns)
    skip_patterns: list[str] = field(default_factory=list)

    # Text processing
    language: str = field(default_factory=lambda: os.environ.get("XSDATA_LANG", ""))

    # Field type detection
    monetary_type: str = field(
        default_factory=lambda: os.environ.get("XSDATA_MONETARY_TYPE", "")
    )
    num_type: str = field(
        default_factory=lambda: os.environ.get("XSDATA_NUM_TYPE", "TDec_[5:7.7:9]")
    )
    currency_field: str = field(
        default_factory=lambda: os.environ.get("XSDATA_CURRENCY_FIELD", "currency_id")
    )

    # Backward compatibility
    gends_mode: bool = field(
        default_factory=lambda: os.environ.get("XSDATA_GENDS", "").lower()
        in ("1", "true", "yes")
    )

    def __post_init__(self):
        """Parse skip patterns from environment variable."""
        skip_env = os.environ.get("XSDATA_SKIP", "")
        if skip_env:
            self.skip_patterns = [p.strip() for p in skip_env.split("|") if p.strip()]

    @property
    def field_safe_prefix(self) -> str:
        """Generate field prefix from schema and version."""
        return f"{self.schema}{self.version}_"

    @property
    def inherit_model(self) -> str:
        """Generate inherit model name."""
        return f"spec.mixin.{self.schema}"


# Global configuration instance
_config: OdooGeneratorConfig | None = None


def get_config() -> OdooGeneratorConfig:
    """Get or create global configuration instance.

    Returns:
        OdooGeneratorConfig: The global configuration instance.
    """
    global _config
    if _config is None:
        _config = OdooGeneratorConfig()
    return _config


def reset_config() -> None:
    """Reset the global configuration instance.

    Useful for testing or when environment variables change.
    """
    global _config
    _config = None
