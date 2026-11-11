#!/usr/bin/env python3
"""Manifest check of the demo Kubernetes drafts (task #3787, FR-16, NFR-02, NFR-03, amendment M4).
Contract: check-demo-manifests.py <folder>; exit 0 = every rule holds, 1 = at least one `FAIL <file>: <rule>` line on stdout,
2 = usage or missing folder. Standard library only: the YAML the drafts use (block style, 2-space indent, flow lists and maps on
one line, `|` block scalars, `---` between documents) is read by the small parser below, not by PyYAML.

Rules:
  T1  every object is named `craticula-...` and carries `app.kubernetes.io/part-of: craticula`; a NetworkPolicy selects pods by
      `matchLabels` that include that label (an empty or missing podSelector selects the whole namespace).
  T2  every container has cpu and memory limits, runs as non-root, has a read-only root file system, no privilege escalation,
      drops ALL capabilities and adds none.
  T3  no Secret object holds data; no literal password, token or connection-string password in any file of the folder.
  T5  a database Deployment (craticula-*-db) has, under containers, a container named seed* that runs the craticula-demo image (an init
      container does not count: the database is not up yet), so a recreated database pod is seeded again; an API Deployment
      (craticula-*-demo) references no secret whose name contains admin, in a container, an init container or a volume.
  T4  every Ingress has a tls block with a secretName, ssl-protocols limited to TLSv1.2 and TLSv1.3, and no snippet annotation (the
      cluster's admission webhook refuses them). HSTS is the controller's default; scripts/check-demos.sh verifies it from outside.
"""
import re
import sys
from pathlib import Path

LABEL_KEY, LABEL_VALUE = "app.kubernetes.io/part-of", "craticula"
WORKLOADS = ("Deployment", "StatefulSet", "DaemonSet", "Job", "ReplicaSet")
SKIPPED_KINDS = ("Kustomization", "Application", "AppProject")


class YamlError(Exception):
    pass


def strip_comment(text):
    quote = None
    for index, char in enumerate(text):
        if quote:
            if char == quote:
                quote = None
        elif char in "'\"" and (index == 0 or text[index - 1] in " \t[{,:"):
            quote = char
        elif char == "#" and (index == 0 or text[index - 1] in " \t"):
            return text[:index].rstrip()
    return text.rstrip()


def parse_flow(text):
    position = 0

    def skip():
        nonlocal position
        while position < len(text) and text[position] in " \t":
            position += 1

    def value():
        nonlocal position
        skip()
        if position >= len(text):
            raise YamlError(f"unfinished flow value: {text}")
        if text[position] == "[":
            position += 1
            items = []
            skip()
            while text[position] != "]":
                items.append(value())
                skip()
                if text[position] == ",":
                    position += 1
                    skip()
            position += 1
            return items
        if text[position] == "{":
            position += 1
            mapping = {}
            skip()
            while text[position] != "}":
                key = scalar_until(":")
                position += 1
                mapping[key] = value()
                skip()
                if text[position] == ",":
                    position += 1
                    skip()
            position += 1
            return mapping
        return scalar_until(",]}")

    def scalar_until(stops):
        nonlocal position
        skip()
        if position < len(text) and text[position] in "'\"":
            quote = text[position]
            end = text.index(quote, position + 1)
            raw, position = text[position:end + 1], end + 1
            return convert(raw)
        start = position
        while position < len(text) and text[position] not in stops:
            position += 1
        return convert(text[start:position].strip())

    return value()


def convert(raw):
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
        return raw[1:-1]
    if raw in ("true", "True"):
        return True
    if raw in ("false", "False"):
        return False
    if raw in ("null", "~", ""):
        return None
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    return raw


def scalar(raw):
    raw = raw.strip()
    if raw.startswith(("[", "{")):
        return parse_flow(raw)
    return convert(raw)


def split_key(content):
    quoted = re.match(r"""^("[^"]*"|'[^']*')\s*:(?:\s+(.*))?$""", content)
    if quoted:
        return quoted.group(1)[1:-1], quoted.group(2) or ""
    plain = re.match(r"^([^\s\[{'\"-][^:]*?|-[^\s:][^:]*?):(?:\s+(.*))?$", content)
    if plain:
        return plain.group(1).strip(), plain.group(2) or ""
    return None


class Parser:
    def __init__(self, text):
        self.lines = text.split("\n")
        self.i = 0

    def peek(self):
        while self.i < len(self.lines):
            raw = self.lines[self.i]
            content = strip_comment(raw.strip())
            if content:
                return len(raw) - len(raw.lstrip(" ")), content
            self.i += 1
        return None

    def block(self, min_indent):
        item = self.peek()
        if not item or item[0] < min_indent:
            return None
        indent, content = item
        if content == "-" or content.startswith("- "):
            return self.sequence(indent)
        return self.mapping(indent)

    def sequence(self, indent):
        out = []
        while True:
            item = self.peek()
            if not item or item[0] != indent or not (item[1] == "-" or item[1].startswith("- ")):
                return out
            content = item[1]
            rest = content[1:].lstrip(" ")
            if not rest:
                self.i += 1
                out.append(self.block(indent + 1))
            elif split_key(rest) is not None:
                offset = len(content) - len(rest)
                self.lines[self.i] = " " * (indent + offset) + rest
                out.append(self.mapping(indent + offset))
            else:
                self.i += 1
                out.append(scalar(rest))

    def mapping(self, indent):
        out = {}
        while True:
            item = self.peek()
            if not item or item[0] != indent:
                return out
            pair = split_key(item[1])
            if pair is None:
                raise YamlError(f"line {self.i + 1}: cannot read `{item[1]}`")
            key, value = pair
            self.i += 1
            value = strip_comment(value)
            if value == "":
                following = self.peek()
                if following and following[0] > indent:
                    out[key] = self.block(following[0])
                elif following and following[0] == indent and (following[1] == "-" or following[1].startswith("- ")):
                    out[key] = self.sequence(indent)
                else:
                    out[key] = None
            elif value[0] in "|>":
                out[key] = self.block_scalar(indent)
            else:
                out[key] = scalar(value)

    def block_scalar(self, indent):
        body = []
        while self.i < len(self.lines):
            raw = self.lines[self.i]
            if raw.strip() and len(raw) - len(raw.lstrip(" ")) <= indent:
                break
            body.append(raw)
            self.i += 1
        margin = min((len(line) - len(line.lstrip(" ")) for line in body if line.strip()), default=0)
        return "\n".join(line[margin:] for line in body).strip("\n")


def parse_documents(text):
    documents, current = [], []
    for line in text.split("\n"):
        if line.strip() == "---":
            documents.append("\n".join(current))
            current = []
        else:
            current.append(line)
    documents.append("\n".join(current))
    parsed = []
    for document in documents:
        value = Parser(document).block(0)
        if value is not None:
            parsed.append(value)
    return parsed


def dig(node, *path):
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def pod_spec(kind, doc):
    if kind in WORKLOADS:
        return dig(doc, "spec", "template", "spec")
    if kind == "CronJob":
        return dig(doc, "spec", "jobTemplate", "spec", "template", "spec")
    if kind == "Pod":
        return dig(doc, "spec")
    return None


def pod_labels(kind, doc):
    if kind in WORKLOADS:
        return dig(doc, "spec", "template", "metadata", "labels")
    if kind == "CronJob":
        return dig(doc, "spec", "jobTemplate", "spec", "template", "metadata", "labels")
    return None


def is_placeholder(value):
    return value.startswith(("<", "$", "{")) or value in ("", "changeme")


def check_container(where, container, pod_context, fail):
    if not isinstance(container, dict):
        fail(f"{where}: a container is not a mapping")
        return
    label = f"{where} container {container.get('name', '?')}"
    limits = dig(container, "resources", "limits")
    if not isinstance(limits, dict):
        fail(f"{label}: resources.limits missing (cpu and memory)")
    else:
        for resource in ("cpu", "memory"):
            if not limits.get(resource):
                fail(f"{label}: resources.limits.{resource} missing")
    context = container.get("securityContext") if isinstance(container.get("securityContext"), dict) else {}
    pod = pod_context if isinstance(pod_context, dict) else {}
    user = context.get("runAsUser", pod.get("runAsUser"))
    non_root_flag = context.get("runAsNonRoot", pod.get("runAsNonRoot"))
    if user == 0 or not (non_root_flag is True or (isinstance(user, int) and user > 0)):
        fail(f"{label}: must run as non-root (runAsNonRoot: true or a runAsUser above 0, never 0)")
    if context.get("readOnlyRootFilesystem") is not True:
        fail(f"{label}: readOnlyRootFilesystem must be true")
    if context.get("allowPrivilegeEscalation") is not False:
        fail(f"{label}: allowPrivilegeEscalation must be false")
    capabilities = context.get("capabilities") if isinstance(context.get("capabilities"), dict) else {}
    if capabilities.get("add"):
        fail(f"{label}: capabilities.add must be empty")
    if "ALL" not in (capabilities.get("drop") or []):
        fail(f"{label}: capabilities.drop must contain ALL")
    for variable in container.get("env") or []:
        if not isinstance(variable, dict) or "value" not in variable:
            continue
        literal = variable.get("value")
        sensitive = re.search(r"(?i)pass|secret|token|key|credential", str(variable.get("name", "")))
        if sensitive and literal not in (None, "") and not is_placeholder(str(literal)):
            fail(f"{label}: env {variable.get('name')} holds a literal value (password or token): use secretKeyRef")


def secret_names(spec):
    names = []
    for field in ("containers", "initContainers"):
        for container in spec.get(field) or []:
            if not isinstance(container, dict):
                continue
            for variable in container.get("env") or []:
                names.append(dig(variable, "valueFrom", "secretKeyRef", "name"))
            for source in container.get("envFrom") or []:
                names.append(dig(source, "secretRef", "name"))
    for volume in spec.get("volumes") or []:
        names.append(dig(volume, "secret", "secretName"))
    return [n for n in names if isinstance(n, str)]


def check_seeding(where, name, spec, fail):
    if re.fullmatch(r"craticula-.+-db", name):
        seeds = [c for c in spec.get("containers") or []
                 if isinstance(c, dict) and str(c.get("name", "")).startswith("seed") and "craticula-demo" in str(c.get("image", ""))]
        if not seeds:
            fail(f"{where}: the database pod needs a container named seed* running the craticula-demo image under containers "
                 "(an init container does not count), so that a recreated database is seeded again")
    elif re.fullmatch(r"craticula-.+-demo", name):
        for secret in secret_names(spec):
            if "admin" in secret:
                fail(f"{where}: the API pod must not reference the admin secret {secret}")


def check_document(doc, fail):
    if not isinstance(doc, dict):
        fail("document is not a mapping")
        return
    kind = doc.get("kind")
    if kind in SKIPPED_KINDS:
        return
    name = dig(doc, "metadata", "name")
    where = f"{kind}/{name}"
    if not isinstance(name, str) or not name.startswith("craticula-"):
        fail(f"{where}: the name must start with craticula-")
    labels = dig(doc, "metadata", "labels")
    if not isinstance(labels, dict) or labels.get(LABEL_KEY) != LABEL_VALUE:
        fail(f"{where}: metadata.labels needs {LABEL_KEY}: {LABEL_VALUE}")
    if kind in WORKLOADS or kind == "CronJob":
        template_labels = pod_labels(kind, doc)
        if not isinstance(template_labels, dict) or template_labels.get(LABEL_KEY) != LABEL_VALUE:
            fail(f"{where}: the pod template labels need {LABEL_KEY}: {LABEL_VALUE}")

    if kind == "NetworkPolicy":
        selector = dig(doc, "spec", "podSelector")
        if not isinstance(selector, dict) or not selector:
            fail(f"{where}: spec.podSelector is empty or missing (it would select every pod of the namespace)")
        elif dig(selector, "matchLabels", LABEL_KEY) != LABEL_VALUE:
            fail(f"{where}: spec.podSelector.matchLabels must include {LABEL_KEY}: {LABEL_VALUE}")

    spec = pod_spec(kind, doc)
    if isinstance(spec, dict):
        if not spec.get("containers"):
            fail(f"{where}: no containers")
        for field in ("containers", "initContainers"):
            for container in spec.get(field) or []:
                check_container(where, container, spec.get("securityContext"), fail)

    if kind == "Deployment" and isinstance(spec, dict):
        check_seeding(where, str(name), spec, fail)

    if kind == "Secret" and (doc.get("data") or doc.get("stringData")):
        fail(f"{where}: a Secret object with data must not be in a file (create it with kubectl create secret)")

    if kind == "Ingress":
        tls = dig(doc, "spec", "tls")
        if not tls:
            fail(f"{where}: spec.tls block missing")
        else:
            for entry in tls:
                if not isinstance(entry, dict) or not entry.get("secretName"):
                    fail(f"{where}: a tls entry has no secretName")
        annotations = dig(doc, "metadata", "annotations")
        annotations = annotations if isinstance(annotations, dict) else {}
        protocols = annotations.get("nginx.ingress.kubernetes.io/ssl-protocols")
        if not isinstance(protocols, str) or not protocols.split() or not set(protocols.split()) <= {"TLSv1.2", "TLSv1.3"}:
            fail(f"{where}: annotation ssl-protocols must be \"TLSv1.2 TLSv1.3\" (TLS 1.2 or higher only)")
        for key in annotations:
            if "snippet" in str(key).lower():
                fail(f"{where}: annotation {key} is a snippet annotation, which the cluster's admission webhook refuses")


SECRET_LITERAL = re.compile(r"""(?i)(?<![A-Za-z0-9_])(password|passwd|secret|token|apikey|api_key)\s*[:=]\s*['"]?([^\s'"]{8,})""")
# scheme, user, the part to inspect, then the at-sign: built in pieces so a secrets scanner does not read this pattern as a literal
URL_USERINFO = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:" + "//" + r"[^/\s:@]+:([^@\s/]+)" + "@")


def scan_literals(relative, text, fail):
    for number, line in enumerate(text.splitlines(), 1):
        for match in SECRET_LITERAL.finditer(line):
            if not is_placeholder(match.group(2)):
                fail(f"line {number}: a literal {match.group(1).lower()} value (use a placeholder or a secret reference)", relative)
        for match in URL_USERINFO.finditer(line):
            if not is_placeholder(match.group(1)):
                fail(f"line {number}: a connection string with a password in it", relative)


def main(argv):
    if len(argv) != 2 or not Path(argv[1]).is_dir():
        print("usage: check-demo-manifests.py <folder>", file=sys.stderr)
        return 2
    root = Path(argv[1])
    failures = []
    objects = 0
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        relative = str(path.relative_to(root))

        def fail(message, where=relative):
            failures.append(f"FAIL {where}: {message}")

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        scan_literals(relative, text, fail)
        if path.suffix in (".yaml", ".yml"):
            try:
                documents = parse_documents(text)
            except (YamlError, ValueError, IndexError) as error:
                fail(f"cannot read the YAML: {error}")
                continue
            for document in documents:
                objects += 1
                check_document(document, fail)
    for line in failures:
        print(line)
    if failures:
        return 1
    print(f"check-demo-manifests: {objects} objects in {root} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
