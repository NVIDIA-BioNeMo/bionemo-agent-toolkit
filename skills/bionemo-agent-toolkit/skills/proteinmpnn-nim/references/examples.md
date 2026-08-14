# ProteinMPNN Examples

## Hosted Basic Design

```python
payload = {
    "input_pdb": pdb_content,
    "num_seq_per_target": 10,
    "sampling_temp": [0.1],
    "use_soluble_model": False,
    "ca_only": False,
}
```

## Redesign Chain A Only

```python
payload = {
    "input_pdb": Path("structure.pdb").read_text(),
    "input_pdb_chains": ["A"],
    "num_seq_per_target": 5,
    "sampling_temp": [0.2],
    "omit_AAs": ["C"],
}
```

## Diverse Soluble Designs

```python
payload = {
    "input_pdb": Path("protein.pdb").read_text(),
    "num_seq_per_target": 10,
    "sampling_temp": [0.1, 0.3, 0.5],
    "use_soluble_model": True,
    "omit_AAs": ["M"],
}
```

## Save Multi-FASTA

```python
mfasta = result["mfasta"]
with open("designed_sequences.fa", "w", encoding="utf-8") as handle:
    handle.write(mfasta)
```
