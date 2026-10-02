# Custom Irrep subclasses

Use this reference when built-in SO3, O3, and SU2 do not represent the user's
group. Implement value equality and hashing so irreps work in dictionaries and
selection rules. A frozen dataclass is a convenient way to do that; `cue.Irrep`
itself is not a dataclass.

This complete Z2 example uses real one-dimensional irreps:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator
import re
import numpy as np
import cuequivariance as cue


@dataclass(frozen=True)
class Z2(cue.Irrep):
    odd: bool

    @classmethod
    def regexp_pattern(cls) -> re.Pattern:
        return re.compile(r"(odd|even)")

    @classmethod
    def from_string(cls, string: str) -> Z2:
        if string not in ("odd", "even"):
            raise ValueError(f"Invalid Z2 irrep: {string!r}")
        return cls(odd=(string == "odd"))

    def __repr__(self) -> str:
        return "odd" if self.odd else "even"

    def __mul__(self, other: Z2) -> Iterator[Z2]:
        yield Z2(self.odd ^ other.odd)

    @classmethod
    def clebsch_gordan(cls, rep1: Z2, rep2: Z2, rep3: Z2) -> np.ndarray:
        # One leading entry per independent coupling; zero for forbidden output.
        if rep3 in rep1 * rep2:
            return np.ones((1, 1, 1, 1))
        return np.zeros((0, 1, 1, 1))

    @property
    def dim(self) -> int:
        return 1

    def __lt__(self, other: Z2) -> bool:
        return (self.dim, self.odd) < (other.dim, other.odd)

    @classmethod
    def iterator(cls) -> Iterator[Z2]:
        yield cls(False)  # Trivial irrep first, then in __lt__ order.
        yield cls(True)

    def discrete_generators(self) -> np.ndarray:
        return np.array([[[-1.0 if self.odd else 1.0]]])

    def continuous_generators(self) -> np.ndarray:
        return np.zeros((0, self.dim, self.dim))

    def algebra(self) -> np.ndarray:
        return np.zeros((0, 0, 0))


even, odd = Z2(False), Z2(True)
assert cue.Irreps(Z2, "3xodd + 2xeven").dim == 5
assert list(odd * odd) == [even]
assert Z2.from_string(repr(odd)) == odd
assert {odd: "value"}[Z2(True)] == "value"
assert Z2.clebsch_gordan(odd, odd, odd).shape == (0, 1, 1, 1)
assert Z2.trivial() == even
```

The generator arrays have shapes `(num_discrete_generators, dim, dim)` and
`(lie_dim, dim, dim)`. The algebra has shape `(lie_dim, lie_dim, lie_dim)`;
finite groups use `lie_dim=0`. CG coefficients have shape
`(num_paths, rep1.dim, rep2.dim, rep3.dim)` even when no coupling is allowed.
The subclass's `__lt__` must implement its full ordering; an override does not
automatically call the base class's dimension comparison.

Validate parsing, equality, hashing, ordering, the group relations for the
generators, and CG covariance. For each discrete generator, transforming both
CG inputs must equal transforming the CG output. A selection rule alone does
not establish that the coefficient tensor uses the correct basis.

For a cyclic Z3 group, specify the representation field. Complex characters
can use labels `k=0,1,2`, generator `exp(2j*pi*k/3)`, and the selection rule
`k3=(k1+k2)%3` with real coefficient 1 for an allowed coupling. This is different
from a real two-dimensional rotation representation. Check the intended
backend's complex-array support before execution; core `Path` coefficients in
0.12.0 are stored as float64 and cannot preserve complex CG coefficients.
