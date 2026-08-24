#!/bin/bash
# Bootstraps Ansible on a freshly deployed Debian VPS and runs the playbook
# against localhost. Run this from inside the git checkout, as root (or a
# user that can sudo), after cloning/pulling the repo onto the box:
#
#   git clone <repo-url> /opt/sectortrace/app
#   cd /opt/sectortrace/app/deploy/ansible
#   cp group_vars/all/vault.yml.example group_vars/all/vault.yml
#   $EDITOR group_vars/all/vault.yml     # fill in passwords/keys
#   ansible-vault encrypt group_vars/all/vault.yml
#   ./ansible-install.sh
#
# Re-running it (after a `git pull`) is safe: every task is idempotent, and
# it is how you pick up playbook or docker-compose changes on an existing box.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this as root (or via sudo) — it installs packages and writes to /opt." >&2
    exit 1
fi

cd "$(dirname "$0")"

if ! command -v ansible-playbook >/dev/null 2>&1; then
    echo "==> Installing Ansible"
    apt-get update
    apt-get install -y --no-install-recommends ansible git ca-certificates
fi

echo "==> Ensuring required Ansible collections are present"
ansible-galaxy collection install -r requirements.yml

if [ ! -f group_vars/all/vault.yml ]; then
    echo "group_vars/all/vault.yml is missing." >&2
    echo "Copy group_vars/all/vault.yml.example, fill it in, and encrypt it:" >&2
    echo "  cp group_vars/all/vault.yml.example group_vars/all/vault.yml" >&2
    echo "  \$EDITOR group_vars/all/vault.yml" >&2
    echo "  ansible-vault encrypt group_vars/all/vault.yml" >&2
    exit 1
fi

echo "==> Running the playbook (you'll be asked for the vault password)"
ansible-playbook site.yml --ask-vault-pass "$@"
