# grpc-stubs

Python package that bundles the generated gRPC/protobuf stubs for use by Python microservices.

## Tech Stack

- Python 3.10+
- setuptools (packaging)
- grpcio / grpcio-tools (runtime, generation)

## Install

```bash
pip install -e libs/grpc-stubs
```

## Folder Structure

```
setup.py
src/
  grpc_stubs/
    __init__.py   # Package init (generated stubs are placed here)
```

## Conventions

- Stubs are generated from the `.proto` files in `protos/grpc_stubs/`.
- The package namespace matches the proto package directory: `grpc_stubs`.
- Services import stubs via `from grpc_stubs import <service>_pb2, <service>_pb2_grpc`.

## What This Provides to Other Services

- Pre-compiled Python protobuf and gRPC stubs shared across all Python services.
- Single source of truth for inter-service message types and service interfaces.
