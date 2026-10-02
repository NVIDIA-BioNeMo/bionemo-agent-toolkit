# Irrep dictionaries and IrDictPolynomial

`IrDictPolynomial` is **metadata**, not a callable dictionary layer. In 0.12.0
it contains `polynomial`, `input_irreps`, and `output_irreps`. Each logical
group (weights, features, harmonics, output) is described by one `Irreps`;
each `(mul, ir)` block in that group becomes one polynomial operand of size
`mul * ir.dim`. Operand order follows the groups and their blocks.

The core descriptors `linear`, `fully_connected_tensor_product`,
`channelwise_tensor_product`, `full_tensor_product`,
`elementwise_tensor_product`, `spherical_harmonics`, and
`symmetric_contraction` have `_ir_dict` variants in 0.12.0. Their polynomial
is already split; do not split it again.

## Runnable CPU example

This example couples node features with edge harmonic coefficients, keeping
output angular momentum up to 3. It demonstrates one interaction per batch
element; graph gathering and aggregation belong in the framework layer.
The sample harmonic coefficients are random test inputs, not harmonics
computed from coordinates.

Dictionary values here use `(..., mul, ir.dim)`. The descriptor expects
`ir_mul`, so transpose each block before flattening it. Group by unique irrep
keys before using a dictionary; repeated keys would overwrite earlier blocks.

```python
import numpy as np
import cuequivariance as cue

features = 4 * cue.Irreps("SO3", "0 + 1 + 2")
harmonics = cue.Irreps("SO3", "0 + 1 + 2 + 3")
output_filter = [cue.SO3(l) for l in range(4)]
desc = cue.descriptors.channelwise_tensor_product_ir_dict(
    features, harmonics, output_filter,
)
weight_irreps, features, harmonics = desc.input_irreps
(irreps_out,) = desc.output_irreps
poly = desc.polynomial
rng = np.random.default_rng(2)
batch = 2


def random_group(irreps):
    assert len({ir for _, ir in irreps}) == len(irreps)
    return {ir: rng.normal(size=(batch, mul, ir.dim)) for mul, ir in irreps}


def flatten_group(irreps, values):
    # Use descriptor order, not dictionary insertion order.
    return [
        values[ir].swapaxes(-1, -2).reshape(batch, ir.dim * mul)
        for mul, ir in irreps
    ]


w, x, sh = [random_group(irs) for irs in desc.input_irreps]
flat_inputs = [
    block
    for irreps, values in zip(desc.input_irreps, (w, x, sh))
    for block in flatten_group(irreps, values)
]
assert len(flat_inputs) == poly.num_inputs
blocks = poly(*flat_inputs)
assert len(blocks) == len(irreps_out)
result = {
    ir: block.reshape(batch, ir.dim, mul).swapaxes(-1, -2)
    for (mul, ir), block in zip(irreps_out, blocks)
}
for mul, ir in irreps_out:
    assert result[ir].shape == (batch, mul, ir.dim)
    assert np.isfinite(result[ir]).all()

# Same operation as a dense descriptor with consolidated output irreps.
dense = cue.descriptors.channelwise_tensor_product(
    features, harmonics, output_filter, simplify_irreps3=True,
)
dense_inputs = [
    np.concatenate(flatten_group(irs, values), axis=-1)
    for irs, values in zip(desc.input_irreps, (w, x, sh))
]
np.testing.assert_allclose(
    np.concatenate(blocks, axis=-1), dense(*dense_inputs)[0],
)
```

`channelwise_tensor_product_ir_dict` consolidates output irreps automatically.
Its third argument filters allowed irrep types; inspect `irreps_out` for the
actual multiplicities. Use `fully_connected_tensor_product_ir_dict` when
specific output channel counts are required.

## Splitting an existing dense descriptor

Prefer a built-in `_ir_dict` variant. For a custom dense polynomial,
`cue.split_polynomial_by_irreps(poly, operand_id, irreps)` only splits buffers;
it does not transpose data or change its layout. For a weighted tensor product,
split input 2 before input 1, then the single output at `-1`. Higher input
indices otherwise shift when a lower input is split. Wrap the final result in
`cue.IrDictPolynomial(poly, input_irreps, output_irreps)` and ensure every
group's block count, order, and size match its polynomial operands.

## JAX execution boundary

`cuequivariance_jax.ir_dict.segmented_polynomial_uniform_1d` accepts a polynomial
and input/output pytrees. Each leaf must match its operand's
`(..., num_segments, *segment_shape)`, with uniform segment shapes. This may
require reshaping weights as well as transposing feature blocks. The wrapper
uses JAX's leaf order, so ensure it agrees with the descriptor's irrep order;
arbitrary dictionary insertion order is not a way to choose that order.

The high-level convention `(..., mul, ir.dim)` is not sufficient to determine
the execution shape. Read the actual operand descriptors and check the
installed framework API, dtype, and device constraints before selecting this
backend. Use the CPU example above to verify the mathematical contraction
without making assumptions about a GPU kernel.
