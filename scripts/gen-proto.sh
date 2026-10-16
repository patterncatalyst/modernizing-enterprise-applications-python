#!/usr/bin/env bash
set -euo pipefail

# Regenerates Python gRPC stubs for BOTH sides of the inventory ACL seam
# (r04/ch.19) from the canonical proto and its byte-identical vendored copy:
#
#   canonical: examples/04-inventory-service/proto/dev/patterncatalyst/inventory/v1/inventory.proto
#   vendored:  examples/00-monolith/order/proto/dev/patterncatalyst/inventory/v1/inventory.proto
#
# Uses `uvx --from grpcio-tools==1.84.0` so this works without either
# project's own venv being set up -- see the per-project `uv run` form
# printed at the end for the alternative once grpcio-tools is a dev dep.
#
# Pin: grpcio-tools==1.84.0 / protobuf==7.36.2 (re-verify current stable at
# lock time; Python 3.14 STANDARD build, not free-threaded).

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd)"

GRPC_TOOLS_PIN="grpcio-tools==1.84.0"
PROTO_LEAF_REL="dev/patterncatalyst/inventory/v1"
PROTO_FILE_REL="${PROTO_LEAF_REL}/inventory.proto"

SVC_PROTO_ROOT="${ROOT_DIR}/examples/04-inventory-service/proto"
SVC_OUT_DIR="${ROOT_DIR}/examples/04-inventory-service/app/grpc_gen"

MONO_PROTO_ROOT="${ROOT_DIR}/examples/00-monolith/order/proto"
MONO_OUT_DIR="${ROOT_DIR}/examples/00-monolith/order/grpc_gen"

generate() {
  local proto_root="$1"
  local out_dir="$2"

  mkdir -p "${out_dir}"
  [ -f "${out_dir}/__init__.py" ] || : > "${out_dir}/__init__.py"

  # -I is pointed at the proto's own LEAF directory (not proto_root), so
  # protoc flattens the dev.patterncatalyst.inventory.v1 package statement
  # out of the GENERATED FILE PATH -- otherwise protoc would nest the stubs
  # under <out_dir>/dev/patterncatalyst/inventory/v1/inventory_pb2.py instead
  # of the clean <out_dir>/inventory_pb2.py we want. The `package` statement
  # still governs the wire-level fully-qualified message/service names
  # regardless of this flattening.
  echo "Generating stubs into ${out_dir} ..."
  uvx --from "${GRPC_TOOLS_PIN}" python -m grpc_tools.protoc \
    -I "${proto_root}/${PROTO_LEAF_REL}" \
    --python_out="${out_dir}" \
    --grpc_python_out="${out_dir}" \
    "${proto_root}/${PROTO_FILE_REL}"

  # Classic grpc_tools import-path gotcha: protoc-gen-grpc-python emits a
  # bare top-level `import inventory_pb2 as inventory__pb2` in the generated
  # *_pb2_grpc.py. That only resolves if the output directory itself is on
  # sys.path -- it breaks the moment the stubs are imported as
  # `<pkg>.grpc_gen.inventory_pb2_grpc` from elsewhere in the app. Rewrite it
  # to a package-relative import so it works regardless of caller location.
  sed -i \
    -e 's/^import inventory_pb2 as inventory__pb2$/from . import inventory_pb2 as inventory__pb2/' \
    "${out_dir}/inventory_pb2_grpc.py"
}

generate "${SVC_PROTO_ROOT}" "${SVC_OUT_DIR}"
generate "${MONO_PROTO_ROOT}" "${MONO_OUT_DIR}"

cat <<EOF

Generated:
  ${SVC_OUT_DIR}/inventory_pb2.py
  ${SVC_OUT_DIR}/inventory_pb2_grpc.py
  ${MONO_OUT_DIR}/inventory_pb2.py
  ${MONO_OUT_DIR}/inventory_pb2_grpc.py

Per-project 'uv run' form (once grpcio-tools==${GRPC_TOOLS_PIN#*==} is a dev
dependency in that project's pyproject.toml / uv.lock):

  cd examples/04-inventory-service && \\
    uv run python -m grpc_tools.protoc \\
      -I proto/${PROTO_LEAF_REL} \\
      --python_out=app/grpc_gen --grpc_python_out=app/grpc_gen \\
      proto/${PROTO_FILE_REL}
  # then re-apply the sed fixup above to app/grpc_gen/inventory_pb2_grpc.py

  cd examples/00-monolith && \\
    uv run python -m grpc_tools.protoc \\
      -I order/proto/${PROTO_LEAF_REL} \\
      --python_out=order/grpc_gen --grpc_python_out=order/grpc_gen \\
      order/proto/${PROTO_FILE_REL}
  # then re-apply the sed fixup above to order/grpc_gen/inventory_pb2_grpc.py
EOF
