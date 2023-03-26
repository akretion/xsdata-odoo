import textwrap
from typing import Tuple

# where to stop when trying to extract the beginning of a text
STRONG_PONCT_TOKENS = (". ", ", ", " (", " - ", ".", ",", ": ", "|")

# adpositions separator
# works for Brazilian fiscal documents, you may need to adapt for your language
PONCT_TOKENS = (
    " e ",
    " da ",
    " do ",
    " de ",
    " na ",
    " no ",
    " nas ",
    " nos ",
    " ou ",
    " que ",
    " em ",
    " para ",
)

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
    """Eventually attr_name is technical and a better string/label can be
    extracted from the beginning of the help text."""

    def remove_after(string, token):
        return token.join(string.split(token)[:-1])

    string = attr_name
    if doc:
        doc = doc.strip().replace('"', "'")
        for start in USELESS_STARTS:
            if doc.lower().startswith(start.lower()):
                doc = doc[len(start) :]

        string = " ".join(doc.splitlines()[0].split())  # avoids double spaces

        for token in STRONG_PONCT_TOKENS:  # cut aggressively
            while token in string:
                if len(string) > STRING_MIN_LEN:
                    string = remove_after(string, token)
                else:
                    break

        while len(string) > max_len:
            max_index = 0
            max_token = None
            for token in PONCT_TOKENS:  # cut progressively
                if token in string and string.rindex(token) > max_index:
                    max_index = string.rindex(token)
                    max_token = token
            if max_token:
                string = remove_after(string, max_token)
            else:
                break

        for token in PONCT_TOKENS + STRONG_PONCT_TOKENS:
            if string.endswith(token.rstrip()):
                string = string[: string.rindex(token.rstrip())]

        if "(" in string and not ")" in string:
            string = string.split("(")[0].strip()
        if len(string) > max_len:
            string = attr_name

        if string == doc or doc[:-1] == string:  # doc might end with '.'
            doc = None

    if string in unique_labels:
        string = f"{string} ({attr_name})"
        if len(string) > max_len:
            string = attr_name

    unique_labels.add(string)

    return string, doc


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
    for l in text.splitlines():
        if first:
            w = width - initial_indent
            first = False
        else:
            w = width
        lines = textwrap.fill(
            " ".join(l.strip().split()),
            width=w,
            subsequent_indent=" " * indent,
            replace_whitespace=False,
        ).splitlines()
        wrapped_lines += [i.strip() for i in lines]
    text = ("\n" + " " * indent).join(wrapped_lines)

    return text
