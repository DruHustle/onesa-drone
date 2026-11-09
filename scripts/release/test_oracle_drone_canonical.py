"""Real Git/archive/signature fixtures; no network, hosted release or flight authority."""

import base64
import copy
import hashlib
import io
import json
import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import oracle_drone as runner
import oracle_install as installer
import oracle_owner as owner
import test_oracle_drone as plan_fixture
import test_oracle_owner as store_fixture

from source_protocol_fixtures import SourceFixture


def archive_pins(source):
    return {name: hashlib.sha256(base64.b64decode(data)).hexdigest() for name, data in source.archives.items()}


class InstallFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=Path.home() if os.getuid() == 0 else None)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.root.chmod(0o700)
        self.bundle = self.root / "bundle"
        self.bundle.mkdir(mode=0o700)
        self.checkout = self.root / "repository"
        self.checkout.mkdir(mode=0o700)
        self.parent = self.root / "immutable"
        self.parent.mkdir(mode=0o700)
        self.enterContext(patch.object(installer, "INSTALL_PARENT", self.parent))
        self.product = self.checkout / "onesa-drone"
        self.product.mkdir()
        self.pins = {}
        actual = Path(__file__).resolve().parents[2]
        for local, upstream in installer.ALLOWED.items():
            data = (actual / upstream).read_bytes()
            target = self.product / upstream
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            target.chmod(0o644)
            self.put(local, data)
            self.pins[local] = hashlib.sha256(data).hexdigest()
        app = self.product / "backend/app/main.py"
        app.parent.mkdir(parents=True)
        app.write_text("# Synthetic source fixture; never executed.\n")
        (self.checkout / "README.md").write_text("Synthetic independent root tree.\n")
        self.git("init", "--quiet")
        self.git("add", ".")
        self.git("-c", "user.name=Source Fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "--quiet", "-m", "Synthetic canonical source")
        commit = self.git("rev-parse", "HEAD").decode().strip()
        tree = self.git("rev-parse", "HEAD^{tree}").decode().strip()
        product_tree = self.git("rev-parse", "HEAD:onesa-drone").decode().strip()
        self.put("tool-source.tar", self.git("archive", "--format=tar", "HEAD:onesa-drone"))
        self.source = SourceFixture(owner, product="drone", branch="main")
        self.replacements = {"a" * 40: commit, "b" * 40: tree, "c" * 40: product_tree}
        self.source.source = self.translate(self.source.source)
        for name in self.source.manifests:
            self.source.manifests[name] = self.translate(self.source.manifests[name])
            self.source.repack(name)
        self.github = self.source.github
        self.github.api = self.api
        # The disposable GitHub API fixture has no owner credentials. Keep its
        # synthetic identity explicit; the real Actions refusal is tested below.
        self.github.owner = lambda: owner.OWNER
        for name, encoded in self.source.archives.items():
            self.put("source-artifacts/" + name + ".zip", base64.b64decode(encoded))
        self.target = self.parent / ("drone-canonical-" + tree)
        self.manifest = {**self.source.source, "files": self.pins.copy(),
                         "tool_source_sha256": owner.file_digest(self.bundle / "tool-source.tar")}
        self.policy = {"schema_version": 2, "components": {}, "toolchain": {
            "source_binding": copy.deepcopy(self.source.source), "source_commit": commit,
            "source_tree": tree, "source_sha256": self.manifest["tool_source_sha256"],
            "source_archives": archive_pins(self.source), "files": self.pins.copy(),
        }}
        for component in owner.DRONE_COMPONENTS:
            self.policy["components"][owner.CONSOLIDATED_REPOSITORY + ":drone:" + component] = {
                "qualification_attempt_limit": 1,
                "runners": {phase: {"path": str(self.target / "runners/oracle_drone.py"),
                                    "sha256": self.pins["runners/oracle_drone.py"], "timeout_seconds": 600}
                            for phase in owner.PHASES},
                "required_checks": {phase: sorted(checks) for phase, checks in owner.REQUIRED_CHECKS.items()},
            }
        self.seal()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.checkout), *args], stderr=subprocess.PIPE)

    def put(self, name, value):
        path = self.bundle / name
        path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        path.write_bytes(value)
        path.chmod(0o600)
        return path

    def seal(self):
        self.put("policy.json", owner.canonical(self.policy))
        self.manifest["policy_sha256"] = owner.file_digest(self.bundle / "policy.json")
        self.put("manifest.json", owner.canonical(self.manifest))
        self.pin = owner.file_digest(self.bundle / "manifest.json")

    def translate(self, value, *, reverse=False):
        replacements = ({right: left for left, right in self.replacements.items()}
                        if reverse else self.replacements)
        if isinstance(value, dict):
            return {self.translate(key, reverse=reverse): self.translate(item, reverse=reverse)
                    for key, item in value.items()}
        if isinstance(value, list):
            return [self.translate(item, reverse=reverse) for item in value]
        if isinstance(value, str):
            for left, right in replacements.items():
                value = value.replace(left, right)
        return value

    def api(self, path):
        prefix = self.source.prefix
        if path == prefix + "git/trees/" + self.source.source["product_source_tree"] + "?recursive=1":
            rows = []
            for line in self.git("ls-tree", "-r", "HEAD:onesa-drone").decode().splitlines():
                metadata, name = line.split("\t")
                mode, kind, sha = metadata.split()
                rows.append({"mode": mode, "type": kind, "sha": sha, "path": name})
            return {"sha": self.source.source["product_source_tree"], "truncated": False, "tree": rows}
        if path.startswith(prefix + "git/blobs/"):
            sha = path.rsplit("/", 1)[1]
            return {"sha": sha, "encoding": "base64",
                    "content": base64.b64encode(self.git("cat-file", "blob", sha)).decode()}
        return self.translate(self.source.api(self.translate(path, reverse=True)))

    def validate(self):
        return installer.validate(self.bundle, self.pin, self.github, uid=os.getuid())

    def materialize(self):
        manifest, target, payloads, ci = self.validate()
        target.mkdir(mode=0o700)
        for name, data in payloads.items():
            path = target / name
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod(0o600)
        return manifest, target, payloads, ci


class CanonicalInstallationTests(InstallFixture):
    def test_real_owner_refuses_actions_before_any_api_request(self):
        github = owner.GitHub("synthetic-owner-refusal")
        with (patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}),
              patch.object(github, "api") as api):
            with self.assertRaisesRegex(owner.Rejected, "Owner custody cannot run in Actions"):
                github.owner()
            api.assert_not_called()

    def test_exact_main_source_archive_and_bootstrap_blobs_are_independent_proofs(self):
        manifest, target, payloads, evidence = self.validate()
        self.assertNotEqual(manifest["source_tree"], manifest["product_source_tree"])
        self.assertEqual(target, self.target)
        self.assertEqual(set(installer.ALLOWED), owner.DRONE_INSTALL_FILES)
        self.assertEqual(owner.DRONE_INSTALL_FILES, runner.DRONE_INSTALL_FILES)
        self.assertEqual(len([name for name in payloads if name.startswith("source-artifacts/")]), 2)
        self.assertTrue(evidence[0]["verification_only"])
        self.assertFalse(evidence[0]["release_authorized"])
        self.assertFalse(target.exists())
        result = installer.install(self.bundle, self.pin, self.github, dry_run=True, uid=os.getuid())
        self.assertEqual(result["state"], "INSTALLATION_READY")
        self.assertEqual(result["provider_requests"], 0)
        self.assertFalse(result["release_authorized"])
        self.assertFalse(target.exists())

    def test_wrong_repository_product_root_subtree_and_branch_fail_closed(self):
        for key, value in [("repository_id", 1), ("repository", "DruHustle/onesa-drone"),
                           ("product", "robot"), ("source_path", "onesa-robot"), ("branch", "staging"),
                           ("source_tree", "f" * 40), ("product_source_tree", "e" * 40)]:
            original = self.manifest[key]
            self.manifest[key] = value
            self.seal()
            with self.subTest(key=key), self.assertRaises(owner.Rejected):
                self.validate()
            self.manifest[key] = original
        self.seal()

    def test_repinning_local_helper_cannot_replace_a_genuine_current_source_blob(self):
        name = "runners/hosted_probe.mjs"
        path = self.bundle / name
        path.write_bytes(path.read_bytes() + b"\n// synthetic unreviewed change\n")
        self.manifest["files"][name] = owner.file_digest(path)
        self.policy["toolchain"]["files"][name] = owner.file_digest(path)
        self.seal()
        with self.assertRaisesRegex(owner.Rejected, "current canonical source"):
            self.validate()

    def test_partial_profiles_relaxed_allowances_and_missing_helpers_are_refused(self):
        for mutation in ("partial", "allowance", "helper", "caller-authority"):
            original = copy.deepcopy(self.policy)
            if mutation == "partial":
                self.policy["components"].pop(owner.CONSOLIDATED_REPOSITORY + ":drone:frontend")
            elif mutation == "allowance":
                next(iter(self.policy["components"].values()))["qualification_attempt_limit"] = 2
            elif mutation == "helper":
                self.policy["toolchain"]["files"].pop("runners/oracle_drone_rollback.py")
            else:
                self.policy["release_authorized"] = True
            self.seal()
            with self.subTest(mutation=mutation), self.assertRaises(owner.Rejected):
                self.validate()
            self.policy = original
        self.seal()

    def test_ci_archive_tampering_alias_and_duplicate_manifest_are_refused(self):
        path = self.bundle / "source-artifacts" / (next(iter(self.source.archives)) + ".zip")
        original = path.read_bytes()
        path.write_bytes(original + b"changed")
        with self.assertRaises(owner.Rejected):
            self.validate()
        path.unlink()
        alias = self.put("unrelated.zip", original)
        path.symlink_to(alias)
        with self.assertRaises(owner.Rejected):
            self.validate()
        path.unlink()
        path.write_bytes(original)
        path.chmod(0o600)
        raw = (self.bundle / "manifest.json").read_bytes()
        self.put("manifest.json", raw[:-1] + b',"schema_version":2}')
        self.pin = owner.file_digest(self.bundle / "manifest.json")
        with self.assertRaisesRegex(owner.Rejected, "Duplicate"):
            self.validate()

    def test_install_is_immutable_and_never_creates_authority(self):
        actual_private = owner.private
        with patch.object(installer.os, "geteuid", return_value=0), \
             patch.dict(os.environ, {"SUDO_USER": "ubuntu"}, clear=True), \
             patch.object(owner, "private", side_effect=lambda path, **kwargs: actual_private(
                 path, **{**kwargs, "uid": os.getuid()})):
            result = installer.install(self.bundle, self.pin, self.github, uid=0)
            self.assertEqual(result["state"], "INSTALLED_NOT_COMMISSIONED")
            self.assertEqual(result["provider_requests"], 0)
            self.assertFalse(result["release_authorized"])
            self.assertFalse(any((self.target / name).exists() for name in ("signing.pem", "records.sqlite", "trust.json")))
            before = {str(path.relative_to(self.target)): path.read_bytes() for path in self.target.rglob("*") if path.is_file()}
            with self.assertRaisesRegex(owner.Rejected, "Existing immutable"):
                installer.install(self.bundle, self.pin, self.github, uid=0)
            after = {str(path.relative_to(self.target)): path.read_bytes() for path in self.target.rglob("*") if path.is_file()}
            self.assertEqual(before, after)

    def test_archive_reconstruction_rejects_foreign_tree_alias_duplicate_and_link(self):
        path = self.bundle / "tool-source.tar"
        for parser in (owner.source_inventory, runner.source_inventory):
            self.assertIn("backend/app/main.py", parser(path, self.source.source))
            with self.assertRaises(ValueError):
                parser(path, {**self.source.source, "product_source_tree": "f" * 40})
            for name, kind in [("../escape", tarfile.REGTYPE), ("/absolute", tarfile.REGTYPE),
                               ("alias", tarfile.SYMTYPE), ("duplicate", tarfile.REGTYPE)]:
                forged = self.bundle / "forged.tar"
                with tarfile.open(forged, "w") as archive:
                    member = tarfile.TarInfo(name)
                    member.type = kind
                    member.linkname = "unrelated"
                    archive.addfile(member, io.BytesIO(b""))
                    if name == "duplicate":
                        archive.addfile(member, io.BytesIO(b""))
                with self.subTest(parser=parser.__module__, name=name), self.assertRaises(ValueError):
                    parser(forged, self.source.source)
        self.assertFalse((self.root / "escape").exists())

    def test_interrupted_installation_retains_its_reserved_target_without_retry(self):
        actual_private = owner.private
        with patch.object(installer.os, "geteuid", return_value=0), \
             patch.dict(os.environ, {"SUDO_USER": "ubuntu"}, clear=True), \
             patch.object(owner, "private", side_effect=lambda path, **kwargs: actual_private(
                 path, **{**kwargs, "uid": os.getuid()})), \
             patch.object(installer.os, "fsync", side_effect=OSError("synthetic interrupted storage")):
            with self.assertRaisesRegex(owner.Rejected, "retain and inspect"):
                installer.install(self.bundle, self.pin, self.github, uid=0)
        self.assertTrue(self.target.is_dir())
        self.assertTrue(any(path.is_file() for path in self.target.rglob("*")))
        self.assertFalse((self.target / "installation.json").exists())
        with self.assertRaisesRegex(owner.Rejected, "Existing immutable"):
            installer.install(self.bundle, self.pin, self.github, dry_run=True, uid=os.getuid())


class CanonicalRuntimeTests(InstallFixture):
    def setUp(self):
        super().setUp()
        self.legacy = legacy = plan_fixture.PlanTests()
        legacy.setUp()
        self.addCleanup(legacy.doCleanups)
        self.plan = legacy.plan
        self.binding = legacy.binding
        self.binding.update(self.source.source)
        self.binding["source_sha256"] = self.manifest["tool_source_sha256"]
        self.plan["source_binding"] = copy.deepcopy(self.source.source)
        self.plan["source_archive"] = str(self.bundle / "tool-source.tar")
        self.plan["transport_guard"] = str(self.target / "runners/vercel_transport_guard.cjs")
        self.plan["bindings"]["frontend"] = {**self.binding, "component": "frontend"}
        path = Path(self.plan["build_manifests"]["backend"])
        native = json.loads(path.read_bytes())
        native.update(repository=owner.CONSOLIDATED_REPOSITORY, source_path="onesa-drone",
                      source_commit=self.binding["candidate_commit"], source_tree=self.binding["source_tree"],
                      product_source_tree=self.binding["product_source_tree"], component="backend", mode="simulation",
                      verification_only=True, release_authorized=False)
        path.write_bytes(owner.canonical(native))
        legacy.rebind_native()

    def test_canonical_runtime_keeps_paired_source_simulation_and_native_artifact_checks(self):
        runner.validate_plan(self.plan, self.binding)
        for key, value in [("repository", "DruHustle/onesa-drone"), ("source_path", "onesa-robot"),
                           ("product_source_tree", "f" * 40), ("release_authorized", True), ("mode", "physical")]:
            path = Path(self.plan["build_manifests"]["backend"])
            original = path.read_bytes()
            native = json.loads(original)
            native[key] = value
            path.write_bytes(owner.canonical(native))
            self.legacy.rebind_native()
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "provenance"):
                runner.validate_plan(self.plan, self.binding)
            path.write_bytes(original)
            self.legacy.rebind_native()

    def test_a_missing_or_cross_product_frontend_binding_cannot_borrow_backend_source(self):
        original = self.plan["bindings"]["frontend"]
        for value in (None, {**original, "product": "robot"}, {**original, "candidate_commit": "f" * 40}):
            if value is None:
                self.plan["bindings"].pop("frontend")
            else:
                self.plan["bindings"]["frontend"] = value
            with self.assertRaises(ValueError):
                runner.validate_plan(self.plan, self.binding)
            self.plan["bindings"]["frontend"] = original

    def test_runtime_custody_requires_exact_immutable_tools_and_installed_ci_bytes(self):
        self.materialize()
        self.plan["tool_sha256"] = {str(self.target / name): pin for name, pin in self.pins.items()}
        with patch.object(runner, "CANONICAL_INSTALL_PARENT", self.parent), \
             patch.object(runner, "__file__", str(self.target / "runners/oracle_drone.py")):
            runner.canonical_custody(self.plan, self.binding, self.policy, self.target / "oracle_owner.py")
            path = self.target / "runners/hosted_probe.mjs"
            path.write_bytes(path.read_bytes() + b"\n// changed helper\n")
            with self.assertRaisesRegex(ValueError, "helper changed"):
                runner.canonical_custody(self.plan, self.binding, self.policy, self.target / "oracle_owner.py")
            pin = owner.file_digest(path)
            self.policy["toolchain"]["files"]["runners/hosted_probe.mjs"] = pin
            self.plan["tool_sha256"][str(path)] = pin
            with self.assertRaisesRegex(ValueError, "product source"):
                runner.canonical_custody(self.plan, self.binding, self.policy, self.target / "oracle_owner.py")

    def test_genuine_helper_pins_cannot_select_a_different_private_transport_guard(self):
        self.materialize()
        self.plan["tool_sha256"] = {str(self.target / name): pin for name, pin in self.pins.items()}
        other = self.root / "different-guard.cjs"
        other.write_bytes((self.target / "runners/vercel_transport_guard.cjs").read_bytes())
        other.chmod(0o600)
        with patch.object(runner, "CANONICAL_INSTALL_PARENT", self.parent), \
             patch.object(runner, "__file__", str(self.target / "runners/oracle_drone.py")):
            runner.canonical_custody(self.plan, self.binding, self.policy, self.target / "oracle_owner.py")
            self.plan["transport_guard"] = str(other)
            with self.assertRaisesRegex(ValueError, "selected transport guard"):
                runner.canonical_custody(self.plan, self.binding, self.policy, self.target / "oracle_owner.py")

    def test_canonical_invocation_selects_the_separate_fixed_plan(self):
        selected = self.root / "canonical-plan.json"
        legacy = self.root / "legacy-plan.json"
        selected.write_bytes(owner.canonical({"evidence_root": str(self.root), "selected": "canonical"}))
        legacy.write_bytes(owner.canonical({"evidence_root": str(self.root), "selected": "legacy"}))
        with patch.object(runner, "CANONICAL_PLAN", selected), patch.object(runner, "PLAN", legacy), \
             patch.object(runner.os, "geteuid", return_value=0), patch.dict(os.environ, {}, clear=True), \
             patch.object(runner, "validate_plan") as validate, \
             patch.object(runner.Runner, "check_context", return_value={}):
            canonical = runner.Runner(self.binding, {}, "operations")
            self.assertEqual(canonical.plan["selected"], "canonical")
            self.assertEqual(validate.call_args.args[1], self.binding)
            original = runner.Runner({**self.binding, "repository": "DruHustle/onesa-drone"}, {}, "operations")
            self.assertEqual(original.plan["selected"], "legacy")

    def test_frontend_package_identity_must_match_the_full_canonical_binding(self):
        artifact = self.root / "frontend-package"
        static = artifact / ".vercel/output/static"
        static.mkdir(parents=True)
        (static / "index.html").write_text("synthetic frontend")
        config = artifact / ".vercel/output/config.json"
        config.write_text("{}")
        files = {"index.html": runner.digest(static / "index.html")}
        native = self.root / "frontend-native.json"
        native.write_bytes(owner.canonical({"files": files}))
        value = {
            "source_commit": self.binding["candidate_commit"], "environment": "staging",
            "project_id": "prj_synthetic", "backend_origin": runner.ORIGINS["staging"][1],
            "source_binding": copy.deepcopy(self.source.source), "files": files,
            "routing_sha256": runner.digest(config),
        }
        self.plan["vercel_project_id"] = "prj_synthetic"
        self.plan["slots"]["staging"]["frontend_artifact"] = str(artifact)
        self.plan["build_manifests"]["frontend"] = str(native)
        instance = runner.Runner.__new__(runner.Runner)
        instance.plan, instance.binding = self.plan, {**self.binding, "component": "frontend"}
        manifest = artifact / "release.json"
        manifest.write_bytes(owner.canonical(value))
        self.assertEqual(instance.frontend_files("staging"), artifact)
        for source in (None, {**self.source.source, "product": "robot"},
                       {**self.source.source, "source_tree": "f" * 40}):
            changed = {**value, "source_binding": source}
            manifest.write_bytes(owner.canonical(changed))
            with self.assertRaisesRegex(ValueError, "package source"):
                instance.frontend_files("staging")


class CanonicalStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        store_fixture.OwnerStoreTests.setUpClass()

    def setUp(self):
        self.fixture = fixture = store_fixture.OwnerStoreTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.source = source = SourceFixture(owner, product="drone", branch="main")
        source.github.owner = fixture.ci.owner
        fixture.binding.update(source.source, component="backend")
        native_profile = next(iter(fixture.policy["components"].values()))
        native_profile["qualification_attempt_limit"] = 1
        fixture.policy = {"schema_version": 2, "components": {
            owner.CONSOLIDATED_REPOSITORY + ":drone:" + name: copy.deepcopy(native_profile)
            for name in owner.DRONE_COMPONENTS
        }, "toolchain": {
            "source_binding": copy.deepcopy(source.source), "source_commit": source.source["candidate_commit"],
            "source_tree": source.source["source_tree"], "source_sha256": fixture.binding["source_sha256"],
            "source_archives": archive_pins(source), "files": {name: "a" * 64 for name in owner.DRONE_INSTALL_FILES},
        }}
        (fixture.root / "policy.json").write_bytes(owner.canonical(fixture.policy))
        trust = json.loads((fixture.root / "trust.json").read_bytes())
        trust["policy_sha256"] = owner.file_digest(fixture.root / "policy.json")
        (fixture.root / "trust.json").write_bytes(owner.canonical(trust))
        fixture.commission_fixture()
        install = fixture.root / "installed"
        install.mkdir(mode=0o700)
        (install / "oracle_owner.py").write_bytes(Path(owner.__file__).read_bytes())
        (install / "oracle_owner.py").chmod(0o600)
        artifacts = install / "source-artifacts"
        artifacts.mkdir(mode=0o700)
        for name, data in source.archives.items():
            path = artifacts / (name + ".zip")
            path.write_bytes(base64.b64decode(data))
            path.chmod(0o600)
        self.enterContext(patch.object(owner, "__file__", str(install / "oracle_owner.py")))
        fixture.store.db.close()
        fixture.ci = source.github
        fixture.store = self.store = fixture.open()
        self.addCleanup(self.store.db.close)

    def test_signed_context_uses_canonical_product_scope_and_cannot_be_renewed(self):
        context = self.store.issue_context(self.fixture.binding)
        self.assertEqual(context["record"]["binding"], self.fixture.binding)
        scope = self.store.db.execute("SELECT scope FROM records WHERE id=?", (context["record"]["id"],)).fetchone()[0]
        self.assertEqual(scope, "DruHustle/onesa-ug:drone:backend")
        self.assertFalse(context["record"]["details"]["ci"][0]["release_authorized"])
        with self.assertRaisesRegex(owner.Rejected, "allowance exhausted"):
            self.store.issue_context(self.fixture.binding)

    def test_changed_source_archive_blocks_reserved_context_before_any_hosted_runner(self):
        context = self.store.issue_context(self.fixture.binding)["record"]["id"]
        path = Path(owner.__file__).parent / "source-artifacts" / (next(iter(self.source.archives)) + ".zip")
        path.write_bytes(path.read_bytes() + b"changed")
        with patch.object(self.store, "runner") as hosted, self.assertRaisesRegex(owner.Rejected, "archive changed"):
            self.store.qualify(context)
        hosted.assert_not_called()
        state = self.store.db.execute("SELECT state FROM contexts WHERE id=?", (context,)).fetchone()[0]
        self.assertEqual(state, "reserved")

    def test_legacy_policy_cannot_authorize_a_relabelled_canonical_binding(self):
        legacy = {"components": {"DruHustle/onesa-drone:backend": next(iter(self.fixture.policy["components"].values()))}}
        with self.assertRaises(owner.Rejected):
            owner.binding_valid(self.fixture.binding, legacy)


if __name__ == "__main__":
    unittest.main()
