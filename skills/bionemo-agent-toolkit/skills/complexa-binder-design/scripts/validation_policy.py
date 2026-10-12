# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Default independent validation thresholds, shared by planning and scoring."""

GATE = {
    "ipsae_min": ("min", 0.45),
    "iptm": ("min", 0.65),
    "binder_plddt": ("min", 0.70),
    "complex_plddt": ("min", 0.70),
    "apo_binder_plddt": ("min", 0.70),
    "binder_rmsd": ("max", 2.50),
    "hotspot_contact_frac": ("min", 0.20),
}
