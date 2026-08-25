#!/bin/bash
# Bootstraps Ansible on a freshly deployed Debian VPS and runs the playbook
# against localhost. Run this from inside the git checkout, as root (or a
# user that can sudo), after cloning/pulling the repo onto the box:
#
#   git clone <repo-url> /opt/sectortrace/app
#   cd /opt/sectortrace/app/deploy/ansible
#   ./ansible-install.sh
#
# On a first run it asks for the handful of values it needs, generates the
# database passwords itself, and writes an ansible-vault encrypted
# group_vars/all/vault.yml. On later runs it finds that file already
# configured and goes straight to the playbook.
#
#   ./ansible-install.sh --reconfigure   # re-run the setup questions
#
# Anything else you pass is handed to ansible-playbook, so
# `./ansible-install.sh --check` does a dry run.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this as root (or via sudo) — it installs packages and writes to /opt." >&2
    exit 1
fi

cd "$(dirname "$0")"

VAULT_FILE="group_vars/all/vault.yml"
# Sorts after vars.yml, and Ansible loads group_vars/all/* alphabetically
# with later files winning — so this overrides the tracked defaults without
# making the tracked file dirty and conflicting on the next `git pull`.
LOCAL_FILE="group_vars/all/zz-local.yml"

RECONFIGURE=0
PLAYBOOK_ARGS=()
for arg in "$@"; do
    if [ "$arg" = "--reconfigure" ]; then
        RECONFIGURE=1
    else
        PLAYBOOK_ARGS+=("$arg")
    fi
done

# --- Ansible itself -----------------------------------------------------------

if ! command -v ansible-playbook >/dev/null 2>&1; then
    echo "==> Installing Ansible"
    apt-get update
    apt-get install -y --no-install-recommends ansible git ca-certificates
fi

echo "==> Ensuring required Ansible collections are present"
ansible-galaxy collection install -r requirements.yml

# --- Helpers -------------------------------------------------------------------

# Passwords are interpolated into postgresql://user:PASSWORD@host URLs. A
# generated '@', '/', ':', '#' or '?' would silently split the URL somewhere
# it should not, and the failure surfaces as a confusing connection error
# rather than as anything naming the password. Alphanumeric only: 32 of
# those is ~190 bits, far more than the character-class variety would buy.
generate_password() {
    # `head -c` closing the pipe early sends SIGPIPE to tr, which is the
    # intended way for this to end — but `set -o pipefail` at the top of the
    # script would read it as the pipeline failing. Turn it off for this one
    # subshell rather than dropping it for the whole script.
    local raw
    raw="$(set +o pipefail; LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 32)"
    if [ ${#raw} -ne 32 ]; then
        echo "Could not generate a password from /dev/urandom." >&2
        exit 1
    fi
    printf '%s' "$raw"
}

# YAML single-quoted scalars escape a quote by doubling it. Everything the
# wizard writes goes through this, so a password or key containing a quote
# cannot break the file.
yaml_quote() {
    printf "'%s'" "$(printf '%s' "$1" | sed "s/'/''/g")"
}

ask() {  # ask <prompt> <default>; answer on stdout
    local prompt="$1" default="${2:-}" reply
    if [ -n "$default" ]; then
        read -r -p "$prompt [$default]: " reply </dev/tty
        printf '%s' "${reply:-$default}"
    else
        read -r -p "$prompt: " reply </dev/tty
        printf '%s' "$reply"
    fi
}

ask_secret() {  # ask_secret <prompt>; answer on stdout, not echoed
    local prompt="$1" reply
    read -r -s -p "$prompt: " reply </dev/tty
    printf '\n' >/dev/tty
    printf '%s' "$reply"
}

ask_yes_no() {  # ask_yes_no <prompt> <default y|n>
    local prompt="$1" default="$2" reply
    local hint="y/N"; [ "$default" = "y" ] && hint="Y/n"
    read -r -p "$prompt [$hint]: " reply </dev/tty
    reply="${reply:-$default}"
    [[ "$reply" =~ ^[Yy] ]]
}

vault_is_encrypted() {
    [ -f "$VAULT_FILE" ] && head -n 1 "$VAULT_FILE" 2>/dev/null | grep -q '^\$ANSIBLE_VAULT'
}

# A plaintext vault.yml counts as configured only if the values that have no
# usable default are actually filled in.
vault_is_configured() {
    vault_is_encrypted && return 0
    [ -f "$VAULT_FILE" ] || return 1
    local key
    for key in vault_contact_email vault_postgres_app_password \
               vault_postgres_reader_password vault_neo4j_password; do
        grep -qE "^${key}:[[:space:]]*[\"']?[^\"'[:space:]]" "$VAULT_FILE" || return 1
    done
    return 0
}

# --- The setup questions --------------------------------------------------------

run_setup_wizard() {
    cat <<'BANNER'

================================================================
 SectorTrace VPS setup
================================================================
This asks for the few values the playbook cannot guess, then
writes an encrypted group_vars/all/vault.yml. Press Enter to
accept a default shown in brackets.

BANNER

    # --- Domain and contact ---
    echo "--- Domain -----------------------------------------------------"
    echo "The A record you are pointing at this VPS. It must already resolve"
    echo "here before the playbook runs: Caddy asks Let's Encrypt for a"
    echo "certificate on first start, and the challenge fails otherwise."
    echo "(Check with: dig +short <domain>)"
    echo
    local domain=""
    while [ -z "$domain" ]; do
        domain="$(ask 'Domain')"
        [ -z "$domain" ] && echo "  A domain is required." >&2
    done

    echo
    echo "--- Contact email ----------------------------------------------"
    echo "Sent in the User-Agent of every request this pipeline makes, so a"
    echo "site operator can reach you about it, and given to Let's Encrypt"
    echo "for expiry notices. The pipeline refuses to start without it."
    echo
    local contact_email=""
    while [ -z "$contact_email" ]; do
        contact_email="$(ask 'Contact email')"
        case "$contact_email" in
            *@*.*) ;;
            *) echo "  That does not look like an email address." >&2; contact_email="" ;;
        esac
    done

    # --- Database passwords ---
    echo
    echo "--- Database passwords -----------------------------------------"
    local pg_app pg_reader neo4j_pw
    if ask_yes_no "Generate the PostgreSQL and Neo4j passwords automatically?" "y"; then
        pg_app="$(generate_password)"
        pg_reader="$(generate_password)"
        neo4j_pw="$(generate_password)"
        echo "  Generated three 32-character passwords."
        echo "  You never need to type them: they go into the encrypted vault,"
        echo "  and from there into .env on this box."
    else
        echo
        echo "  Note: these are interpolated into postgresql:// URLs, so avoid"
        echo "  @ / : # ? in them — those characters split a URL."
        echo
        pg_app="$(ask_secret '  PostgreSQL sectortrace_app password')"
        pg_reader="$(ask_secret '  PostgreSQL sectortrace_reader password')"
        neo4j_pw="$(ask_secret '  Neo4j password')"
    fi

    # --- Raw archive ---
    echo
    echo "--- Raw archive (S3) -------------------------------------------"
    echo "Where archived source bytes live. Leave this off to use local disk"
    echo "under data/raw instead; you can add it later by re-running with"
    echo "--reconfigure."
    echo
    local s3_bucket="" s3_endpoint="" s3_region="ams" s3_style="virtual"
    local s3_key="" s3_secret=""
    if ask_yes_no "Use an S3-compatible bucket for the raw archive?" "n"; then
        s3_bucket="$(ask '  Bucket')"
        s3_endpoint="$(ask '  Endpoint (e.g. s3.example.com)')"
        s3_region="$(ask '  Region' 'ams')"
        s3_style="$(ask '  URL style (virtual|path)' 'virtual')"
        s3_key="$(ask '  Access key')"
        s3_secret="$(ask_secret '  Secret key')"
    fi

    # --- Module API keys ---
    echo
    echo "--- Module API keys --------------------------------------------"
    echo "All optional. A module that needs a missing key fails with a message"
    echo "naming it, rather than half-collecting; everything else still runs."
    echo
    local charity="" companies="" cqc="" kaggle_user="" kaggle_key=""
    if ask_yes_no "Enter API keys now?" "n"; then
        charity="$(ask '  Charity Commission API key')"
        companies="$(ask '  Companies House API key')"
        cqc="$(ask '  CQC subscription key')"
        kaggle_user="$(ask '  Kaggle username')"
        kaggle_key="$(ask '  Kaggle key')"
    fi

    # --- Vault password ---
    echo
    echo "--- Vault password ---------------------------------------------"
    echo "Encrypts the file holding everything above. You will need it again"
    echo "to re-run this playbook, so put it in your password manager now."
    echo
    local vault_pw vault_pw2
    while true; do
        vault_pw="$(ask_secret 'Vault password')"
        if [ ${#vault_pw} -lt 8 ]; then
            echo "  Use at least 8 characters." >&2
            continue
        fi
        vault_pw2="$(ask_secret 'Confirm vault password')"
        [ "$vault_pw" = "$vault_pw2" ] && break
        echo "  They do not match. Try again." >&2
    done

    # --- Write the files ---
    umask 077

    cat > "$VAULT_FILE" <<EOF
---
# Written by ansible-install.sh. Edit with:
#   ansible-vault edit group_vars/all/vault.yml
# or re-run: ./ansible-install.sh --reconfigure

vault_contact_email: $(yaml_quote "$contact_email")

vault_postgres_app_password: $(yaml_quote "$pg_app")
vault_postgres_reader_password: $(yaml_quote "$pg_reader")

vault_neo4j_password: $(yaml_quote "$neo4j_pw")

vault_archive_s3_bucket: $(yaml_quote "$s3_bucket")
vault_archive_s3_endpoint: $(yaml_quote "$s3_endpoint")
vault_archive_s3_region: $(yaml_quote "$s3_region")
vault_archive_s3_url_style: $(yaml_quote "$s3_style")
vault_archive_s3_access_key: $(yaml_quote "$s3_key")
vault_archive_s3_secret: $(yaml_quote "$s3_secret")

vault_charity_commission_api_key: $(yaml_quote "$charity")
vault_companies_house_api_key: $(yaml_quote "$companies")
vault_cqc_subscription_key: $(yaml_quote "$cqc")
vault_kaggle_username: $(yaml_quote "$kaggle_user")
vault_kaggle_key: $(yaml_quote "$kaggle_key")
EOF
    chmod 600 "$VAULT_FILE"

    cat > "$LOCAL_FILE" <<EOF
---
# Written by ansible-install.sh. Not tracked in git, and loaded after
# vars.yml (group_vars/all/* is read alphabetically, later files win), so
# what is here overrides the tracked defaults without making vars.yml dirty.
domain: $(yaml_quote "$domain")
EOF
    chmod 644 "$LOCAL_FILE"

    # The password file is how we avoid asking for the same passphrase twice
    # in one run — once to encrypt, once for the playbook. Removed on exit,
    # including on Ctrl-C.
    VAULT_PW_FILE="$(mktemp)"
    chmod 600 "$VAULT_PW_FILE"
    printf '%s\n' "$vault_pw" > "$VAULT_PW_FILE"

    ansible-vault encrypt --vault-password-file "$VAULT_PW_FILE" "$VAULT_FILE"
    echo
    echo "==> Wrote encrypted $VAULT_FILE and $LOCAL_FILE"
    echo
}

# --- Decide whether to run it ----------------------------------------------------

VAULT_PW_FILE=""
cleanup() { [ -n "$VAULT_PW_FILE" ] && rm -f "$VAULT_PW_FILE"; }
trap cleanup EXIT INT TERM

if [ "$RECONFIGURE" -eq 1 ]; then
    if [ -f "$VAULT_FILE" ]; then
        # Deliberately NOT beside the original. A backup left in
        # group_vars/all/ is a secrets file one `git add` away from being
        # committed, and it would not match the .gitignore rule that covers
        # vault.yml itself.
        mkdir -p .vault-backups
        chmod 700 .vault-backups
        BACKUP=".vault-backups/vault-$(date -u +%Y%m%dT%H%M%SZ).yml"
        cp -p "$VAULT_FILE" "$BACKUP"
        chmod 600 "$BACKUP"
        echo "==> Kept the previous vault as $BACKUP"
        echo "    (still encrypted with its OLD password)"
    fi
    run_setup_wizard
elif vault_is_configured; then
    echo "==> $VAULT_FILE is already configured"
    vault_is_encrypted || echo "    (it is NOT encrypted — run: ansible-vault encrypt $VAULT_FILE)"
    echo "    Re-run with --reconfigure to change any of it."
else
    [ -f "$VAULT_FILE" ] && echo "==> $VAULT_FILE exists but is incomplete; asking again"
    run_setup_wizard
fi

# --- Run the playbook -------------------------------------------------------------

echo "==> Running the playbook"
if [ -n "$VAULT_PW_FILE" ]; then
    # Just created the vault in this run: reuse the passphrase rather than
    # asking for it a second time.
    ansible-playbook site.yml --vault-password-file "$VAULT_PW_FILE" "${PLAYBOOK_ARGS[@]+"${PLAYBOOK_ARGS[@]}"}"
elif vault_is_encrypted; then
    ansible-playbook site.yml --ask-vault-pass "${PLAYBOOK_ARGS[@]+"${PLAYBOOK_ARGS[@]}"}"
else
    ansible-playbook site.yml "${PLAYBOOK_ARGS[@]+"${PLAYBOOK_ARGS[@]}"}"
fi
