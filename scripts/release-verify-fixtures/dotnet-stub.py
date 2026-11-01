#!/usr/bin/env python3
"""Synthetic stand-in for `dotnet nuget verify`, driven by the JSON file named in RELEASE_VERIFY_STUB_CONFIG:
{"expectedFingerprint": "<64 hex>", "modes": {"<package id>": "ok|unsigned|wrong-fingerprint|untrusted-root|no-timestamp|silent-no-timestamp"}, "default": "ok", "log": "<file>"}
The output texts imitate the SDK's NU3004 / NU3018 / NU3027 lines and, for a timestamped package, the detailed line the real SDK 10.0.114
prints; nothing here is real output or key material. The log gets one JSON object per call: the full argv and the invariant-culture variable."""
import json
import os
import re
import sys

config = json.loads(open(os.environ["RELEASE_VERIFY_STUB_CONFIG"], encoding="utf-8").read())
args = sys.argv[1:]
if config.get("log"):
    with open(config["log"], "a", encoding="utf-8") as log:
        log.write(json.dumps({"argv": args, "invariant": os.environ.get("DOTNET_SYSTEM_GLOBALIZATION_INVARIANT", "unset")}) + "\n")
package = args[-1]
match = re.match(r"^(.*?)\.\d+\.\d+\.\d+.*\.nupkg$", os.path.basename(package))
package_id = match.group(1) if match else os.path.basename(package)
mode = config.get("modes", {}).get(package_id, config.get("default", "ok"))
fingerprint = args[args.index("--certificate-fingerprint") + 1] if "--certificate-fingerprint" in args else ""
if mode == "ok" and fingerprint.lower() != config.get("expectedFingerprint", "").lower():
    mode = "wrong-fingerprint"
if mode == "unsigned":
    print(f"Verifying {package_id}")
    print("error: NU3004: The package is not signed. The package must be signed.")
    sys.exit(1)
if mode == "untrusted-root":
    print("error: NU3018: A certificate chain processed, but terminated in a root certificate which is not trusted")
    sys.exit(1)
if mode == "wrong-fingerprint":
    print(f"Verifying {package_id}")
    print("error: NU3034: The package signature certificate fingerprint does not match any allowed fingerprint.")
    sys.exit(1)
print(f"Verifying {package_id}")
if mode == "no-timestamp":
    print("warning: NU3027: The signature should be timestamped to enable long-term signature validity after the certificate has expired.")
elif mode == "ok":
    print("Verifying author primary signature's timestamp with timestamping service certificate:")
print(f"Successfully verified package '{package_id}'.")
