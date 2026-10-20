# Resolve the installed authoring contract

This catalog contains skills, not the RFD4-Proteina model source or its manuals.
Use the model checkout selected by the user. Set `RFPROTEINA_ROOT` to its absolute
path and activate that checkout's Python environment. Do not resolve model paths
relative to this skill's installation directory.

## Conditions and interactions

Read `docs/workflow/inputs.md` under `RFPROTEINA_ROOT`, especially **Supported
annotations reference** and **Interaction rules (read before conditioning)**.
These sections define condition levels, values, and combinations supported by
that model revision. The bundled recipes illustrate authoring; successful CIF
serialization alone does not prove that a model consumes an annotation.

```bash
test -f "$RFPROTEINA_ROOT/docs/workflow/inputs.md" || exit 1
```

If the checkout or this manual is missing, obtain the matching source from the
operator before inventing condition semantics. Record the model revision with
the authored input.

## Parser presets and tutorial

The matching tutorial is `docs/examples/annotated_cif_tutorial.ipynb` in the
model checkout. Parser presets live in the installed `rfproteina.utils.parse_presets`
module. Locate the actual implementation using the activated environment:

```python
import inspect
import rfproteina.utils.parse_presets as presets
print(inspect.getfile(presets))
```

## Annotation registries and validation

AtomWorks may be installed as a dependency rather than vendored into the model
checkout. Locate its installed registries and the model's validation module:

```python
import inspect
import rfproteina.conditions  # Register model-specific conditions first.
import atomworks.io.utils.annotator as annotator
import atomworks.io.utils.standard_annotations.base as annotations
import rfproteina.conditions_reporting as reporting

for module in (annotator, annotations, reporting):
    print(inspect.getfile(module))
```

## Chemistry and expandable segments

Read **Charges and bonds** and **Expandable segments** in the same input manual
before changing ligand chemistry, flanking residues, index groups, or sampled
unindexed spacing. Run the installed reporting checks and the bundled CIF
checker afterward. A missing API or disagreement between the manual and installed
code is a version mismatch to resolve, not permission to drop the condition.
