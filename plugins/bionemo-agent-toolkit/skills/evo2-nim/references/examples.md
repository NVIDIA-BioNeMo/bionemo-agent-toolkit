# Evo 2 Examples

These compact patterns supplement the activated skill.

## Hosted Generation Payload

```python
payload = {
    "sequence": "ACTGACTGACTGACTG",
    "num_tokens": 64,
    "temperature": 0.7,
    "top_k": 3,
    "top_p": 0.0,
    "random_seed": 1,
    "enable_sampled_probs": True,
    "enable_elapsed_ms_per_token": True,
}
```

## Local Generation Payload

```python
url = "http://localhost:8000/biology/arc/evo2/generate"
headers = {"Content-Type": "application/json"}
```

Do not send `Authorization` to local inference requests.

## Local Forward Payload

```python
payload = {
    "sequence": "ACTGACTGACTG",
    "output_layers": ["output_layer", "decoder.layers.3.self_attention"],
}
```

## Decode Forward Response

```python
npz_bytes = base64.b64decode(result["data"])
with open("evo2_forward_outputs.npz", "wb") as handle:
    handle.write(npz_bytes)

arrays = np.load(io.BytesIO(npz_bytes), allow_pickle=False)
for name in arrays.files:
    arr = arrays[name]
    print(name, arr.shape, arr.dtype, np.isfinite(arr).all())
```
