#!/usr/bin/bash
cd pyodide
make
cd ..
mkdir -p packages/ifcopenshell
cp IfcOpenShell/pyodide/meta.yaml packages/ifcopenshell
# Required, otherwise pyodide will create new temp pyodide environment.
PYODIDE_ROOT=/src/pyodide
# Ensure emsdk tools are in PATH.
PATH=$PYODIDE_ROOT/emsdk/emsdk:$PYODIDE_ROOT/emsdk/emsdk/node/22.16.0_64bit/bin:$PYODIDE_ROOT/emsdk/emsdk/upstream/emscripten:$PATH
pyodide build-recipes ifcopenshell --install
