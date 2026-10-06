"""Run the documented ir_dict example on CPU, including the generated copy.

Install tests/requirements-cuequivariance.txt, then run:
    python -m unittest discover -s tests -p test_cuequivariance_examples.py -v
"""

from pathlib import Path
import re
import unittest

import numpy as np


REPO = Path(__file__).resolve().parents[1]
REFERENCES = (
    REPO / "library-skills/cuequivariance/references/ir-dict.md",
    REPO / "skills/bionemo-agent-toolkit/skills/cuequivariance/references/ir-dict.md",
)


def run_documented_example(reference):
    """Execute the actual Markdown snippets so documentation changes are tested."""
    text = reference.read_text(encoding="utf-8")
    blocks = list(re.finditer(r"^```python\n(.*?)^```", text, re.MULTILINE | re.DOTALL))
    if not blocks:
        raise AssertionError(f"No Python example found in {reference}")
    namespace = {"__name__": "__cuequivariance_example__"}
    for block in blocks:
        # Keep traceback line numbers aligned with the reference.
        source = "\n" * text[:block.start(1)].count("\n") + block.group(1)
        exec(compile(source, str(reference), "exec"), namespace)
    return namespace


class IrDictExampleTests(unittest.TestCase):
    def test_documented_dictionary_contraction_matches_dense(self):
        for reference in REFERENCES:
            with self.subTest(reference=reference.relative_to(REPO)):
                example = run_documented_example(reference)
                actual = np.concatenate(example["blocks"], axis=-1)
                expected, = example["dense"](*example["dense_inputs"])
                self.assertEqual(actual.shape, expected.shape)
                self.assertTrue(np.isfinite(actual).all())
                np.testing.assert_allclose(actual, expected, rtol=1e-10, atol=1e-10)

    def test_dictionary_layout_preserves_rotation_equivariance(self):
        # Dense/split agreement alone can miss a shared layout mistake.
        angles = np.array([0.31, -0.43, 0.27])
        discrete = np.zeros(0, dtype=int)  # SO3 has no discrete generators.
        for reference in REFERENCES:
            with self.subTest(reference=reference.relative_to(REPO)):
                example = run_documented_example(reference)
                rotated_inputs = []
                groups = (example["w"], example["x"], example["sh"])
                for irreps, values in zip(example["desc"].input_irreps, groups):
                    rotated = {
                        ir: values[ir] @ ir.exp_map(angles, discrete).T
                        for _, ir in irreps
                    }
                    rotated_inputs.extend(example["flatten_group"](irreps, rotated))

                actual = np.concatenate(example["poly"](*rotated_inputs), axis=-1)
                output, = example["dense"](*example["dense_inputs"])
                output_rotation = example["dense"].outputs[0].exp_map(angles, discrete)
                np.testing.assert_allclose(
                    actual, output @ output_rotation.T, rtol=1e-10, atol=1e-10,
                )


if __name__ == "__main__":
    unittest.main()
