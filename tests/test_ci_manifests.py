"""Provenance uses real disposable Git objects without contacting GitHub or Docker."""

import subprocess

import pytest

from scripts.ci_manifests import source_binding


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def repository(tmp_path, *, nested=False, folder="onesa-drone", owner="DruHustle"):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    product = checkout / folder if nested else checkout
    product.mkdir(exist_ok=True)
    (product / "source.py").write_text("simulation_only = True\n")
    git(checkout, "init", "--quiet")
    git(checkout, "config", "user.name", "Synthetic provenance fixture")
    git(checkout, "config", "user.email", "fixture@example.test")
    name = "onesa-ug" if nested else "onesa-drone"
    git(checkout, "remote", "add", "origin", f"https://github.com/{owner}/{name}.git")
    git(checkout, "add", ".")
    git(checkout, "commit", "--quiet", "-m", "Synthetic source")
    return checkout, product


@pytest.mark.parametrize("nested", [False, True])
def test_manifest_source_preserves_exact_repository_commit_and_tree(tmp_path, monkeypatch, nested):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    checkout, product = repository(tmp_path, nested=nested)
    binding = source_binding(product)
    assert binding["repository"] == ("DruHustle/onesa-ug" if nested else "DruHustle/onesa-drone")
    assert binding["source_commit"] == git(checkout, "rev-parse", "HEAD")
    assert binding["source_tree"] == git(checkout, "rev-parse", "HEAD^{tree}")
    if nested:
        assert binding["source_path"] == "onesa-drone"
        assert binding["product_source_tree"] == git(checkout, "rev-parse", "HEAD:onesa-drone")
        assert binding["product_source_tree"] != binding["source_tree"]
        assert binding["verification_only"] is True
        assert binding["release_authorized"] is False
    else:
        assert set(binding) == {"repository", "source_commit", "source_tree"}


@pytest.mark.parametrize("failure", ["foreign-origin", "wrong-workflow-repository", "wrong-product-path"])
def test_mislabelled_checkout_cannot_publish_a_provenance_manifest(tmp_path, monkeypatch, failure):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    _, product = repository(
        tmp_path,
        nested=True,
        owner="synthetic-other-owner" if failure == "foreign-origin" else "DruHustle",
        folder="wrong-product" if failure == "wrong-product-path" else "onesa-drone",
    )
    if failure == "wrong-workflow-repository":
        monkeypatch.setenv("GITHUB_REPOSITORY", "DruHustle/onesa-drone")
    with pytest.raises(SystemExit):
        source_binding(product)


@pytest.mark.parametrize("untracked", [False, True])
def test_uncommitted_product_changes_cannot_claim_the_checked_commit(tmp_path, monkeypatch, untracked):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    _, product = repository(tmp_path, nested=True)
    (product / ("new.py" if untracked else "source.py")).write_text("changed = True\n")
    with pytest.raises(SystemExit, match="uncommitted changes"):
        source_binding(product)
