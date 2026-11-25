#!/usr/bin/env bash
set -euo pipefail

mode="$1"
archives=(
    PyOverScreen-windows-x64.zip
    PyOverScreen-linux-x64.tar.gz
    PyOverScreen-linux-arm64.tar.gz
    PyOverScreen-macos-x64.zip
    PyOverScreen-macos-arm64.zip
)

fail() {
    echo "$1" >&2
    exit 1
}

[[ "$mode" == validate || "$mode" == publish ]] || fail "Unknown release mode."
[[ "$GITHUB_REF" == refs/heads/main ]] || fail "Run the release workflow from main."
[[ "$BUILD_RUN_ID" =~ ^[1-9][0-9]*$ ]] || fail "Enter a numeric build run ID."
[[ "$TAG" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-(alpha|beta|rc)\.[1-9][0-9]*)?$ ]] ||
    fail "Use a tag like v1.1.0 or v1.1.0-rc.1."

run="$(gh api "repos/$GITHUB_REPOSITORY/actions/runs/$BUILD_RUN_ID")"
jq -e --arg sha "$GITHUB_SHA" --arg repo "$GITHUB_REPOSITORY" '
    .path == ".github/workflows/build-artifacts.yml" and
    (.event == "push" or .event == "workflow_dispatch") and
    .head_repository.full_name == $repo and .head_branch == "main" and
    .head_sha == $sha and .conclusion == "success"
' <<< "$run" > /dev/null || fail "Choose a successful build from this exact main commit."

assets="$(mktemp -d)"
trap 'rm -rf "$assets"' EXIT
download_flags=()
for archive in "${archives[@]}"; do
    download_flags+=(--name "${archive%%.*}")
done
gh run download "$BUILD_RUN_ID" --repo "$GITHUB_REPOSITORY" --dir "$assets" "${download_flags[@]}"

release_files=()
checksums=()
for archive in "${archives[@]}"; do
    package_dir="$assets/${archive%%.*}"
    package="$package_dir/$archive"
    checksum="$package.sha256"
    [[ -f "$package" && -f "$checksum" ]] || fail "Missing archive or checksum for $archive."
    hash="$(sha256sum "$package" | cut -d ' ' -f 1)"
    [[ "$(tr -d '\r' < "$checksum")" == "$hash  $archive" ]] ||
        fail "The supplied checksum does not match $archive."
    release_files+=("$package" "$checksum")
    checksums+=("$hash  $archive")
done
digest="$(printf '%s\n' "${checksums[@]}" | sha256sum | cut -d ' ' -f 1)"

main_sha="$(gh api "repos/$GITHUB_REPOSITORY/branches/main" --jq '.commit.sha')"
[[ "$main_sha" == "$GITHUB_SHA" ]] || fail "Main has advanced. Select a build for the new commit."
tag_count="$(gh api "repos/$GITHUB_REPOSITORY/git/matching-refs/tags/$TAG" |
    jq --arg ref "refs/tags/$TAG" '[.[] | select(.ref == $ref)] | length')"
[[ "$tag_count" == 0 ]] || fail "Tag $TAG already exists."
release_matches="$(gh api --paginate "repos/$GITHUB_REPOSITORY/releases?per_page=100" |
    jq -r --arg tag "$TAG" '.[] | select(.tag_name == $tag) | .id')"
[[ -z "$release_matches" ]] || fail "A release or draft already uses $TAG."

if [[ "$mode" == validate ]]; then
    echo "digest=$digest" >> "$GITHUB_OUTPUT"
    echo "Validated $TAG from run $BUILD_RUN_ID at $GITHUB_SHA."
    exit 0
fi

[[ "$digest" == "$VERIFIED_DIGEST" ]] || fail "The release archives changed after validation."
flags=()
if [[ "$TAG" == *-* ]]; then
    flags+=(--prerelease --latest=false)
fi
gh release create "$TAG" "${release_files[@]}" \
    --repo "$GITHUB_REPOSITORY" --target "$GITHUB_SHA" --title "PyOverScreen $TAG" \
    --generate-notes "${flags[@]}"
