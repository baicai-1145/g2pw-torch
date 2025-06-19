# g2pw-torch

This project is the core G2P (Grapheme-to-Phoneme) conversion engine, modified from the original [g2pW](https://github.com/GitYCC/g2pW) to support direct inference with PyTorch (`.pth`) models.

It is designed to be the "brains" of the operation, providing high-accuracy polyphonic character disambiguation for Chinese text by leveraging a neural network model.

## Key Features

- **PyTorch-Native Inference**: Directly loads and uses a `.pth` model checkpoint, removing the need for ONNX conversion.
- **High Accuracy**: Uses a BERT-based model to understand context and select the correct pronunciation for polyphonic characters.
- **GPU Acceleration**: Automatically utilizes CUDA for faster inference if a compatible GPU is available.

## Installation

This package is intended to be used as a dependency for `pypinyin_g2pw_torch`. You can install the entire workspace by navigating to the project's root directory (`g2pw_torch_publish`) and running:

```bash
pip install -e .
```

This will install both `g2pw_torch` and its `pypinyin` wrapper.

## Advanced Usage (Standalone)

While typically used via `pypinyin_g2pw_torch`, you can also use the `G2PWConverter` class directly for batch processing if needed.

```python
from g2pw_torch.g2pw.api import G2PWConverter

# --- Configuration ---
MODEL_DIR = '../../G2PWModel'  # Path to model assets
CHECKPOINT_PATH = '../../G2PWModel-pth/best_accuracy.pth' # Path to your .pth file

# --- Initialization ---
converter = G2PWConverter(
    model_dir=MODEL_DIR,
    checkpoint_path=CHECKPOINT_PATH,
    use_onnx=False, # Use PyTorch backend
    style='pinyin' # Output pinyin with tone number
)

# --- Inference ---
sentences = [
    "重载和重任是两个不同的词。",
    "请把你的银行卡给我。"
]

results = converter(sentences)

for sent, result in zip(sentences, results):
    print(f"Sentence: {sent}")
    # The result is a list of pinyins, one for each character
    print(f"Result: {result}")
    print("-" * 20)
```
