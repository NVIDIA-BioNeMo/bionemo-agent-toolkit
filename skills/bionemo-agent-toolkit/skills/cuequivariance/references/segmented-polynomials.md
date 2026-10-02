# Segmented tensor products and polynomials

An STP specifies a contraction over segmented flat operands. Its subscript
string lists operands separated by commas; coefficient modes follow `+`.
`add_segment` returns a segment index. In `add_path`, an integer selects an
existing segment, a shape tuple creates a new one, and `c` supplies its scalar
or tensor coefficient. Each resulting `Path` links one segment per operand.

## Runnable matrix-vector contraction

```python
import numpy as np
import cuequivariance as cue

d = cue.SegmentedTensorProduct.from_subscripts("ij,j,i")
d.add_segment(0, (3, 4))
d.add_segment(1, (4,))
d.add_segment(2, (3,))
d.add_path(0, 0, 0, c=1.0)
poly = cue.SegmentedPolynomial.eval_last_operand(d)

matrix = np.arange(12, dtype=float).reshape(3, 4)
x = np.arange(4, dtype=float)
[y] = poly(matrix.reshape(-1), x)
np.testing.assert_allclose(y, matrix @ x)
```

The last operand of this STP becomes the polynomial's output. Flat input sizes
must match `poly.inputs[i].size`; leading batch dimensions may broadcast.

## Runnable weighted CG contraction

This constructs SO3(1) × SO3(1) → SO3(0) with four channels per input and sixteen
chosen scalar output channels. Sixteen is a design choice, not a requirement
of the selection rule. The descriptor's first operand is invariant weights.

```python
import numpy as np
import cuequivariance as cue

irreps_in = cue.Irreps("SO3", "4x1")
irreps_out = cue.Irreps("SO3", "16x0")
d = cue.SegmentedTensorProduct.from_subscripts("uvw,iu,jv,kw+ijk")
d.add_segment(1, (3, 4))
d.add_segment(2, (3, 4))
d.add_segment(3, (1, 16))

# cue.clebsch_gordan returns (num_paths, dim1, dim2, dim3).
# Each path uses one (dim1, dim2, dim3) tensor, not the leading path axis.
for cg in cue.clebsch_gordan(cue.SO3(1), cue.SO3(1), cue.SO3(0)):
    d.add_path((4, 4, 16), 0, 0, 0, c=cg)
d = d.normalize_paths_for_operand(-1)

ep = cue.EquivariantPolynomial(
    [
        cue.IrrepsAndLayout(irreps_in.new_scalars(d.operands[0].size), cue.ir_mul),
        cue.IrrepsAndLayout(irreps_in, cue.ir_mul),
        cue.IrrepsAndLayout(irreps_in, cue.ir_mul),
    ],
    [cue.IrrepsAndLayout(irreps_out, cue.ir_mul)],
    cue.SegmentedPolynomial.eval_last_operand(d),
)
rng = np.random.default_rng(1)
w = rng.normal(size=ep.inputs[0].dim)
x1 = rng.normal(size=(2, ep.inputs[1].dim))
x2 = rng.normal(size=(2, ep.inputs[2].dim))
[out] = ep(w, x1, x2)
assert out.shape == (2, 16)

# Compare to the library's equivalent descriptor.
builtin = cue.descriptors.fully_connected_tensor_product(
    irreps_in, irreps_in, irreps_out,
)
np.testing.assert_allclose(out, builtin(w, x1, x2)[0])
```

For multiple irrep blocks, add a segment for each block and loop over the
allowed `(ir1, ir2, ir3)` triples and their CG paths. Derive weight size from
the constructed descriptor. An STP's operand order is chosen by its author;
weights-first is the convention of these weighted descriptors, not a rule
for every STP.

`normalize_paths_for_operand(-1)` changes coefficients for the descriptor's
unit-variance convention. Apply it when matching that convention, not when
the user needs exact, unnormalized coefficients such as matrix multiplication.

## Inspect and transform

- `e.inputs`, `e.outputs`: dense `Rep` metadata; `e.polynomial`: contraction.
- `poly.inputs`, `poly.outputs`: `SegmentedOperand` objects with `size`,
  `num_segments`, `segments`, and `ndim`.
- `operand.all_same_segment_shape()` must be true before reading
  `operand.segment_shape`.
- `poly.operations`: `(Operation, SegmentedTensorProduct)` pairs. `op.buffers`
  indexes the concatenation of polynomial inputs and outputs; with two inputs,
  `(0, 1, 2)` means input 0, input 1, output 0.
- `e * 0.5` scales coefficients; `e.fuse_stps()` fuses compatible operations.
- `e.squeeze_modes().flatten_coefficient_modes()` prepares some descriptors
  for uniform-segment execution; the selected backend's shape constraints
  still need checking.
- `e.split_operand_by_irrep(i)` splits dense representation metadata along
  with the polynomial. If splitting several inputs, split higher indices first
  because earlier splits change the following operand indices.

To validate equivariance on CPU, use each `IrrepsAndLayout.exp_map` with the
same rotation parameters. With row-vector batches, apply the representation
as `x @ D.T`, evaluate the transformed inputs, and compare with `out @ D_out.T`.
Invariant weight operands stay unchanged.
