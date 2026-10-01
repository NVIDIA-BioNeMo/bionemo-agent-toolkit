# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
# Source in the same shell as each hosted NIM command:
#   source scripts/hosted_env.sh && python your_nim_request.py
# A separate shell invocation cannot update a later command's environment.
if [ -n "${NGC_API_KEY:-}" ]; then
    export NGC_API_KEY
elif [ -n "${NVIDIA_API_KEY:-}" ]; then
    export NGC_API_KEY="$NVIDIA_API_KEY"
else
    printf '%s\n' 'Set NGC_API_KEY or NVIDIA_API_KEY for hosted NIM access.' >&2
    return 1
fi
