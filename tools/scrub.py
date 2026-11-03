"""
PII scrubber (TECH_SPEC §6). Standard library only. A byte-identical copy lives in Repo B
(ingest/vendor/scrub.py); change both together, by pull request only.

    scrub_text(text, private_terms) -> (text, findings)
    scrub_record(record, private_terms, free_text=FREE_TEXT_FIELDS) -> (record, findings)

Every match is replaced with [removed] (personal paths become <home>/, URLs keep only
scheme, host and path). scrub_record applies scrub_text to every string anywhere in a
record, then drops any adult free-text field that still holds more than 3 capitalised word
pairs not in tools/allowed_terms.txt (likely names of people or places).
"""
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

SCRUB_VERSION = "1.1"
REMOVED = "[removed]"
FREE_TEXT_FIELDS = {"answer_text", "note", "comment", "goals", "what_works"}
MAX_CAPITALISED_PAIRS = 3
ALLOWED_TERMS_FILE = Path(__file__).resolve().parent / "allowed_terms.txt"

_I = re.IGNORECASE
SECRETS = [
    ("private-key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)", re.S)),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}")),
    ("aws-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("github-token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("api-key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("slack-token", re.compile(r"\bxox[bapr]-[A-Za-z0-9-]+")),
    ("password", re.compile(r"(?<![A-Za-z])(?:password|passwd|pwd)\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|\S+)", _I)),
    ("token", re.compile(r"(?<![A-Za-z])(?:token|secret|api[_-]?key|access[_-]?key)\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|\S+)", _I)),
    ("bearer", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}")),
]
URL = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]{1,15}://[^\s\"'<>)\]]+")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
# Number detectors never start or end next to a letter, digit or hyphen, so identifiers such as
# UUIDs and learner ids (hex/alphanumeric runs) are never mistaken for cards, phones or Aadhaar.
CARD = re.compile(r"(?<![\w-])(?:\d[ -]?){12,18}\d(?![\w-])")
AADHAAR = re.compile(r"(?<![\w-])\d{4}\s?\d{4}\s?\d{4}(?![\w-])")
PHONE_INTL = re.compile(r"(?<![\w+])\+\d(?:[\s().-]{0,2}\d){9,14}(?!\d)")
PHONE_IN = re.compile(r"(?<![\w+-])(?:(?:91|0)[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?![\w-])")
PAN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
_OCTET = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
IPV4 = re.compile(rf"(?<![\d.]){_OCTET}(?:\.{_OCTET}){{3}}(?![\d.])")
_H = r"[0-9A-Fa-f]{1,4}"
IPV6 = re.compile(rf"(?<![\w:])(?:(?:{_H}:){{7}}{_H}|(?:{_H}(?::{_H})*)?::(?:{_H}(?::{_H})*)?)(?![\w:])")
HOME_PATHS = [
    re.compile(r"/home/[^/\s\"'`]+(?=/|\b)/?"),
    re.compile(r"/Users/[^/\s\"'`]+(?=/|\b)/?"),
    re.compile(r"[A-Za-z]:\\+Users\\+[^\\\s\"'`]+\\*", _I),
]
GIT_AUTHOR = re.compile(r"(?im)^(\s*(?:Author|Commit|Signed-off-by|Co-authored-by)\s*:).*$")
GIT_CONFIG = re.compile(r"\b(user\.(?:email|name))(\s*=?\s*)(\"[^\"]*\"|'[^']*'|\S+)")
CAPITALISED_PAIR = re.compile(r"\b([A-Z][a-zA-Z'’.-]*)\s+([A-Z][a-zA-Z'’.-]*)")


def _luhn(digits):
    total, alt = 0, False
    for d in reversed(digits):
        n = int(d)
        if alt:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
        alt = not alt
    return total % 10 == 0


def _clean_url(match, findings):
    url = match.group(0)
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
    except ValueError:
        findings.append("url")
        return REMOVED
    if "@" in parts.netloc or parts.query or parts.fragment:
        findings.append("url-secret")
        netloc = host + (f":{parts.port}" if parts.port else "")
        return urlunsplit((parts.scheme, netloc, parts.path, "", ""))
    return url


def _ipv6(match, findings):
    text = match.group(0)
    groups = [g for g in text.split(":") if g]
    if text.count(":") == 7 or len(groups) >= 3 or any(len(g) >= 3 for g in groups):
        findings.append("ip")
        return REMOVED
    return text  # e.g. a Python slice like a[1::2]


def scrub_text(text, private_terms=()):
    """Return (scrubbed text, list of what was found)."""
    if not isinstance(text, str) or not text:
        return text, []
    findings = []

    def sub(kind, pattern, s, repl=REMOVED):
        def r(m):
            findings.append(kind)
            return repl(m) if callable(repl) else repl
        return pattern.sub(r, s)

    s = text
    for kind, pattern in SECRETS:
        s = sub(kind, pattern, s)
    s = URL.sub(lambda m: _clean_url(m, findings), s)
    s = sub("email", EMAIL, s)
    s = GIT_AUTHOR.sub(lambda m: (findings.append("git-identity"), f"{m.group(1)} {REMOVED}")[1], s)
    s = GIT_CONFIG.sub(lambda m: (findings.append("git-identity"), f"{m.group(1)}{m.group(2)}{REMOVED}")[1], s)

    def card(m):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn(digits):
            findings.append("card")
            return REMOVED
        return m.group(0)
    s = CARD.sub(card, s)
    s = sub("aadhaar", AADHAAR, s)
    s = sub("phone", PHONE_INTL, s)
    s = sub("phone", PHONE_IN, s)
    s = sub("pan", PAN, s)
    s = sub("ip", IPV4, s)
    s = IPV6.sub(lambda m: _ipv6(m, findings), s)
    for pattern in HOME_PATHS:
        s = sub("home-path", pattern, s, "<home>/")
    for term in sorted({t.strip() for t in private_terms if isinstance(t, str) and t.strip()}, key=len, reverse=True):
        s = sub("private-term", re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", _I), s)
    return s, findings


def load_allowed_terms(path=ALLOWED_TERMS_FILE):
    words = set()
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                words.add(line.lower())
    except OSError:
        pass
    return words


def capitalised_pairs(text, allowed):
    """Count pairs of consecutive capitalised words that aren't both common terms."""
    count = 0
    for a, b in CAPITALISED_PAIR.findall(text or ""):
        a, b = a.strip(".'’-").lower(), b.strip(".'’-").lower()
        if a == REMOVED.strip("[]") or b == REMOVED.strip("[]"):
            continue
        if not (a in allowed and b in allowed) and f"{a} {b}" not in allowed:
            count += 1
    return count


def scrub_record(record, private_terms=(), free_text=FREE_TEXT_FIELDS, allowed=None):
    """Scrub every string in a record. Free-text fields with too many unknown capitalised word
    pairs are dropped (list items are removed). Returns (new record, findings)."""
    allowed = load_allowed_terms() if allowed is None else allowed
    findings = []

    def walk(value, key=None):
        if isinstance(value, str):
            out, found = scrub_text(value, private_terms)
            findings.extend(found)
            if key in free_text and capitalised_pairs(out, allowed) > MAX_CAPITALISED_PAIRS:
                findings.append("dropped-free-text")
                return _DROP
            return out
        if isinstance(value, dict):
            result = {}
            for k, v in value.items():
                new = walk(v, k)
                if new is not _DROP:
                    result[k] = new
            return result
        if isinstance(value, list):
            return [n for n in (walk(v, key) for v in value) if n is not _DROP]
        return value

    return walk(record), findings


_DROP = object()
