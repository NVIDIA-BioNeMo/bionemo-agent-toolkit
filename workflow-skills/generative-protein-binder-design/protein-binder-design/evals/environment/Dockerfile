FROM python:3.12-slim

# Shared by both conditions, before the offline agent task starts. Pin the
# versions used by the local regression suite; no NIM clients or credentials.
RUN python3 -m pip install --no-cache-dir numpy==2.5.1 biotite==1.7.1
