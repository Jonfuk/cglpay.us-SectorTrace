#!/bin/bash
# Bootstraps Ansible on a freshly deployed Debian VPS and runs the mirror
# playbook against localhost. Run this from inside the git checkout, as root
# (or a user that can sudo), after cloning/pulling the repo onto the box:
#
#   git clone <repo-url> /opt/sectortrace/app
#   cd /opt/sectortrace/app/deploy/ansible-mirror
#   ./ansible-mirror.sh
#
# It is ansible-install.sh with one extra subject: the deployment this box
# is a mirror OF. On a first run it asks for that, generates this box's own
# database passwords itself, and writes an ansible-vault encrypted
# group_vars/all/vault.yml. On later runs it finds that file already
# configured and goes straight to the playbook.
#
#   ./ansible-mirror.sh --reconfigure   # re-run the setup questions
#
# Anything else you pass is handed to ansible-playbook, so
# `./ansible-mirror.sh --check` does a dry run.
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

ask_choice() {  # ask_choice <prompt> <default-number> <count>; number on stdout
    local prompt="$1" default="$2" count="$3" reply
    while true; do
        read -r -p "$prompt [$default]: " reply </dev/tty
        reply="${reply:-$default}"
        if [[ "$reply" =~ ^[0-9]+$ ]] && [ "$reply" -ge 1 ] && [ "$reply" -le "$count" ]; then
            printf '%s' "$reply"
            return 0
        fi
        echo "  Enter a number between 1 and $count." >&2
    done
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
 SectorTrace MIRROR setup
================================================================
This box will run the same stack as a SectorTrace deployment,
with nothing collecting into it: the warehouse arrives from an
existing deployment, and its raw archive is pulled out of that
deployment's S3 bucket onto this box's local disk.

Two things follow from that, and they are worth knowing before
you answer anything:

  * The warehouse here is REPLACED WHOLESALE on every sync.
    Review decisions, promotions and document processing done on
    this box are discarded at the next one. Do that work on the
    source deployment.
  * This box will hold the source's data, restricted_ tables
    included. It needs the same care the source gets.

Press Enter to accept a default shown in brackets.

BANNER

    # --- Domain and contact ---
    echo "--- This mirror's domain ---------------------------------------"
    echo "The A record you are pointing at THIS VPS — the mirror's own"
    echo "hostname, not the source deployment's. It must already resolve"
    echo "here before the playbook runs: Caddy asks Let's Encrypt for a"
    echo "certificate on first start, and the challenge fails otherwise."
    echo "(Check with: dig +short <domain>)"
    echo
    local domain=""
    while [ -z "$domain" ]; do
        domain="$(ask 'Mirror domain')"
        [ -z "$domain" ] && echo "  A domain is required." >&2
    done

    echo
    echo "--- Contact email ----------------------------------------------"
    echo "Given to Let's Encrypt for expiry notices, and served as the"
    echo "operator contact. The application refuses to start without it."
    echo "Nothing on a mirror crawls a source, so this is not the"
    echo "User-Agent contact the collecting deployment carries."
    echo
    local contact_email=""
    while [ -z "$contact_email" ]; do
        contact_email="$(ask 'Contact email')"
        case "$contact_email" in
            *@*.*) ;;
            *) echo "  That does not look like an email address." >&2; contact_email="" ;;
        esac
    done

    # --- This box's database passwords ---
    echo
    echo "--- This box's database passwords ------------------------------"
    echo "New passwords for this mirror's own PostgreSQL and Neo4j. They"
    echo "are NOT the source deployment's: the warehouse is copied, not the"
    echo "server, and two boxes sharing a password is two boxes with one"
    echo "password to lose."
    echo
    local pg_app pg_reader neo4j_pw
    if ask_yes_no "Generate them automatically?" "y"; then
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

    # --- The source deployment ---
    echo
    echo "================================================================"
    echo " The deployment this box mirrors"
    echo "================================================================"
    echo
    echo "Its domain, for the record. Nothing connects to it — this is what"
    echo "the sync log, the playbook summary and the portal's"
    echo "X-SectorTrace-Mirror-Of header say, so that a figure taken from"
    echo "here can be traced back to the box it came from."
    echo
    local source_label
    source_label="$(ask 'Source deployment domain' '')"

    echo
    echo "--- How the warehouse gets here --------------------------------"
    echo
    echo "  1) Its nightly verified backup, from S3       (recommended)"
    echo "     The source already writes a verified snapshot to its offsite"
    echo "     bucket every night. This box downloads the newest one and"
    echo "     restores it. No inbound access to the source at all — one"
    echo "     bucket, read-only keys. Freshness: the source's last backup."
    echo
    echo "  2) Directly from its PostgreSQL, over an SSH tunnel"
    echo "     A full copy, verified row by row against the live source."
    echo "     Fresher, and checked against the warehouse rather than"
    echo "     against a file. Costs: an SSH key on the source box, and a"
    echo "     tunnel to keep up."
    echo
    local mode_choice sync_mode
    mode_choice="$(ask_choice 'Choose' '1' 2)"
    if [ "$mode_choice" = "1" ]; then sync_mode="snapshot"; else sync_mode="tunnel"; fi

    # --- The source's raw archive bucket ---
    echo
    echo "--- The source's raw archive (S3 -> this box's local disk) -----"
    echo "The bucket the source archives retrieved bytes into. This box"
    echo "copies what it is missing onto local disk and serves it from"
    echo "there — the mirror's own app is given no S3 configuration at all."
    echo
    echo "Read-only keys are enough, and are what to use: nothing here ever"
    echo "writes to the source's buckets."
    echo
    echo "The first sync downloads the WHOLE archive. Ask the source how"
    echo "large that is (\`sectortrace archive-verify\`) before you agree."
    echo
    local archive_sync="true"
    local a_bucket="" a_endpoint="" a_region="ams" a_style="virtual" a_key="" a_secret=""
    if ask_yes_no "Mirror the raw archive to local disk?" "y"; then
        a_bucket="$(ask '  Bucket')"
        a_endpoint="$(ask '  Endpoint (e.g. s3.example.com)')"
        a_region="$(ask '  Region' 'ams')"
        a_style="$(ask '  URL style (virtual|path)' 'virtual')"
        a_key="$(ask '  Access key (read-only)')"
        a_secret="$(ask_secret '  Secret key')"
    else
        archive_sync="false"
        echo "  Skipped. This mirror will serve figures whose archived bytes"
        echo "  it does not hold — a choice, not an accident. Re-run with"
        echo "  --reconfigure to change it."
    fi

    # --- Snapshot mode: the backup bucket ---
    local b_bucket="" b_endpoint="" b_region="" b_style="" b_key="" b_secret=""
    local b_prefix="warehouse-backups"
    if [ "$sync_mode" = "snapshot" ]; then
        echo
        echo "--- The source's offsite backup bucket -------------------------"
        echo "Where the source's sectortrace-backup-offsite script puts its"
        echo "verified snapshots. Its own vars.yml calls the prefix"
        echo "backup_s3_prefix, under the archive bucket by default."
        echo
        b_prefix="$(ask '  Prefix' 'warehouse-backups')"
        if [ -n "$a_bucket" ] && ask_yes_no "  Same bucket and credentials as the archive above?" "y"; then
            echo "  Using the archive credentials for the snapshots too."
        else
            b_bucket="$(ask '  Bucket')"
            b_endpoint="$(ask '  Endpoint')"
            b_region="$(ask '  Region' 'ams')"
            b_style="$(ask '  URL style (virtual|path)' 'virtual')"
            b_key="$(ask '  Access key (read-only)')"
            b_secret="$(ask_secret '  Secret key')"
        fi
    fi

    # --- Tunnel mode: reaching the source ---
    local ssh_host="" ssh_user="root" ssh_port="22"
    local ssh_key="/root/.ssh/sectortrace-mirror"
    local src_pg_user="sectortrace_reader" src_pg_db="sectortrace" src_pg_pw=""
    local src_pg_host="127.0.0.1" src_pg_port="5432"
    if [ "$sync_mode" = "tunnel" ]; then
        echo
        echo "--- Reaching the source's PostgreSQL ---------------------------"
        echo "The source publishes PostgreSQL on its own loopback, which is"
        echo "correct — so this box holds an SSH tunnel to it rather than the"
        echo "source opening a port."
        echo
        while [ -z "$ssh_host" ]; do
            ssh_host="$(ask '  SSH host (the source box)' "$source_label")"
            [ -z "$ssh_host" ] && echo "    Required." >&2
        done
        ssh_user="$(ask '  SSH user' 'root')"
        # Validated because it is written into zz-local.yml unquoted, as the
        # integer the tunnel unit and the compose file expect.
        ssh_port=""
        while [ -z "$ssh_port" ]; do
            ssh_port="$(ask '  SSH port' '22')"
            [[ "$ssh_port" =~ ^[0-9]+$ ]] || { echo "    A port is a number." >&2; ssh_port=""; }
        done
        ssh_key="$(ask '  SSH private key on this box' '/root/.ssh/sectortrace-mirror')"

        if [ ! -f "$ssh_key" ]; then
            echo
            echo "  $ssh_key does not exist."
            if ask_yes_no "  Generate an ed25519 key pair there now?" "y"; then
                mkdir -p "$(dirname "$ssh_key")"
                chmod 700 "$(dirname "$ssh_key")"
                # No passphrase: the tunnel is a systemd unit with nobody to
                # type one. What protects it is the key being root-only on a
                # box whose whole login surface is the hardening role's, and
                # its being a read-only warehouse credential at the far end.
                ssh-keygen -t ed25519 -N "" -f "$ssh_key" \
                    -C "sectortrace-mirror@$(hostname -f 2>/dev/null || hostname)" >/dev/null
                echo "  Generated."
            fi
        fi
        if [ -f "${ssh_key}.pub" ]; then
            echo
            echo "  Add this public key to ${ssh_user}@${ssh_host}:~/.ssh/authorized_keys"
            echo "  before continuing. Restrict it there if you can — this key"
            echo "  only ever needs a port forward:"
            echo
            echo "    restrict,permitopen=\"${src_pg_host}:${src_pg_port}\" $(cat "${ssh_key}.pub")"
            echo
            read -r -p "  Press Enter once it is in place: " _ </dev/tty
            echo "  Testing the connection..."
            if ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
                   -o ConnectTimeout=10 -i "$ssh_key" -p "$ssh_port" \
                   "${ssh_user}@${ssh_host}" true 2>/dev/null; then
                echo "  Connected."
            else
                echo "  Could NOT connect. The playbook will still install the tunnel," >&2
                echo "  and the first sync will fail until the key is accepted." >&2
            fi
        fi

        echo
        echo "  The warehouse role to read as. Use the source's read-only one:"
        echo "  a copy only ever reads its source, and a mirror holding a"
        echo "  credential that could write to the authoritative warehouse is"
        echo "  a bad trade for nothing."
        echo
        src_pg_user="$(ask '  Source PostgreSQL user' 'sectortrace_reader')"
        src_pg_db="$(ask '  Source database name' 'sectortrace')"
        src_pg_pw="$(ask_secret "  Password for ${src_pg_user} on the source")"
    fi

    # --- When ---
    echo
    echo "--- When to sync -----------------------------------------------"
    echo "Nightly. Leave time after the source's own backup (03:15 by"
    echo "default) and its offsite copy — syncing before those have run"
    echo "just restores last night's snapshot again."
    echo
    local sync_time
    sync_time="$(ask 'Sync time (HH:MM, UTC)' '04:30')"

    # --- Vault password ---
    echo
    echo "--- Vault password ---------------------------------------------"
    echo "Encrypts the file holding everything above — this box's passwords"
    echo "and the source's credentials. You will need it again to re-run"
    echo "this playbook, so put it in your password manager now."
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
# Written by ansible-mirror.sh. Edit with:
#   ansible-vault edit group_vars/all/vault.yml
# or re-run: ./ansible-mirror.sh --reconfigure
#
# Two kinds of secret live here: this box's own database passwords, and
# copies of the source deployment's credentials. Every one of the latter
# should be read-only — a mirror reads a bucket and reads a warehouse.

vault_contact_email: $(yaml_quote "$contact_email")

# --- This box's own databases ---
vault_postgres_app_password: $(yaml_quote "$pg_app")
vault_postgres_reader_password: $(yaml_quote "$pg_reader")
vault_neo4j_password: $(yaml_quote "$neo4j_pw")

# --- Source: raw archive bucket (read by the sync container only) ---
vault_mirror_archive_s3_bucket: $(yaml_quote "$a_bucket")
vault_mirror_archive_s3_endpoint: $(yaml_quote "$a_endpoint")
vault_mirror_archive_s3_region: $(yaml_quote "$a_region")
vault_mirror_archive_s3_url_style: $(yaml_quote "$a_style")
vault_mirror_archive_s3_access_key: $(yaml_quote "$a_key")
vault_mirror_archive_s3_secret: $(yaml_quote "$a_secret")

# --- Source: offsite backup bucket. Blank means "reuse the archive
# credentials above", which is what the sync script falls back to.
vault_mirror_backup_s3_bucket: $(yaml_quote "$b_bucket")
vault_mirror_backup_s3_endpoint: $(yaml_quote "$b_endpoint")
vault_mirror_backup_s3_region: $(yaml_quote "$b_region")
vault_mirror_backup_s3_url_style: $(yaml_quote "$b_style")
vault_mirror_backup_s3_access_key: $(yaml_quote "$b_key")
vault_mirror_backup_s3_secret: $(yaml_quote "$b_secret")

# --- Source: the warehouse itself (tunnel mode) ---
vault_mirror_source_pg_password: $(yaml_quote "$src_pg_pw")
EOF
    chmod 600 "$VAULT_FILE"

    cat > "$LOCAL_FILE" <<EOF
---
# Written by ansible-mirror.sh. Not tracked in git, and loaded after
# vars.yml (group_vars/all/* is read alphabetically, later files win), so
# what is here overrides the tracked defaults without making vars.yml dirty.
domain: $(yaml_quote "$domain")

mirror_source_label: $(yaml_quote "$source_label")
mirror_sync_mode: $(yaml_quote "$sync_mode")
mirror_sync_time: $(yaml_quote "$sync_time")
mirror_archive_sync: $archive_sync
mirror_backup_s3_prefix: $(yaml_quote "$b_prefix")

mirror_ssh_host: $(yaml_quote "$ssh_host")
mirror_ssh_user: $(yaml_quote "$ssh_user")
mirror_ssh_port: $ssh_port
mirror_ssh_key: $(yaml_quote "$ssh_key")
mirror_source_pg_host: $(yaml_quote "$src_pg_host")
mirror_source_pg_port: $src_pg_port
mirror_source_pg_database: $(yaml_quote "$src_pg_db")
mirror_source_pg_user: $(yaml_quote "$src_pg_user")
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
