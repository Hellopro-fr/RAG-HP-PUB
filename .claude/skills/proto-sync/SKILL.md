---
name: proto-sync
description: Regenerate Python gRPC stubs from protos/ definitions and verify imports
argument-hint: [proto-file-name] (optional — regenerates all if omitted)
---

# Regenerate gRPC Stubs

Regenerate Python gRPC stubs from `.proto` files in `protos/grpc_stubs/`.

## Steps

### 1. List available proto files

```bash
find protos/ -name "*.proto" -type f 2>/dev/null
```

If `$ARGUMENTS` specifies a proto file, only process that one. Otherwise process all.

### 2. Check prerequisites

Verify `grpcio-tools` is installed:
```bash
python -m grpc_tools.protoc --version 2>/dev/null || echo "MISSING"
```

If missing, instruct: `pip install grpcio-tools`

### 3. Regenerate stubs

For each `.proto` file:
```bash
python -m grpc_tools.protoc \
  -I./protos/grpc_stubs \
  --python_out=./libs/grpc-stubs/src/grpc_stubs/ \
  --grpc_python_out=./libs/grpc-stubs/src/grpc_stubs/ \
  protos/grpc_stubs/<file>.proto
```

### 4. Verify generation

- List generated `*_pb2.py` and `*_pb2_grpc.py` files.
- Test import:
  ```bash
  python -c "from grpc_stubs import <module>_pb2; print('OK')"
  ```

### 5. Check for breaking changes

If a proto was modified (not just added):
- Compare old vs new generated stubs.
- Flag removed or renamed fields/RPCs.
- List services that import the changed stubs (grep for `from grpc_stubs import <module>`).
- Flag Rust consumers: `libs/rust-common-utils` will need `cargo build` to pick up changes.

### 6. Summary

```
## Proto Sync Results
- Proto files processed: N
- Stubs generated: N (list files)
- Import verification: OK / FAILED
- Breaking changes: None / [list]
- Downstream services to rebuild: [list]
```

## Rules

- NEVER modify `.proto` files — this skill only regenerates stubs.
- If proto compilation fails, show the error and ask the user to fix the proto first.
- Apply `.claude/rules/impact-awareness.md` — proto changes affect all gRPC consumers.
- Note: In Docker builds, stubs are regenerated at build time. This skill is for local development.
