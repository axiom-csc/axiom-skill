#!/usr/bin/env bash
set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEMO_DIR="/tmp/axiom-demo"

rm -rf "$DEMO_DIR"
mkdir -p "$DEMO_DIR"
cd "$DEMO_DIR"
git init -q

echo 'MAX_TRANSACTION = 10000' > checkout.py

echo "==> Installing Axiom..."
curl -fsSL https://raw.githubusercontent.com/axiom-csc/axiom-skill/v1.2.2/install.sh | bash

echo ""
echo "==> Seeding invariants (overwriting auto-generated)..."
cp "$REPO_DIR/scripts/demo_invariants.yaml" .axiom/invariants.yaml
echo "    invariants.yaml:"
cat .axiom/invariants.yaml

echo ""
echo "==> Invoking hook: Edit checkout.py -> MAX_TRANSACTION = 75000"
echo '{"tool_name":"Edit","tool_input":{"file_path":"checkout.py","new_string":"MAX_TRANSACTION = 75000"}}' \
  | python3 .claude/skills/axiom-csc/hooks/pre_tool_use.py

echo ""
echo "==> checkout.py after hook:"
cat checkout.py

cd ~
rm -rf "$DEMO_DIR"
echo ""
echo "==> Done."
