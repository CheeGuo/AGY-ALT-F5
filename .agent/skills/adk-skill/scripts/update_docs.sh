#!/usr/bin/env bash
# Synchronizes Google Agent Development Kit (ADK) documentation into references/
# Follows the canonical pointer at https://github.com/google/adk-python/blob/main/llms-full.txt
# Uses purely relative paths from this script's directory.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REFS_DIR="${SKILL_ROOT}/references"
mkdir -p "${REFS_DIR}"

POINTER_URL="https://raw.githubusercontent.com/google/adk-python/main/llms-full.txt"
DEFAULT_FULL="https://adk.dev/llms-full.txt"
DEFAULT_INDEX="https://adk.dev/llms.txt"

echo "=== Google ADK Documentation Synchronizer (Bash) ==="
echo "Skill root: ${SKILL_ROOT}"
echo "Target dir: ${REFS_DIR}"

FULL_URL="${DEFAULT_FULL}"
INDEX_URL="${DEFAULT_INDEX}"

if pointer_content=$(curl -sL --max-time 15 "${POINTER_URL}" 2>/dev/null); then
    echo "[*] Checked GitHub pointer successfully."
    found_full=$(echo "${pointer_content}" | grep -oE 'https://[^ ]*llms-full[^ \)]*' | head -n 1 || true)
    found_index=$(echo "${pointer_content}" | grep -oE 'https://[^ ]*llms\.txt' | head -n 1 || true)
    if [ -n "${found_full}" ]; then FULL_URL="${found_full}"; fi
    if [ -n "${found_index}" ]; then INDEX_URL="${found_index}"; fi
else
    echo "[!] Warning: Could not fetch pointer from GitHub. Using fallback defaults."
fi

echo "[+] Resolved URLs:"
echo "    - Full:  ${FULL_URL}"
echo "    - Index: ${INDEX_INDEX:-${INDEX_URL}}"

echo "[*] Downloading llms-full.txt..."
curl -sL --max-time 60 -H "User-Agent: ADK-Skill-Updater/1.0" "${FULL_URL}" -o "${REFS_DIR}/llms-full.txt"
echo "[+] Updated llms-full.txt"

echo "[*] Downloading llms.txt..."
curl -sL --max-time 30 -H "User-Agent: ADK-Skill-Updater/1.0" "${INDEX_URL}" -o "${REFS_DIR}/llms.txt"
echo "[+] Updated llms.txt"

cat <<EOF > "${REFS_DIR}/.last_updated.json"
{
  "last_updated_utc": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "pointer_source": "${POINTER_URL}",
  "llms_full_url": "${FULL_URL}",
  "llms_index_url": "${INDEX_URL}"
}
EOF

echo "[+] Updated references/.last_updated.json"
echo "=== Synchronization Complete ==="
