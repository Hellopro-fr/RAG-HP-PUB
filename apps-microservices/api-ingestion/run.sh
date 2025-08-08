#!/bin/bash

source .venv/bin/activate
# pip install -r requirements.txt
ls -la
cd ./app/
ls -la
cd ./common_utils/
ls -la
cd ../..

uvicorn main:app --host 0.0.0.0 --port 8509 --reload
