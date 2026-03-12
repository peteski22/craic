#!/usr/bin/env bash
# Install or uninstall CRAIC for OpenCode.
#
# Usage:
#   install-opencode.sh install [--project <path>]
#   install-opencode.sh uninstall [--project <path>]
#
# Without --project, installs globally to ~/.config/opencode/.
# With --project, installs into <path>/.opencode/.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PLUGIN_DIR="${REPO_ROOT}/plugins/craic"
SERVER_DIR="${PLUGIN_DIR}/server"

# -- Dependencies. --

if ! command -v jq &>/dev/null; then
    echo "Error: jq is required. Install with: brew install jq" >&2
    exit 1
fi

# -- Argument parsing. --

usage() {
    echo "Usage: $(basename "$0") <install|uninstall> [--project <path>]"
    exit 1
}

if [[ $# -lt 1 ]]; then
    usage
fi

ACTION="$1"
shift
PROJECT=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project)
            PROJECT="${2:?--project requires a path}"
            shift 2
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage
            ;;
    esac
done

if [[ -n "${PROJECT}" ]]; then
    TARGET="${PROJECT}/.opencode"
else
    TARGET="${HOME}/.config/opencode"
fi

# -- Core: apply an action to a set of sources. --
# Usage: apply <install|uninstall> <target_dir> <label> <strip_ext> <sources...>
# Sources are pre-expanded by the caller (glob expansion happens at call site).

apply() {
    local action="$1" target_dir="$2" label="$3" strip_ext="$4"
    shift 4

    [[ "${action}" == "install" ]] && mkdir -p "${target_dir}"

    for src in "$@"; do
        [[ -e "${src}" ]] || continue
        local name
        name="$(basename "${src}" "${strip_ext}")"

        if [[ "${action}" == "install" ]]; then
            if [[ -d "${src}" ]]; then
                ln -sfn "${src}" "${target_dir}/$(basename "${src}")"
            else
                ln -sf "${src}" "${target_dir}/"
            fi
            echo "  Linked ${label}: ${name}"
        else
            rm -rf "${target_dir}/$(basename "${src}")"
            echo "  Removed ${label}: ${name}"
        fi
    done
}

# -- Generate OpenCode command files from Claude Code command files. --
# Strips the `name:` frontmatter field and adds `agent: build`.

generate_commands() {
    local target_dir="$1"
    mkdir -p "${target_dir}"

    for cmd_file in "${PLUGIN_DIR}"/commands/*.md; do
        [[ -f "${cmd_file}" ]] || continue

        local basename
        basename="$(basename "${cmd_file}")"

        awk '
            BEGIN { in_fm=0; past_fm=0 }
            /^---$/ {
                if (!in_fm) { in_fm=1; print; next }
                else { print "agent: build"; print "---"; past_fm=1; next }
            }
            in_fm && /^name:/ { next }
            { print }
        ' "${cmd_file}" > "${target_dir}/${basename}"
        echo "  Generated command: /${basename%.md}"
    done
}

remove_commands() {
    local target_dir="$1"

    for cmd_file in "${PLUGIN_DIR}"/commands/*.md; do
        [[ -f "${cmd_file}" ]] || continue
        local basename
        basename="$(basename "${cmd_file}")"
        if [[ -f "${target_dir}/${basename}" ]]; then
            rm -f "${target_dir}/${basename}"
            echo "  Removed command: /${basename%.md}"
        fi
    done
}

# -- MCP configuration. --

configure_mcp() {
    local config_file="${TARGET}/opencode.json"
    local server_path
    server_path="$(cd "${SERVER_DIR}" && pwd)"

    local craic_entry
    craic_entry=$(jq -n \
        --arg dir "${server_path}" \
        '{ type: "local", command: ["uv", "run", "--directory", $dir, "craic-mcp-server"] }')

    if [[ -f "${config_file}" ]]; then
        if jq -e '.mcp.craic' "${config_file}" &>/dev/null; then
            echo "  MCP server already configured in ${config_file}"
        else
            local tmp
            tmp=$(jq --argjson entry "${craic_entry}" '.mcp.craic = $entry' "${config_file}")
            printf '%s\n' "${tmp}" > "${config_file}"
            echo "  Added CRAIC MCP server to ${config_file}"
        fi
    else
        mkdir -p "$(dirname "${config_file}")"
        jq -n --argjson entry "${craic_entry}" \
            '{ "$schema": "https://opencode.ai/config.json", mcp: { craic: $entry } }' \
            > "${config_file}"
        echo "  Created ${config_file} with CRAIC MCP server"
    fi
}

remove_mcp() {
    local config_file="${TARGET}/opencode.json"
    [[ -f "${config_file}" ]] || return 0

    local tmp
    tmp=$(jq 'del(.mcp.craic) | if .mcp == {} then del(.mcp) else . end' "${config_file}")
    printf '%s\n' "${tmp}" > "${config_file}"
    echo "  Removed CRAIC MCP server from ${config_file}"
}

# -- Dispatch. --

case "${ACTION}" in
    install)
        echo "Installing CRAIC for OpenCode (${TARGET})..."
        apply install "${TARGET}/skills" "skill" "" "${PLUGIN_DIR}"/skills/*/
        generate_commands "${TARGET}/commands"
        configure_mcp
        echo ""
        echo "Done. Restart OpenCode to pick up the changes."
        ;;
    uninstall)
        echo "Removing CRAIC for OpenCode (${TARGET})..."
        apply uninstall "${TARGET}/skills" "skill" "" "${PLUGIN_DIR}"/skills/*/
        remove_commands "${TARGET}/commands"
        remove_mcp
        echo ""
        echo "Done."
        ;;
    *)
        usage
        ;;
esac
