#!/usr/bin/env python3
"""
OWNER ONLY. Generate the collector key pair for Repo B.

Run this yourself in a terminal (not through an AI agent):

    pip install pynacl==1.5.0
    python tools/owner/generate_keys.py k1

It prints the PUBLIC key (safe to share; goes into project.json) and writes the PRIVATE key to
collector_private_<key_id>.txt next to where you run it, readable only by you. Then:

    gh secret set COLLECTOR_PRIVATE_KEY_K1 --repo vikramyadav06/Ai-Tutor-Platform < collector_private_k1.txt
    # then delete the file securely:
    #   macOS/Linux: rm -P collector_private_k1.txt   (or shred -u)
    #   Windows:     del collector_private_k1.txt

It also creates ACCOUNT_HASH_KEY the first time (k1 only) in account_hash_key.txt:

    gh secret set ACCOUNT_HASH_KEY --repo vikramyadav06/Ai-Tutor-Platform < account_hash_key.txt

Never commit these files, paste them into a chat, or share them with an AI agent.
"""
import base64
import os
import re
import secrets
import sys
from pathlib import Path


def write_private(path: Path, text: str) -> None:
    if path.exists():
        sys.exit(f"{path} already exists. Move or delete it first; refusing to overwrite a key.")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text + "\n")


def main() -> None:
    try:
        from nacl.public import PrivateKey
    except ImportError:
        sys.exit("PyNaCl is missing. Run: pip install pynacl==1.5.0")

    key_id = sys.argv[1] if len(sys.argv) > 1 else "k1"
    if not re.fullmatch(r"k\d+", key_id):
        sys.exit("Key id must look like k1, k2, ...")

    private = PrivateKey.generate()
    public_b64 = base64.b64encode(bytes(private.public_key)).decode()
    private_b64 = base64.b64encode(bytes(private)).decode()

    priv_path = Path(f"collector_private_{key_id}.txt")
    write_private(priv_path, private_b64)

    created_hash_key = False
    hash_path = Path("account_hash_key.txt")
    if key_id == "k1" and not hash_path.exists():
        write_private(hash_path, base64.b64encode(secrets.token_bytes(32)).decode())
        created_hash_key = True

    print(f"Key id:      {key_id}")
    print(f"Public key:  {public_b64}")
    print()
    print("Put the public key in project.json -> collector.keys, e.g.:")
    print(f'  {{"key_id": "{key_id}", "public_key_b64": "{public_b64}", "status": "active"}}')
    print()
    print(f"Private key written to {priv_path} (only you can read it). Next:")
    print(f"  gh secret set COLLECTOR_PRIVATE_KEY_{key_id.upper()} --repo vikramyadav06/Ai-Tutor-Platform < {priv_path}")
    if created_hash_key:
        print(f"  gh secret set ACCOUNT_HASH_KEY --repo vikramyadav06/Ai-Tutor-Platform < {hash_path}")
    print("Then delete those files. Never commit them or share them with anyone, including AI agents.")


if __name__ == "__main__":
    main()
