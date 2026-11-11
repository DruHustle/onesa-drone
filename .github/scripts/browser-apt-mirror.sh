#!/usr/bin/env bash
set -euo pipefail

# GitHub's Ubuntu image uses either a deb822 file or the legacy sources list.
sources=()
for file in /etc/apt/sources.list.d/ubuntu.sources /etc/apt/sources.list; do
  [[ ! -f "$file" ]] || sources+=("$file")
done
(( ${#sources[@]} )) || exit 0

failed_hosts=()
for host in azure.archive.ubuntu.com archive.ubuntu.com security.ubuntu.com; do
  if grep -Fq "://$host/ubuntu" "${sources[@]}" && ! getent ahosts "$host" >/dev/null; then
    failed_hosts+=("$host")
  fi
done
(( ${#failed_hosts[@]} )) || exit 0

. /etc/os-release
mirror=https://mirrors.edge.kernel.org/ubuntu
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
for suffix in '' -updates -backports -security; do
  suite="${VERSION_CODENAME:?}$suffix"
  curl --fail --silent --show-error --max-time 30 "$mirror/dists/$suite/InRelease" -o "$work/$suite.in"
  gpgv --keyring /usr/share/keyrings/ubuntu-archive-keyring.gpg --output "$work/$suite.release" "$work/$suite.in"
  grep -Fxq 'Origin: Ubuntu' "$work/$suite.release"
  grep -Fxq "Suite: $suite" "$work/$suite.release"
done
for host in "${failed_hosts[@]}"; do
  # Only replace the archive URI; keep the image's components, suites and Signed-By settings.
  escaped=${host//./\\.}
  sudo sed -Ei "s#https?://$escaped/ubuntu([/[:space:]]|$)#$mirror\\1#g" "${sources[@]}"
done
