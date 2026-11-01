#!/usr/bin/env python3
"""Synthetic stand-in for `dotnet nuget verify`, driven by the JSON file named in RELEASE_VERIFY_STUB_CONFIG:
{"expectedFingerprint": "<64 hex>", "modes": {"<package id>": "ok|unsigned|wrong-fingerprint|no-timestamp"}, "default": "ok", "log": "<file>"}
The output texts imitate the SDK's NU3004 / NU3027 lines; nothing here is real output or key material."""
import json
import os
import re
import sys

config = json.loads(open(os.environ["RELEASE_VERIFY_STUB_CONFIG"], encoding="utf-8").read())
args = sys.argv[1:]
if config.get("log"):
    with open(config["log"], "a", encoding="utf-8") as log:
        log.write(json.dumps(args) + "\n")
package = args[-1]
match = re.match(r"^(.*)\.\d+\.\d+\.\d+\.nupkg$", os.path.basename(package))
package_id = match.group(1) if match else os.path.basename(package)
mode = config.get("modes", {}).get(package_id, config.get("default", "ok"))
fingerprint = args[args.index("--certificate-fingerprint") + 1] if "--certificate-fingerprint" in args else ""
if mode == "ok" and fingerprint.lower() != config.get("expectedFingerprint", "").lower():
    mode = "wrong-fingerprint"
if mode == "unsigned":
    print(f"Verifying {package_id}")
    print("error: NU3004: The package is not signed. The package must be signed.")
    sys.exit(1)
if mode == "wrong-fingerprint":
    print(f"Verifying {package_id}")
    print("error: NU3034: The package signature certificate fingerprint does not match any allowed fingerprint.")
    sys.exit(1)
print(f"Verifying {package_id}")
if mode == "no-timestamp":
    print("warning: NU3027: The signature should be timestamped to enable long-term signature validity after the certificate has expired.")
print(f"Successfully verified package '{package_id}'.")
