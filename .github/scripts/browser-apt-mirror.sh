#!/usr/bin/env bash
set -euo pipefail

# GitHub's Ubuntu image uses either a deb822 file or the legacy sources list.
sources=()
for file in /etc/apt/sources.list /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources; do
  [[ ! -f "$file" ]] || sources+=("$file")
done
(( ${#sources[@]} )) || exit 0
# Modern hosted images direct APT to this local mirror list from a source stanza.
mirror_list=/etc/apt/apt-mirrors.txt
if [[ -f "$mirror_list" ]] && grep -Fq "mirror+file:$mirror_list" "${sources[@]}"; then
  sources+=("$mirror_list")
fi

failed_hosts=()
for host in azure.archive.ubuntu.com archive.ubuntu.com security.ubuntu.com us-east-2.ec2.archive.ubuntu.com; do
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
  echo "Using the Ubuntu-signed mirror for $host"
  for file in "${sources[@]}"; do
    grep -Fq "://$host/ubuntu" "$file" || continue
    sudo sed -Ei "s#https?://$escaped/ubuntu([/[:space:]]|$)#$mirror\\1#g" "$file"
  done
done
