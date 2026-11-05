"""Run the upstream core polynomial example on CPU, including the generated copy.

Install tests/requirements-cuequivariance.txt, then run:
    python -m unittest discover -s tests -p test_cuequivariance_examples.py -v
"""

from pathlib import Path
import re
import unittest

import numpy as np


REPO = Path(__file__).resolve().parents[1]
REFERENCES = (
    REPO / "library-skills/cuequivariance/SKILL.md",
    REPO / "skills/bionemo-agent-toolkit/skills/cuequivariance/SKILL.md",
)


def run_documented_example(reference):
    """Execute the complete upstream example; preceding snippets are API sketches."""
    text = reference.read_text(encoding="utf-8")
    section = re.search(
        r"^## Custom equivariant polynomial from scratch\n(.*?)(?=^## |\Z)",
        text, re.MULTILINE | re.DOTALL,
    )
    if section is None:
        raise AssertionError(f"No complete polynomial example found in {reference}")
    block = re.search(r"^```python\n(.*?)^```", section.group(1), re.MULTILINE | re.DOTALL)
    if block is None:
        raise AssertionError(f"No Python block found in the polynomial example in {reference}")
    namespace = {"__name__": "__cuequivariance_example__"}
    # Keep traceback line numbers aligned with the upstream document.
    offset = section.start(1) + block.start(1)
    source = "\n" * text[:offset].count("\n") + block.group(1)
    state = np.random.get_state()
    try:
        np.random.seed(42)
        exec(compile(source, str(reference), "exec"), namespace)
    finally:
        np.random.set_state(state)
    return namespace


class PolynomialExampleTests(unittest.TestCase):
    def test_documented_custom_polynomial_matches_builtin_descriptor(self):
        for reference in REFERENCES:
            with self.subTest(reference=reference.relative_to(REPO)):
                example = run_documented_example(reference)
                cue = example["cue"]
                dense = cue.descriptors.fully_connected_tensor_product(
                    cue.Irreps("SO3", "4x1"), cue.Irreps("SO3", "4x1"),
                    cue.Irreps("SO3", "16x0"),
                )
                actual = example["out"]
                expected, = dense(example["w"], example["x"], example["y"])
                self.assertEqual(actual.shape, expected.shape)
                self.assertTrue(np.isfinite(actual).all())
                np.testing.assert_allclose(actual, expected, rtol=1e-10, atol=1e-10)

    def test_documented_polynomial_preserves_rotation_equivariance(self):
        # Agreement with another descriptor alone can miss a shared layout mistake.
        angles = np.array([0.31, -0.43, 0.27])
        discrete = np.zeros(0, dtype=int)  # SO3 has no discrete generators.
        for reference in REFERENCES:
            with self.subTest(reference=reference.relative_to(REPO)):
                example = run_documented_example(reference)
                polynomial = example["ep"]
                inputs = (example["w"], example["x"], example["y"])
                rotated_inputs = [
                    values @ rep.exp_map(angles, discrete).T
                    for rep, values in zip(polynomial.inputs, inputs)
                ]
                actual, = polynomial(*rotated_inputs)
                output_rotation = polynomial.outputs[0].exp_map(angles, discrete)
                np.testing.assert_allclose(
                    actual, example["out"] @ output_rotation.T, rtol=1e-10, atol=1e-10,
                )


if __name__ == "__main__":
    unittest.main()
