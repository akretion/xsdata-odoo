import locale
import os
import textwrap
from typing import Tuple

import babel
from nltk import download
from nltk.corpus import stopwords

# where to stop when trying to extract the beginning of a text
STRONG_PONCT_TOKENS = (". ", ", ", " (", " - ", ".", ",", ": ", "|")
STRING_MIN_LEN = 36  # agressive cuts
STRING_MAX_LEN = 40  # progressive cuts

USELESS_STARTS = ("Informar o ", "Informar a ", "Preencher com ")


def extract_string_and_help(
    obj_name: str,
    attr_name: str,
    doc: str,
    unique_labels: set,
    max_len: int = STRING_MAX_LEN,
) -> Tuple[str, str]:
    """
    Try to extract a proper field string from any (xsd) longest field documentation.
    Eventually attr_name is technical and a better string/label can be
    extracted from the beginning of the help text.
    Giving good results 95% of the time is fine because one can override
    in Odoo fields in the 5% of cases where the extracted string isn't nice.
    Labels duplicates are avoided using the unique_labels set param and by
    appending the field name in the description eventually if required.
    """

    string = attr_name
    if doc:
        if "Tomador do Serviço" in doc and "Preencher com" in doc:
            # FIXME hack for Brazilian CTe:
            doc = doc.strip().replace('"', "'").replace("\\", "/").replace("\t", " ")
        else:
            doc = doc.strip().replace('"', "'")
        string, doc = _aggressive_cut(doc)
        string = _progressive_cut(string, max_len)

        if "(" in string and ")" not in string:
            string = string.split("(")[0].strip()
        if len(string) > max_len:
            string = attr_name

        if string == doc or doc[:-1] == string:  # doc might end with '.'
            doc = ""

    if string in unique_labels:
        string = f"{string} ({attr_name})"
        if len(string) > max_len:
            string = attr_name

    unique_labels.add(string)
    return string, doc


def _aggressive_cut(doc):
    """
    Use ponctuation to cut the string.
    Remove non relevant starting strings from a field string.
    non relevant starting strings can be forced through the USELESS_STARTS env var.
    """

    def remove_after(string, token):
        return token.join(string.split(token)[:-1])

    if os.environ.get("USLESS_STARTS"):
        useless_starts = tuple(os.environ["USELESS_STARTS"].split("|"))
    else:
        useless_starts = USELESS_STARTS  # a good default for us in Brazil
    for start in useless_starts:
        if doc.lower().startswith(start.lower()):
            doc = doc[len(start) :]

    string = " ".join(doc.splitlines()[0].split())  # avoid double spaces

    for token in STRONG_PONCT_TOKENS:  # cut aggressively
        while token in string:
            if len(string) > STRING_MIN_LEN:
                string = remove_after(string, token)
            else:
                break

    return string, doc


def _progressive_cut(string, max_len):
    """
    Try to cut the field string progressively using language specific stopwords.
    language is detected with locale.getdefaultlocale() but can be forced
    through the LANGUAGE ENV var. This will work well for some languages like
    Latin languages. For some other languages (German?), may be customization
    would be required.
    """
    if os.environ.get("XSDATA_LANG"):
        lang = os.environ["XSDATA_LANG"]
    else:
        os_locale = locale.getdefaultlocale()
        lang = (
            babel.Locale.parse(os_locale[0])
            .get_display_name("en")
            .split("(")[0]
            .lower()
            .strip()
        )
    try:
        lang_stopwords = stopwords.words(lang)
    except LookupError:
        download("stopwords")
        lang_stopwords = stopwords.words(lang)

    while len(string) > max_len:
        max_index = 0
        max_token = None
        for stopword in lang_stopwords:  # cut progressively
            token = f" {stopword} "
            if token in string and string.rindex(token) > max_index:
                max_index = string.rindex(token)
                max_token = token
        if max_token:
            string = max_token.join(string.split(max_token)[:-1])
        else:
            break

    should_try_cut = True
    while should_try_cut:
        for token in STRONG_PONCT_TOKENS + tuple(
            [f" {w} " for w in stopwords.words(lang)]
        ):
            if string.endswith(token.rstrip()):
                string = string[: string.rindex(token.rstrip())]
                should_try_cut = True
                break
            else:
                should_try_cut = False

    return string


def wrap_text(
    text,
    indent,
    width=88,
    initial_indent=4,
):
    text = text.strip()
    if len(text) + initial_indent + 8 > width or "\n" in text or '"' in text:
        quote = '"""'
    else:
        quote = '"'
    if text[0] == '"':
        text = f"{quote} {text}"
    else:
        text = f"{quote}{text}"
    if text[-1] == '"':
        text = f"{text} {quote}"
    else:
        text = f"{text}{quote}"

    wrapped_lines = []
    first = True
    for line in text.splitlines():
        if first:
            w = width - initial_indent
            first = False
        else:
            w = width
        lines = textwrap.fill(
            " ".join(line.strip().split()),
            width=w,
            subsequent_indent=" " * indent,
            replace_whitespace=False,
        ).splitlines()
        wrapped_lines += [i.strip() for i in lines]
    text = ("\n" + " " * indent).join(wrapped_lines)

    return text
