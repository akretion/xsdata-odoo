"""Constants for xsdata-odoo."""

# XML Schema namespace
XSD_NS = "http://www.w3.org/2001/XMLSchema"
XSD_NS_BRACE = "{http://www.w3.org/2001/XMLSchema}"

# Namespace prefixes used in XPath queries
XSD_NSMAP = {
    "xs": XSD_NS,
    "xsd": XSD_NS,
}

# XSD element tags
XSD_ANNOTATION_TAG = f"{XSD_NS_BRACE}annotation"
XSD_SEQUENCE_TAG = f"{XSD_NS_BRACE}sequence"
XSD_CHOICE_TAG = f"{XSD_NS_BRACE}choice"

# Line length limits (matching OCA style)
OCA_LINE_LENGTH = 88
