# download_ai_vs_human_model.py
import os
from transformers import AutoImageProcessor, SiglipForImageClassification

MODEL_ID = "Ateeqq/ai-vs-human-image-detector"
OUT_DIR = os.path.join("models", "ai_vs_human")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"Downloading processor from {MODEL_ID} ...")
    processor = AutoImageProcessor.from_pretrained(MODEL_ID)
    processor.save_pretrained(OUT_DIR)

    print(f"Downloading model from {MODEL_ID} ...")
    model = SiglipForImageClassification.from_pretrained(MODEL_ID)
    model.save_pretrained(OUT_DIR)

    print(f"Saved Hugging Face model to: {OUT_DIR}")


if __name__ == "__main__":
    main()
