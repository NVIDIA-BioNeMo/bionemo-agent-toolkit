---
name: cuequivariance
description: Build and debug cuEquivariance irreps, custom Irrep subclasses, Clebsch-Gordan tensor products, and equivariant or segmented polynomials. Use for cuequivariance core descriptors and IrDictPolynomial layout or shape questions; framework execution requires the matching JAX or PyTorch API.
---

# cuEquivariance core

Use `cuequivariance` (`import cuequivariance as cue`) to describe group
representations and tensor contractions. Prefer a built-in descriptor when it
expresses the requested operation; construct a `SegmentedTensorProduct` only
for a custom contraction. Core polynomials can be evaluated with NumPy on CPU.
They do not create trainable framework parameters or select a GPU kernel.

## Choose the workflow

- For built-in groups and dense descriptors, use the examples below.
- For a new group, read [custom irreps](references/custom-irreps.md).
- For custom contractions, CG paths, or polynomial inspection, read
  [segmented polynomials](references/segmented-polynomials.md).
- For dictionaries keyed by irrep, read [the ir_dict workflow](references/ir-dict.md).
  It includes a CPU example and the boundary with JAX execution.

## Check the installed API

These examples were checked with **cuEquivariance 0.12.0**. Check the user's
environment before using version-sensitive APIs, especially `IrDictPolynomial`
and the `_ir_dict` descriptors:

```python
from importlib.metadata import version
import cuequivariance as cue

print(version("cuequivariance"))
print("IrDictPolynomial available:", hasattr(cue, "IrDictPolynomial"))
```

If the package is absent, install it in the project's environment, preserving
existing dependency constraints. A standalone CPU example environment can use
`python -m pip install "cuequivariance==0.12.0"`. Core examples need NumPy but
neither CUDA nor JAX/PyTorch. If an API is unavailable, use the supported dense
descriptor or agree on a compatible upgrade; do not invent a substitute method.

For a framework task, inspect the installed `cuequivariance_jax` or
`cuequivariance_torch` signature and its version's backend requirements.
[Official documentation](https://docs.nvidia.com/cuda/cuequivariance/) and the
[0.12.0 source](https://github.com/NVIDIA/cuEquivariance/tree/v0.12.0) cover those
separate packages.

## Groups, multiplicities, and layout

| Group | Construction | Dimension and meaning |
| --- | --- | --- |
| SO(3) | `cue.SO3(l)` | `2*l + 1`; rotations; nonnegative integer `l` |
| O(3) | `cue.O3(l, p)` | `2*l + 1`; also parity `p=+1` or `-1`, e.g. `0e`, `1o` |
| SU(2) | `cue.SU2(j)` | `2*j + 1`; nonnegative integer or half-integer spin |

`cue.Irreps("SO3", "16x0 + 4x1 + 2x2")` has dimension 38. Iterating it yields
`(multiplicity, irrep)` blocks. Multiplying an `Irreps` by an integer scales
multiplicities; `ir1 * ir2` on individual irreps gives the selection rule.
For SO(3), allowed output angular momenta run from `abs(l1-l2)` to `l1+l2`.
For O(3), output parity must also equal `p1*p2`.

Layout is defined **within each irrep block**, not across the whole vector:

| Layout | Block shape before flattening |
| --- | --- |
| `cue.ir_mul` | `(..., ir.dim, mul)` |
| `cue.mul_ir` | `(..., mul, ir.dim)` |

Read `e.inputs[i].layout` and `e.outputs[i].layout` from the descriptor.
The tensor-product examples here use `ir_mul`; many PyTorch layers default to
`mul_ir` and accept explicit layout options. JAX dictionary features often use
`mul_ir`, while polynomial execution can require `ir_mul`.
Convert the actual data block by block with a transpose before flattening;
changing metadata or calling `reshape` alone does not change the element order.
Similarly, sorting or simplifying irreps metadata does not reorder an existing
tensor. Preserve the descriptor's block order when evaluating it.

## Runnable dense tensor product

When the user asks for all output irreps, start with `full_tensor_product`.
It has two inputs and no weights. This example includes all input definitions:

```python
import numpy as np
import cuequivariance as cue

irreps1 = cue.Irreps("SO3", "2x0 + 1x1 + 1x2")
irreps2 = cue.Irreps("SO3", "1x0 + 1x1")
e = cue.descriptors.full_tensor_product(irreps1, irreps2)
rng = np.random.default_rng(0)
x1 = rng.normal(size=(4, e.inputs[0].dim))
x2 = rng.normal(size=(4, e.inputs[1].dim))
[out] = e(x1, x2)
assert out.shape == (4, 40)
assert np.isfinite(out).all()

# A multiplicity summary for display; keep e.outputs[0] for out's actual layout.
summary = e.outputs[0].irreps.sort().irreps.simplify()
assert summary == cue.Irreps("SO3", "3x0 + 5x1 + 3x2 + 1x3")
```

## Select a descriptor

All names below are under `cue.descriptors`. Inspect the returned input/output
metadata to allocate arrays, including weights; do not guess the weight count.

| Descriptor | Use and operand order |
| --- | --- |
| `linear(irreps_in, irreps_out)` | Mix multiplicities of matching irreps; weights, input → output |
| `fully_connected_tensor_product(a, b, out)` | Choose exact output multiplicities; weights, input1, input2 → output |
| `full_tensor_product(a, b)` | All allowed couplings, no weights; input1, input2 → output |
| `channelwise_tensor_product(a, b, irreps3_filter=...)` | Weighted channel pairs; output multiplicity per path is `mul1*mul2` |
| `elementwise_tensor_product(a, b)` | Paired channels without weights; inputs need equal numbers of irrep copies and compatible block boundaries |
| `spherical_harmonics(cue.O3(1, -1), [0, 1, 2, 3])` | Vector → harmonics with parity; normalize input vectors separately if unit-sphere values are required |
| `symmetric_contraction(irreps_in, irreps_out, (1, 2, 3))` | MACE-style polynomial correlations; inspect descriptor shapes and multiplicity constraints |

The third argument to a channelwise product **filters irrep types**; it does not
set output multiplicities. Channelwise retains pairs of channels (`u, v`), unlike
elementwise's matched channel (`u`). Use `simplify_irreps3=True` when a dense
channelwise descriptor should consolidate repeated output irreps.

`EquivariantPolynomial` stores dense representation metadata in `inputs` and
`outputs`, and its contraction in `polynomial`. Calling it returns a **list** of
NumPy outputs, even for one output. The corresponding `_ir_dict` variants return
metadata plus a polynomial already split by irrep; see the linked workflow.

For a custom implementation, check output dimensions and finite values, then
verify covariance under a nontrivial group transformation. Use the same group,
basis, block order, and layout for both the inputs and expected output.
