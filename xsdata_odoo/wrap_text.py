# taken from https://github.com/akretion/generateds-odoo
import textwrap
from typing import Tuple

STRING_MIN_LEN = 36
STRING_MAX_LEN = 64
PONCT_TOKENS = (". ", ", ", " (", "-", ",", ",")


def extract_string_and_help(
    obj_name: str, field_name: str, doc: str, unique_labels: set
) -> Tuple[str, str]:
    """
    Eventually field_name is technical and a better string/label can be
    extracted from the beginning of the help text.
    """

    string = field_name
    if doc:
        doc = doc.strip().replace('"', "")
        string = " ".join(doc.splitlines()[0].split())  # avoids double spaces

        for token in PONCT_TOKENS:
            if len(string) > STRING_MIN_LEN and len(string.split(token)[0]) < STRING_MAX_LEN:
                string = string.split(token)[0].strip()

        string = string.replace('"', "'")
        if string.endswith(":") or string.endswith("."):
            string = string[:-1]

        if len(string) > 58:
            string = field_name.split("_")[-1]

        if string == doc or doc[:-1] == string:  # doc might end with '.'
            doc = None

    if string in unique_labels:
        string = f"{string} ({field_name})"
        if len(string) > 58:
            string = field_name.split("_")[-1]
    unique_labels.add(string)

    return string, doc


def wrap_text(
    text,
    indent,
    width=79,
    initial_indent=4,
    multi=False,
    preserve_line_breaks=True,
    quote=True,
):
    text = text.strip()
    if not multi:
        if not quote:
            quote = ""
        elif len(text) + initial_indent + 8 > width or "\n" in text or '"' in text:
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
    else:
        width -= 3

    wrapped_lines = []
    first = True
    for l in text.splitlines():
        if first:
            w = width - initial_indent
            first = False
        else:
            if multi:
                w = width - indent
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

    if not multi:
        return text
    else:
        lines = ['"{}"'.format(i.strip().replace('"', "'")) for i in text.splitlines()]
        lines2 = []
        c = 0
        for l in lines:
            if preserve_line_breaks:
                if c != 0:
                    l = '"\\n{}'.format(l[1:100])
            elif c != len(lines) - 1:
                l = '%s "' % (l[0:-1])
            c += 1
            lines2.append(l)
        text = ("\n{}".format(" " * indent)).join(lines2)
        if "\n" in text:
            text = f"{text}"
        return text
