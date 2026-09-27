import re
TOKEN = re.compile(r'\$[A-Z][A-Z0-9_]*|#[A-Z][A-Z0-9_]*|(?<!<)</?[^<>]+>(?!>)|%(?:\d+\$)?[-+0 #]*\d*(?:\.\d+)?[sdifu](?![A-Za-z])|\\[nrt]')
