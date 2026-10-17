#!/usr/bin/env bash
#
# build-and-push.sh -- build the 8 service images plus the frozen monolith
# image (DRQ-108) with podman on the host, and push them to OpenShift's
# integrated registry.
#
# Python has no `quarkus-openshift`-style S2I path, so unlike the Java
# sibling's in-cluster binary builds (openshift/build-images.sh there) this
# repo builds on the host and pushes -- the house pattern already verified
# on datamesh-reference-arch-python's own openshift/ counterpart. The
# rejected in-cluster alternative (a Docker-strategy BuildConfig per
# service) is recorded in _plans/r11-build-plan.md: more moving parts across
# 8 Python images for no host-engine win.
#
# Prerequisites (not performed by this script -- see install-infra.sh):
#   - the project exists (oc new-project mea)
#   - the integrated registry's default Route is exposed
#   - logged in to OpenShift (oc login) so `oc whoami -t` yields a push token
#
# Engine: CONTAINER_ENGINE=podman (default) or =docker. Use docker on hosts
# where rootless podman fails these non-root UBI builds (uv .venv permission).
#
#   ./openshift/build-and-push.sh                 # the 8 services + monolith
#   CONTAINER_ENGINE=docker ./openshift/build-and-push.sh   # docker + skopeo push
#   ./openshift/build-and-push.sh --mirror-infra   # + postgres/kafka images
#   ./openshift/build-and-push.sh strangler-proxy order-service   # a subset
set -uo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

require_crc
# CONTAINER_ENGINE selects the build engine (default podman, the OpenShift-path
# convention). docker builds these non-root UBI Containerfiles cleanly; rootless
# podman's user-namespace remap can leave the USER 1001 WORKDIR unwritable
# (`uv sync` -> `/app/.venv: Permission denied`), so on such hosts set
# CONTAINER_ENGINE=docker. The docker path pushes with skopeo, which handles the
# integrated registry's self-signed cert + token creds without a daemon login.
ENGINE="${CONTAINER_ENGINE:-podman}"
case "$ENGINE" in podman|docker) ;; *) fail "CONTAINER_ENGINE must be podman or docker (got '$ENGINE')" ;; esac
command -v "$ENGINE" >/dev/null 2>&1 || fail "$ENGINE not on PATH"
[[ "$ENGINE" == docker ]] && { command -v skopeo >/dev/null 2>&1 || fail "skopeo not on PATH (needed for the docker push path)"; }
occ get project "$NS" >/dev/null 2>&1 || fail "project $NS missing: run ./openshift/install-infra.sh first"

MIRROR_INFRA=false
targets=()
for arg in "$@"; do
  case "$arg" in
    --mirror-infra) MIRROR_INFRA=true ;;
    *) targets+=("$arg") ;;
  esac
done

step "Authenticating to the registry ($ENGINE)"
REGISTRY_USER="$(occ whoami)" || fail "oc whoami failed -- not logged in to OpenShift?"
REGISTRY_TOKEN="$(occ whoami -t)" || fail "oc whoami -t failed -- not logged in to OpenShift?"
if [[ "$ENGINE" == podman ]]; then
  podman login -u "$REGISTRY_USER" -p "$REGISTRY_TOKEN" --tls-verify=false "$REGISTRY_HOST" >/dev/null \
    || fail "podman login $REGISTRY_HOST failed"
fi
ok "registry auth ready ($REGISTRY_HOST)"

build_and_push() {
  local name="$1" context="$2"
  # Services ship a Containerfile; the frozen monolith (00-monolith) ships a
  # Dockerfile (Django + gunicorn) -- accept either.
  local dockerfile="$context/Containerfile"
  [[ -f "$dockerfile" ]] || dockerfile="$context/Dockerfile"
  [[ -f "$dockerfile" ]] || fail "no Containerfile or Dockerfile in $context"
  step "Building $name:$IMAGE_TAG ($ENGINE, $(basename "$dockerfile"))"
  "$ENGINE" build -t "$name:$IMAGE_TAG" -f "$dockerfile" "$context" \
    || fail "$ENGINE build $name failed"
  step "Pushing $name:$IMAGE_TAG -> $REGISTRY_HOST/$NS/$name:$IMAGE_TAG"
  if [[ "$ENGINE" == podman ]]; then
    podman tag "$name:$IMAGE_TAG" "$REGISTRY_HOST/$NS/$name:$IMAGE_TAG"
    podman push --tls-verify=false "$REGISTRY_HOST/$NS/$name:$IMAGE_TAG" \
      || fail "podman push $name failed"
  else
    skopeo copy --dest-tls-verify=false --dest-creds "$REGISTRY_USER:$REGISTRY_TOKEN" \
      "docker-daemon:$name:$IMAGE_TAG" "docker://$REGISTRY_HOST/$NS/$name:$IMAGE_TAG" \
      || fail "skopeo push $name failed"
  fi
  ok "$name:$IMAGE_TAG pushed"
}

want() {
  local name="$1"
  (( ${#targets[@]} == 0 )) && return 0
  local t
  for t in "${targets[@]}"; do [[ "$t" == "$name" ]] && return 0; done
  return 1
}

step "Building + pushing app images into $NS"
for entry in "${SERVICES[@]}"; do
  name="${entry%%:*}"; dir="${entry##*:}"
  want "$name" || continue
  build_and_push "$name" "$REPO_ROOT/examples/$dir"
done

if want monolith; then
  step "Building + pushing the frozen monolith image (bootstrap Job, DRQ-111)"
  build_and_push monolith "$REPO_ROOT/examples/$MONOLITH_DIR"
fi

if [[ "$MIRROR_INFRA" == true ]]; then
  step "Mirroring infra images (postgres/kafka -- the CRC VM has no Docker Hub egress)"
  declare -A INFRA_IMAGES=(
    [postgres]="docker.io/library/postgres:18.6-alpine"
    [kafka]="docker.io/apache/kafka:4.3.1"
  )
  for name in "${!INFRA_IMAGES[@]}"; do
    upstream="${INFRA_IMAGES[$name]}"
    tag="${upstream##*:}"
    step "Mirroring $upstream -> $REGISTRY_HOST/$NS/$name:$tag"
    if [[ "$ENGINE" == podman ]]; then
      podman pull "$upstream" || fail "podman pull $upstream failed"
      podman tag "$upstream" "$REGISTRY_HOST/$NS/$name:$tag"
      podman push --tls-verify=false "$REGISTRY_HOST/$NS/$name:$tag" || fail "podman push $name failed"
    else
      skopeo copy --dest-tls-verify=false --dest-creds "$REGISTRY_USER:$REGISTRY_TOKEN" \
        "docker://$upstream" "docker://$REGISTRY_HOST/$NS/$name:$tag" || fail "skopeo mirror $name failed"
    fi
    ok "$name:$tag mirrored"
  done
  printf '\n    matches the defaults in openshift/helm/mea/values.yaml (postgres.image, kafka.image)\n'
  printf '    on a cluster WITH Docker Hub egress, skip --mirror-infra and point those values at the upstream refs instead\n'
fi

printf '\n    pulled in-cluster from %s/%s/<name>:%s\n' "$REGISTRY_INTERNAL" "$NS" "$IMAGE_TAG"
printf '    next: ./openshift/deploy.sh\n'
