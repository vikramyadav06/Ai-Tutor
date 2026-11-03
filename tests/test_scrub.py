"""TECH_SPEC §6: at least 60 PII samples that must be removed and 30 normal samples that
must survive unchanged. Repo B runs the same tests on its vendored copy."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import scrub  # noqa: E402

PRIVATE_TERMS = ["Ravi Kumar", "Ravi", "Sunrise Public School", "Acme Logistics", "Bandra", "Mrs Iyer", "Pinky"]

# (text, the secret part that must be gone)
PII = [
    # emails
    ("mail me at ravi.k@example.com please", "ravi.k@example.com"),
    ("Contact: priya_sharma+tests@gmail.co.in", "priya_sharma+tests@gmail.co.in"),
    ("email=ANITA.DSOUZA@Company.org", "ANITA.DSOUZA@Company.org"),
    ("<john.doe@sub.mail.example.net>", "john.doe@sub.mail.example.net"),
    ("send to x@y.io", "x@y.io"),
    # phones
    ("call +91 98765 43210 after 6", "98765 43210"),
    ("my number is 9876543210", "9876543210"),
    ("ph: 098765-43210", "98765-43210"),
    ("+1 (415) 555-0132 is the office", "555-0132"),
    ("+44 20 7946 0958", "7946 0958"),
    ("WhatsApp 7012345678 anytime", "7012345678"),
    ("+91-80-4123-4567", "4123-4567"),
    # Aadhaar
    ("aadhaar 2345 6789 0123", "2345 6789 0123"),
    ("UID 234567890123 on the form", "234567890123"),
    ("my id: 9999 8888 7777", "9999 8888 7777"),
    # PAN
    ("PAN ABCDE1234F", "ABCDE1234F"),
    ("pan card no. BNZPM2501F", "BNZPM2501F"),
    # cards (Luhn-valid test numbers)
    ("card 4111 1111 1111 1111 exp 12/29", "4111 1111 1111 1111"),
    ("5500-0000-0000-0004", "5500-0000-0000-0004"),
    ("amex 378282246310005", "378282246310005"),
    ("visa 4012888888881881", "4012888888881881"),
    # IP addresses
    ("server at 192.168.1.23 is down", "192.168.1.23"),
    ("ssh 10.0.0.5", "10.0.0.5"),
    ("my ip is 203.0.113.77", "203.0.113.77"),
    ("ipv6 2001:db8:85a3::8a2e:370:7334 here", "2001:db8:85a3::8a2e:370:7334"),
    ("link-local fe80::1ff:fe23:4567:890a", "fe80::1ff:fe23:4567:890a"),
    # secrets
    ("aws AKIAIOSFODNN7EXAMPLE leaked", "AKIAIOSFODNN7EXAMPLE"),
    ("token ghp_" + "a" * 36, "ghp_" + "a" * 36),
    ("gho_" + "B1" * 20 + " in env", "gho_" + "B1" * 20),
    ("OPENAI sk-proj" + "x" * 30, "sk-proj" + "x" * 30),
    ("slack xoxb-1234-5678-abcdef", "xoxb-1234-5678-abcdef"),
    ("password: hunter2", "hunter2"),
    ('PASSWORD = "S3cr3t!"', "S3cr3t!"),
    ("db_password=letmein123", "letmein123"),
    ("token: abc123def456", "abc123def456"),
    ("api_key = 'zzzzzzzz'", "zzzzzzzz"),
    ("auth eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NSJ9.SflKxwRJSMeKKF2QT4fw", "SflKxwRJSMeKKF2QT4fw"),
    ("-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA\n-----END RSA PRIVATE KEY-----", "MIIEpAIBAAKCAQEA"),
    ("-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXk\n-----END OPENSSH PRIVATE KEY-----", "b3BlbnNzaC1rZXk"),
    ("Authorization: Bearer abcdefghijklmnop1234", "abcdefghijklmnop1234"),
    # URLs with secrets
    ("https://user:pa55@example.com/repo.git", "pa55"),
    ("https://example.com/reset?token=Zm9vYmFy&id=7", "Zm9vYmFy"),
    ("see http://intranet.example.org/page#session=abc", "session=abc"),
    ("https://ravi@github.com/x/y", "ravi@"),
    # personal paths
    ("File \"/home/ravik/projects/test_login.py\", line 3", "ravik"),
    ("/Users/priya.s/Desktop/work/test_a.py failed", "priya.s"),
    (r"C:\Users\AnitaD\Documents\tests\test_x.py", "AnitaD"),
    ("cd /home/john", "john"),
    # git identity
    ("Author: Ravi Kumar <ravi@example.com>", "ravi@example.com"),
    ("git config user.email anita@corp.example", "anita@corp.example"),
    ('git config --global user.name "Priya Sharma"', "Priya Sharma"),
    ("Signed-off-by: Sam Lee <sam@lee.dev>", "Sam Lee"),
    # private terms (from learner/private_terms.json)
    ("I'm Ravi and I study at Sunrise Public School", "Ravi"),
    ("I'm Ravi and I study at Sunrise Public School", "Sunrise Public School"),
    ("I work at acme logistics in QA", "acme logistics"),
    ("we live near bandra station", "bandra"),
    ("Mrs Iyer explained this well", "Mrs Iyer"),
    ("pinky's answer", "pinky"),
    ("RAVI KUMAR wrote this", "RAVI KUMAR"),
    ("Thanks, Ravi.", "Ravi"),
]

# must come out exactly as they went in
NORMAL = [
    'page.goto("https://www.saucedemo.com")',
    'expect(page).to_have_url("https://www.saucedemo.com/inventory.html")',
    "page.get_by_role('button', name='Login').click()",
    "page.fill('#password', value)",
    "def test_login(page: Page):",
    "assert len(items) == 6",
    "x = a[1::2]",
    "for i in range(10): print(i)",
    "pytest my-work/setup -v --headed",
    "Water boils at 100 °C at sea level.",
    "6CO2 + 6H2O → C6H12O6 + 6O2",
    "F = m × a, so a = 20 N / 4 kg = 5 m/s²",
    "The speed of light is about 3 × 10^8 m/s.",
    "Avogadro's number is 6.022 × 10^23 per mole.",
    "Homo sapiens and Escherichia coli are scientific names.",
    "Newton's second law links force and acceleration.",
    "Solve: 2x + 3 = 11, so x = 4.",
    "The area of a circle is πr².",
    "Mitochondria are the powerhouse of the cell.",
    "Python 3.12 and pytest 8.3 work together.",
    "Chapter 7: Motion, page 112.",
    "The year 1947 and the year 2024.",
    "Locator strategies: get_by_role, get_by_label, get_by_text.",
    "HTTP status 404 means not found; 500 is a server error.",
    "Use git commit -m 'message' to save work.",
    "Score: 18/20 on the quiz, 90%.",
    "std::cout << value;",
    "SELECT name FROM products WHERE price > 100;",
    "The CBSE board exam is in March.",
    "pH of pure water is 7 at 25 °C.",
]


def test_sample_counts():
    assert len(PII) >= 60 and len(NORMAL) >= 30


@pytest.mark.parametrize("text,secret", PII)
def test_pii_is_removed(text, secret):
    out, findings = scrub.scrub_text(text, PRIVATE_TERMS)
    assert secret.lower() not in out.lower(), out
    assert findings


@pytest.mark.parametrize("text", NORMAL)
def test_normal_text_survives(text):
    out, findings = scrub.scrub_text(text, PRIVATE_TERMS)
    assert out == text and findings == []


def test_urls_keep_scheme_host_path():
    out, _ = scrub.scrub_text("https://user:pw@example.com:8443/a/b?x=1#y", [])
    assert out == "https://example.com:8443/a/b"


def test_home_paths_become_home():
    out, _ = scrub.scrub_text("/home/ravik/projects/a.py", [])
    assert out == "<home>/projects/a.py"


def test_private_terms_are_whole_word_and_case_insensitive():
    out, _ = scrub.scrub_text("Ravindra met ravi", ["Ravi"])
    assert out == "Ravindra met [removed]"


def test_free_text_with_many_names_is_dropped():
    allowed = scrub.load_allowed_terms()
    record = {"goals": ["Pass my Physics exam", "Meet Rahul Verma, Sneha Kapoor, Arjun Rao and Divya Nair at Hill Park"],
              "steps": [{"answer_text": "Newton's First Law says a body stays at rest"}]}
    out, findings = scrub.scrub_record(record, [], allowed=allowed)
    assert out["goals"] == ["Pass my Physics exam"]
    assert out["steps"][0]["answer_text"] == "Newton's First Law says a body stays at rest"
    assert "dropped-free-text" in findings


def test_scrub_record_reaches_every_string():
    record = {"a": {"b": ["mail ravi@x.com"]}, "subject": "ravi", "n": 3}
    out, _ = scrub.scrub_record(record, ["ravi"], allowed=set())
    assert out == {"a": {"b": ["mail [removed]"]}, "subject": "[removed]", "n": 3}


def test_version():
    assert scrub.SCRUB_VERSION.split(".")[0] == "1"
