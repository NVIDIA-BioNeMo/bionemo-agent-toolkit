#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
# Run a hosted command with its credential in the child's environment:
#   bash scripts/hosted_env.sh python your_nim_request.py
# Sourcing remains supported for existing callers.
set +x  # Never trace credential assignments, even when invoked with bash -x.
if [ -n "${NGC_API_KEY:-}" ]; then
    export NGC_API_KEY
elif [ -n "${NVIDIA_API_KEY:-}" ]; then
    export NGC_API_KEY="$NVIDIA_API_KEY"
else
    printf '%s\n' 'Set NGC_API_KEY or NVIDIA_API_KEY for hosted NIM access.' >&2
    if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
        return 1
    fi
    exit 1
fi

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    if [[ $# -eq 0 ]]; then
        printf '%s\n' 'Usage: bash hosted_env.sh COMMAND [ARG ...]' >&2
        exit 2
    fi
    exec "$@"
fi
