import io
import torch
from PIL import Image
from transformers import AutoImageProcessor, SiglipForImageClassification

MODEL_ID = "Ateeqq/ai-vs-human-image-detector"

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Load once at startup
processor = AutoImageProcessor.from_pretrained(MODEL_ID)
model = SiglipForImageClassification.from_pretrained(MODEL_ID).to(device)
model.eval()


def detect_ai_image_bytes(image_bytes: bytes):
    # bytes -> PIL image
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    # preprocess
    inputs = processor(images=image, return_tensors="pt").to(device)

    # inference
    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits
        probs = torch.softmax(logits, dim=-1)[0]

    id2label = model.config.id2label  # e.g. {0: 'ai', 1: 'hum'}

    # Map labels to indices
    ai_idx = next(i for i, lbl in id2label.items() if "ai" in lbl.lower())
    human_idx = next(i for i, lbl in id2label.items() if "hum" in lbl.lower())

    prob_ai = float(probs[ai_idx].item())
    prob_human = float(probs[human_idx].item())

    is_fake = prob_ai >= 0.5
    confidence = prob_ai if is_fake else prob_human

    return {
        "is_fake": is_fake,
        "prob_ai": prob_ai,
        "prob_human": prob_human,
        "confidence": confidence,
        "predicted_label": "ai" if is_fake else "human",
    }
