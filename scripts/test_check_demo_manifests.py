#!/usr/bin/env python3
"""Pins scripts/check-demo-manifests.py (task #3787, spec FR-16, NFR-02, NFR-03, amendment M4): the rules the Kubernetes drafts of
the two public demos must satisfy, run on small fixture folders (good and bad) built in a temp directory.
T1 names and labels, and network policies that select only `app.kubernetes.io/part-of: craticula` pods.
T2 container limits, non-root user, read-only root file system, no added capabilities.
T3 no Secret object with data and no literal password or token in any file of the folder.
T4 (M4) an Ingress carries a tls block with the secret and ssl-protocols "TLSv1.2 TLSv1.3", and no snippet annotation (the cluster's
admission webhook refuses them). HSTS is the controller's default and is verified from outside by scripts/check-demos.sh.
The last class runs the script on the real drafts docs/feat/3323/gitops/cst/craticula-demo/ (private: skipped in the public mirror).
Contract for the script: `check-demo-manifests.py <folder>`; exit 0 = all rules hold, 1 = one `FAIL <file>: <what>` line per
violation on stdout, 2 = usage or missing folder. Fixtures are block-style YAML, 2-space indent, `---` between documents.
Run: python3 scripts/test_check_demo_manifests.py
"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check-demo-manifests.py"
PUBLISH_SCRIPT = ROOT / "scripts" / "publish-github.sh"
REAL = ROOT / "docs" / "feat" / "3323" / "gitops" / "cst" / "craticula-demo"

LABELS = "app.kubernetes.io/part-of: craticula"
LITERAL = "Sup3r" + "S3cret" + "Value"   # built at run time so the commit secret scanner never sees a literal
DEMO_IMAGE = "docker.io/elieabouaad/craticula-demo:sha-0123456"

DEPLOYMENT = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {name}
  labels:
    app.kubernetes.io/name: {name}
    {labels}
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: {name}
  template:
    metadata:
      labels:
        app.kubernetes.io/name: {name}
        {labels}
    spec:
      containers:
        - name: app
          image: docker.io/elieabouaad/craticula-demo:sha-0123456
{container}
"""

CONTAINER = """\
          env:
            - name: DEMO_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: craticula-pg-demo
                  key: password
          resources:
            limits:
              cpu: 500m
              memory: 256Mi
          securityContext:
            runAsNonRoot: true
            runAsUser: 10001
            readOnlyRootFilesystem: true
            allowPrivilegeEscalation: false
            capabilities:
              drop: [ALL]
"""

POLICY = """\
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: craticula-pg-demo
  labels:
    {labels}
spec:
{selector}
  policyTypes: [Ingress, Egress]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: ingress
"""

SELECTOR_OK = """\
  podSelector:
    matchLabels:
      app.kubernetes.io/part-of: craticula
      app.kubernetes.io/name: craticula-pg-demo"""

INGRESS = """\
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: craticula-pg-demo
  labels:
    {labels}
  annotations:
{annotations}
spec:
  ingressClassName: nginx
{tls}
  rules:
    - host: craticula-pg.pluries.dev
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: craticula-pg-demo
                port:
                  number: 80
"""

ANNOTATIONS_OK = '    nginx.ingress.kubernetes.io/ssl-protocols: "TLSv1.2 TLSv1.3"'

TLS_OK = """\
  tls:
    - hosts: [craticula-pg.pluries.dev]
      secretName: pluries-ingress-tls"""

SERVICE = """\
apiVersion: v1
kind: Service
metadata:
  name: craticula-pg-demo
  labels:
    {labels}
spec:
  selector:
    app.kubernetes.io/name: craticula-pg-demo
  ports:
    - port: 80
      targetPort: 8080
"""


DB_DEPLOYMENT = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: craticula-pg-db
  labels:
    app.kubernetes.io/name: craticula-pg-db
    {labels}
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: craticula-pg-db
  template:
    metadata:
      labels:
        app.kubernetes.io/name: craticula-pg-db
        {labels}
    spec:
{init}      containers:
        - name: database
          image: postgres@sha256:0000000000000000000000000000000000000000000000000000000000000000
{container}{seed}"""

SEED_CONTAINER = """\
        - name: seed
          image: {image}
{container}"""


def db_deployment(seed=True, init="", seed_image=DEMO_IMAGE, seed_name="seed"):
    seed_text = SEED_CONTAINER.format(image=seed_image, container=CONTAINER).replace("name: seed", f"name: {seed_name}", 1) if seed else ""
    return DB_DEPLOYMENT.format(labels=LABELS, container=CONTAINER, seed=seed_text, init=init)


ADMIN_INIT = """\
      initContainers:
        - name: seed
          image: {image}
          env:
            - name: DEMO_PG
              valueFrom:
                secretKeyRef:
                  name: craticula-pg-admin
                  key: connection-string
{hardening}"""

ADMIN_ENV = """\
          env:
            - name: DEMO_PG
              valueFrom:
                secretKeyRef:
                  name: craticula-pg-admin
                  key: connection-string
"""


def deployment(name="craticula-pg-demo", labels=LABELS, container=CONTAINER):
    return DEPLOYMENT.format(name=name, labels=labels, container=container)


def policy(selector=SELECTOR_OK, labels=LABELS):
    return POLICY.format(selector=selector, labels=labels)


def ingress(annotations=ANNOTATIONS_OK, tls=TLS_OK, labels=LABELS):
    return INGRESS.format(annotations=annotations, tls=tls, labels=labels)


def good_files():
    return {"demo.yaml": deployment() + "---\n" + SERVICE.format(labels=LABELS), "db.yaml": db_deployment(),
            "policy.yaml": policy(), "ingress.yaml": ingress(),
            "README.md": "Create the secret by hand: kubectl create secret generic craticula-pg-demo --from-literal=password=<password>\n"}


class ManifestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def folder(self, files, name="gitops"):
        root = self.tmp / name
        for rel, text in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return root

    def run_check(self, folder):
        return subprocess.run([sys.executable, str(SCRIPT), str(folder)], capture_output=True, text=True, timeout=60)

    def assert_passes(self, files):
        result = self.run_check(self.folder(files))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertNotIn("FAIL", result.stdout)

    def assert_fails(self, files, mention):
        result = self.run_check(self.folder(files))
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertNotIn("not implemented", result.stderr)
        self.assertRegex(result.stdout, r"(?m)^FAIL ")
        self.assertIn(mention.lower(), result.stdout.lower())

    def variant(self, **replacements):
        files = good_files()
        files.update(replacements)
        return files


class UsageTests(ManifestCase):
    def test_a_missing_folder_or_no_argument_exits_2(self):
        for args in ((), (str(self.tmp / "absent"),)):
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, timeout=60)
                self.assertEqual(2, result.returncode, result.stderr)
                self.assertNotIn("not implemented", result.stderr)


class T1NamesLabelsAndPolicies(ManifestCase):
    def test_t1_good_folder_passes(self):
        self.assert_passes(good_files())

    def test_t1_an_object_not_named_craticula_fails(self):
        self.assert_fails(self.variant(**{"demo.yaml": deployment(name="demo-pg")}), "craticula-")

    def test_t1_an_object_without_the_part_of_label_fails(self):
        self.assert_fails(self.variant(**{"demo.yaml": deployment(labels="app.kubernetes.io/part-of: other")}), "part-of")

    def test_t1_a_policy_with_an_empty_pod_selector_fails(self):
        self.assert_fails(self.variant(**{"policy.yaml": policy(selector="  podSelector: {}")}), "podSelector")

    def test_t1_a_policy_without_a_pod_selector_fails(self):
        self.assert_fails(self.variant(**{"policy.yaml": policy(selector="  # selects nothing in particular")}), "podSelector")

    def test_t1_a_policy_selecting_another_label_fails(self):
        other = "  podSelector:\n    matchLabels:\n      app: someone-elses-pod"
        self.assert_fails(self.variant(**{"policy.yaml": policy(selector=other)}), "part-of")


class T2ContainerHardening(ManifestCase):
    def container_without(self, text):
        self.assertIn(text, CONTAINER)
        return CONTAINER.replace(text, "")

    def test_t2_a_container_without_limits_fails(self):
        no_limits = self.container_without("          resources:\n            limits:\n              cpu: 500m\n              memory: 256Mi\n")
        self.assert_fails(self.variant(**{"demo.yaml": deployment(container=no_limits)}), "limits")

    def test_t2_limits_without_memory_fail(self):
        self.assert_fails(self.variant(**{"demo.yaml": deployment(container=CONTAINER.replace("              memory: 256Mi\n", ""))}), "memory")

    def test_t2_a_container_that_may_run_as_root_fails(self):
        no_user = self.container_without("            runAsNonRoot: true\n            runAsUser: 10001\n")
        self.assert_fails(self.variant(**{"demo.yaml": deployment(container=no_user)}), "non-root")

    def test_t2_a_container_running_as_user_0_fails(self):
        root = CONTAINER.replace("runAsNonRoot: true\n            runAsUser: 10001", "runAsUser: 0")
        self.assert_fails(self.variant(**{"demo.yaml": deployment(container=root)}), "non-root")

    def test_t2_a_writable_root_file_system_fails(self):
        writable = CONTAINER.replace("readOnlyRootFilesystem: true", "readOnlyRootFilesystem: false")
        self.assert_fails(self.variant(**{"demo.yaml": deployment(container=writable)}), "readOnlyRootFilesystem")

    def test_t2_a_missing_read_only_root_file_system_fails(self):
        missing = self.container_without("            readOnlyRootFilesystem: true\n")
        self.assert_fails(self.variant(**{"demo.yaml": deployment(container=missing)}), "readOnlyRootFilesystem")

    def test_t2_an_added_capability_fails(self):
        added = CONTAINER.replace("drop: [ALL]", "add: [NET_ADMIN]")
        self.assert_fails(self.variant(**{"demo.yaml": deployment(container=added)}), "capabilit")

    def test_t2_one_bad_container_among_two_fails(self):
        second = "        - name: db\n          image: docker.io/library/postgres:16\n"
        self.assert_fails(self.variant(**{"demo.yaml": deployment(container=CONTAINER + second)}), "db")


class T5DatabaseReseedAndAdminSecret(ManifestCase):
    """Design rules of #3787 (review): the database pod reseeds itself when it is recreated, the API pod never sees the admin secret.
    A database Deployment is named craticula-<engine>-db; the API Deployment craticula-<engine>-demo. Contract: a database pod
    needs, under `containers` (an init container does not count: the database is not up yet), a container named `seed*` whose image
    contains `craticula-demo`; the message names "seed". No container or init container of an API pod may reference a secret whose
    name contains `admin` (secretKeyRef, secretRef or a secret volume); the message names "admin"."""

    def test_t5_a_database_pod_with_a_seed_container_passes(self):
        self.assert_passes(good_files())

    def test_t5_a_database_pod_without_a_seed_container_fails(self):
        self.assert_fails(self.variant(**{"db.yaml": db_deployment(seed=False)}), "seed")

    def test_t5_a_seed_that_is_only_an_init_container_does_not_count(self):
        init = ADMIN_INIT.format(image=DEMO_IMAGE, hardening=CONTAINER.split("          env:\n", 1)[0] + CONTAINER[CONTAINER.index("          resources:"):])
        self.assert_fails(self.variant(**{"db.yaml": db_deployment(seed=False, init=init)}), "seed")

    def test_t5_a_seed_container_that_does_not_use_the_demo_image_fails(self):
        self.assert_fails(self.variant(**{"db.yaml": db_deployment(seed_image="docker.io/library/busybox@sha256:" + "1" * 64)}), "seed")

    def test_t5_an_api_pod_with_an_admin_secret_in_a_container_fails(self):
        admin = CONTAINER.replace(CONTAINER.split("          resources:")[0], ADMIN_ENV)
        self.assert_fails(self.variant(**{"demo.yaml": deployment(container=admin)}), "admin")

    def test_t5_an_api_pod_with_an_init_container_mounting_the_admin_secret_fails(self):
        api = deployment().replace("      containers:\n", ADMIN_INIT.format(image=DEMO_IMAGE, hardening=CONTAINER[CONTAINER.index("          resources:"):]) + "      containers:\n", 1)
        self.assert_fails(self.variant(**{"demo.yaml": api}), "admin")

    def test_t5_an_api_pod_with_an_admin_secret_volume_fails(self):
        api = deployment().replace("      containers:\n", "      volumes:\n        - name: creds\n          secret:\n            secretName: craticula-pg-admin\n      containers:\n", 1)
        self.assert_fails(self.variant(**{"demo.yaml": api}), "admin")

    def test_t5_the_seed_container_of_the_database_pod_may_use_the_admin_secret(self):
        seed_with_admin = db_deployment().replace(CONTAINER[: CONTAINER.index("          resources:")], ADMIN_ENV)
        self.assert_passes(self.variant(**{"db.yaml": seed_with_admin}))


class T3NoSecrets(ManifestCase):
    SECRET = "apiVersion: v1\nkind: Secret\nmetadata:\n  name: craticula-pg-demo\n  labels:\n    " + LABELS + "\n{body}"

    def test_t3_a_secret_with_data_fails(self):
        files = self.variant(**{"secret.yaml": self.SECRET.format(body="data:\n  password: c3VwZXJzZWNyZXQ=\n")})
        self.assert_fails(files, "secret")

    def test_t3_a_secret_with_string_data_fails(self):
        files = self.variant(**{"secret.yaml": self.SECRET.format(body="stringData:\n  password: not-for-git\n")})
        self.assert_fails(files, "secret")

    def test_t3_a_literal_password_in_an_env_value_fails(self):
        literal = CONTAINER.replace("valueFrom:\n                secretKeyRef:\n                  name: craticula-pg-demo\n                  key: password",
                                    "value: " + LITERAL)
        self.assert_fails(self.variant(**{"demo.yaml": deployment(container=literal)}), "password")

    def test_t3_a_literal_token_in_any_file_fails(self):
        self.assert_fails(self.variant(**{"notes.txt": "to" + "ken: " + LITERAL + "\n"}), "token")

    def test_t3_a_literal_in_a_kubectl_command_of_the_readme_fails(self):
        readme = "kubectl create secret generic craticula-pg-demo --from-literal=" + "pass" + "word=" + LITERAL + "\n"
        self.assert_fails(self.variant(**{"README.md": readme}), "password")

    def test_t3_a_connection_string_with_a_password_fails(self):
        self.assert_fails(self.variant(**{"notes.txt": "postgres:" + "//reader:" + LITERAL + "@" + "craticula-pg-db:5432/orders\n"}), "password")

    def test_t3_placeholders_and_secret_key_references_pass(self):
        self.assert_passes(self.variant(**{"README.md": "kubectl create secret generic x --from-literal=password=<password> --from-literal=token=${TOKEN}\n"}))


class T4IngressTls(ManifestCase):
    def test_t4_an_ingress_without_a_tls_block_fails(self):
        self.assert_fails(self.variant(**{"ingress.yaml": ingress(tls="")}), "tls")

    def test_t4_a_tls_block_without_the_secret_fails(self):
        self.assert_fails(self.variant(**{"ingress.yaml": ingress(tls="  tls:\n    - hosts: [craticula-pg.pluries.dev]")}), "secretName")

    def test_t4_without_the_ssl_protocols_annotation_fails(self):
        self.assert_fails(self.variant(**{"ingress.yaml": ingress(annotations="    example.com/other: x")}), "ssl-protocols")

    def test_t4_protocols_that_allow_tls_1_1_fail(self):
        old = ANNOTATIONS_OK.replace('"TLSv1.2 TLSv1.3"', '"TLSv1.1 TLSv1.2 TLSv1.3"')
        self.assert_fails(self.variant(**{"ingress.yaml": ingress(annotations=old)}), "ssl-protocols")

    def test_t4_a_snippet_annotation_fails_whatever_its_kind(self):
        for key in ("configuration-snippet", "server-snippet", "stream-snippet"):
            with self.subTest(key=key):
                snippet = ANNOTATIONS_OK + f"\n    nginx.ingress.kubernetes.io/{key}: |\n      more_set_headers \"X-Demo: 1\";"
                self.assert_fails(self.variant(**{"ingress.yaml": ingress(annotations=snippet)}), "snippet")

    def test_t4_no_hsts_annotation_is_required(self):
        self.assert_passes(good_files())

    def test_t4_the_good_ingress_passes(self):
        self.assert_passes(good_files())


@unittest.skipUnless(PUBLISH_SCRIPT.is_file(), "private repository only: scripts/publish-github.sh is absent (public mirror)")
class RealDraftsTests(ManifestCase):
    """RED until the drafts exist: docs/feat/3323/gitops/cst/craticula-demo/ is written by theme 4 (task #3787)."""

    def test_the_real_drafts_pass_the_check(self):
        self.assertTrue(REAL.is_dir(), f"{REAL.relative_to(ROOT)} is missing: the drafts of the demos are not written yet")
        result = self.run_check(REAL)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertNotIn("FAIL", result.stdout)


@unittest.skipUnless(PUBLISH_SCRIPT.is_file(), "private repository only: scripts/publish-github.sh is absent (public mirror)")
class RealDraftsDesignTests(unittest.TestCase):
    """RED until the drafts follow the review: the database pods seed themselves; the API pods never see an admin secret.
    Read as text (comments dropped), independent of the check script."""
    BASE = REAL / "base"

    @staticmethod
    def code(path):
        return "\n".join(l for l in path.read_text(encoding="utf-8").splitlines() if not l.lstrip().startswith("#"))

    def test_each_database_pod_has_a_seed_container_using_the_demo_image(self):
        databases = sorted(self.BASE.glob("*-database.yaml"))
        self.assertEqual(2, len(databases), "pg-database.yaml and mongo-database.yaml")
        for path in databases:
            with self.subTest(path=path.name):
                text = self.code(path)
                pod = text[text.index("      containers:"):] if "      containers:" in text else ""
                self.assertRegex(pod, r"(?m)^        - name: seed\w*\n\s+image: \S*craticula-demo", f"{path.name}: no seed container with the demo image in the database pod")

    def test_no_api_pod_references_an_admin_secret(self):
        demos = sorted(self.BASE.glob("*-demo.yaml"))
        self.assertEqual(2, len(demos), "pg-demo.yaml and mongo-demo.yaml")
        for path in demos:
            with self.subTest(path=path.name):
                self.assertNotRegex(self.code(path), r"-admin\b", f"{path.name} mentions an admin secret")
                self.assertNotIn("initContainers", self.code(path), f"{path.name} still seeds from an init container")


if __name__ == "__main__":
    unittest.main()
