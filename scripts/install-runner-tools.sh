#!/usr/bin/env bash
set -euo pipefail

readonly TERRAFORM_VERSION="1.16.6"
readonly KUBECTL_VERSION="v1.37.1"
readonly HELM_VERSION="v4.3.1"

if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
  echo "This script supports Linux x86_64 only." >&2
  exit 1
fi

sudo -n true

work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT
cd "$work_dir"

download() {
  curl --fail --silent --show-error --location \
    --retry 3 --connect-timeout 15 --max-time 300 \
    --output "$2" "$1"
}

# Terraform
terraform_archive="terraform_${TERRAFORM_VERSION}_linux_amd64.zip"
terraform_base="https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}"

download "${terraform_base}/${terraform_archive}" "$terraform_archive"
download "${terraform_base}/terraform_${TERRAFORM_VERSION}_SHA256SUMS" \
  terraform-SHA256SUMS

awk -v file="$terraform_archive" '$2 == file {print}' \
  terraform-SHA256SUMS > terraform-checksum

test -s terraform-checksum
sha256sum -c terraform-checksum

unzip -q "$terraform_archive" -d terraform-extracted
sudo -n install -m 0755 terraform-extracted/terraform \
  /usr/local/bin/terraform

# kubectl
kubectl_base="https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64"

download "${kubectl_base}/kubectl" kubectl
download "${kubectl_base}/kubectl.sha256" kubectl.sha256

printf '%s  kubectl\n' "$(tr -d '[:space:]' < kubectl.sha256)" \
  | sha256sum -c -

sudo -n install -m 0755 kubectl /usr/local/bin/kubectl

# Helm
helm_archive="helm-${HELM_VERSION}-linux-amd64.tar.gz"

download "https://get.helm.sh/${helm_archive}" "$helm_archive"
download "https://get.helm.sh/${helm_archive}.sha256sum" \
  "${helm_archive}.sha256sum"

sha256sum -c "${helm_archive}.sha256sum"

mkdir helm-extracted
tar xzf "$helm_archive" -C helm-extracted

sudo -n install -m 0755 helm-extracted/linux-amd64/helm \
  /usr/local/bin/helm

# Verify installations
terraform version
kubectl version --client
helm version --short