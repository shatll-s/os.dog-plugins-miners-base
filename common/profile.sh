#!/bin/bash
# Shared slot-profile reader. Call after validating PROFILE.
load_profile() {
    ALGO=$(jq -r '.algo // empty' "$PROFILE")
    POOL=$(jq -r '.pool // empty' "$PROFILE")
    WALLET=$(jq -r '.wallet // empty' "$PROFILE")
    if [[ ${1:-} == wallet-fallback ]]; then
        TEMPLATE=$(jq -r '.template // .wallet // empty' "$PROFILE")
    else
        TEMPLATE=$(jq -r '.template // empty' "$PROFILE")
    fi
    PASS=$(jq -r '.pass // empty' "$PROFILE")
    API_PORT=$(jq -r '.api_port // empty' "$PROFILE")
    ADDITION=$(jq -r '.addition // empty' "$PROFILE")
    extra=()
    read -r -d '' -a extra <<< "$ADDITION" || true
}
