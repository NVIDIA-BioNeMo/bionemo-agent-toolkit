# MSA-Search Examples

Use these compact patterns when the activated skill needs more examples.

## Hosted Standard MSA

```python
payload = {
    "sequence": sequence,
    "databases": ["Uniref30_2302", "colabfold_envdb_202108"],
    "e_value": 0.0001,
    "output_alignment_formats": ["a3m"],
}
```

## Hosted Paired MSA

```python
url = "https://health.api.nvidia.com/v1/biology/colabfold/msa-search/paired/predict"
payload = {
    "sequences": [chain_a, chain_b],
    "e_value": 0.0001,
    "max_msa_sequences": 500,
}
```

## Local Template Search

```python
url = "http://localhost:8000/biology/colabfold/msa-search/structure-templates/predict"
payload = {
    "sequence": sequence,
    "structural_template_databases": ["pdb70_220313"],
    "max_structures": 20,
    "max_msa_sequences": 500,
}
```

## Save Standard Alignments

```python
for db_name, formats in result["alignments"].items():
    for fmt_name, data in formats.items():
        path = f"msa_{db_name}.{fmt_name}"
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(data["alignment"])
```
