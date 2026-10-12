FROM python:3.12-slim

# Identical CPU preparation/scoring dependencies for both evaluation conditions.
# No model runtime, weights, credentials or inference endpoints.
RUN python3 -m pip install --no-cache-dir numpy==2.5.1 biotite==1.7.1 PyYAML==6.0.3
