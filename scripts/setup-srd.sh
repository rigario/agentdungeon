#!/bin/bash
# Fetch D&D 5E SRD reference data (MIT licensed)
# Run once after cloning: bash scripts/setup-srd.sh

set -e
cd "$(dirname "$0)/.."

echo "Fetching SRD reference data..."

mkdir -p data/references
cd data/references

# soryy708/dnd5-srd (MIT) — our primary data source
if [ ! -d "dnd5-srd" ]; then
    git clone https://github.com/soryy708/dnd5-srd.git
    echo "✓ dnd5-srd cloned"
else
    echo "✓ dnd5-srd already exists"
fi

echo ""
echo "Done. Reference data at data/references/"
echo "To update: cd data/references/dnd5-srd && git pull"
