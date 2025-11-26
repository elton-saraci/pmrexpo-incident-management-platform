import io
import json
import os
from functools import lru_cache
from typing import List, Dict, Any, Optional

import torch
from PIL import Image
from fastapi import FastAPI, UploadFile, File, HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field
from transformers import AutoImageProcessor, SiglipForImageClassification

app = FastAPI(
    title="Disaster AI Microservice",
    description="Fake image detection + incident prioritization & resource allocation",
    version="1.0.0",
)

# ============================================
# Fake image detection: Hugging Face model (offline)
# ============================================

FAKE_IMAGE_MODEL_DIR = os.getenv(
    "FAKE_IMAGE_MODEL_DIR",
    "model/models/ai_vs_human",  # local folder with saved HF model
)

FAKE_IMAGE_MODEL_ID = os.getenv(
    "FAKE_IMAGE_MODEL_ID",
    "Ateeqq/ai-vs-human-image-detector",  # just for logging/reason text
)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


@lru_cache
def get_fake_image_model():
    """
    Load the Hugging Face model from a local directory only.
    No internet required.
    """
    try:
        processor = AutoImageProcessor.from_pretrained(
            FAKE_IMAGE_MODEL_DIR,
            local_files_only=True,
        )
        model = SiglipForImageClassification.from_pretrained(
            FAKE_IMAGE_MODEL_DIR,
            local_files_only=True,
        ).to(device)
    except Exception as e:
        raise RuntimeError(
            f"Error loading local fake-image model from '{FAKE_IMAGE_MODEL_DIR}': {e}"
        )
    model.eval()
    return processor, model


def run_fake_image_inference(image_bytes: bytes) -> Dict[str, float]:
    """
    Run inference with the fake-image model and return probabilities
    for 'fake/AI' vs. 'real/human'.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as e:
        raise ValueError(f"Could not read image: {e}")

    processor, model = get_fake_image_model()

    # Preprocess for the HF model
    inputs = processor(images=image, return_tensors="pt").to(device)

    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits[0]
        probs = torch.softmax(logits, dim=-1)

    id2label = getattr(model.config, "id2label", {}) or {}

    # Try to infer which index corresponds to "AI/fake" and which to "human/real"
    ai_index = None
    human_index = None

    for idx, label in id2label.items():
        label_lower = label.lower()
        if ai_index is None and any(
            kw in label_lower for kw in ["ai", "fake", "generated", "synthetic"]
        ):
            ai_index = idx
        if human_index is None and any(
            kw in label_lower for kw in ["human", "real"]
        ):
            human_index = idx

    # Fallback: assume 0 = AI/fake, 1 = human/real
    if ai_index is None or human_index is None:
        ai_index, human_index = 0, 1

    prob_ai = float(probs[ai_index].item())
    prob_human = float(probs[human_index].item())

    return {
        "prob_fake": prob_ai,
        "prob_real": prob_human,
    }


# ---------------------------
# Models for fake-image API
# ---------------------------

class FakeImageResponse(BaseModel):
    is_fake: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


@app.post("/detect-fake-image", response_model=FakeImageResponse)
async def detect_fake_image(file: UploadFile = File(...)):
    """
    Detect whether an uploaded image is likely AI-generated/fake,
    using a Hugging Face vision model.
    """
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image")

    image_bytes = await file.read()

    try:
        result = run_fake_image_inference(image_bytes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model inference failed: {e}")

    prob_fake = result["prob_fake"]
    prob_real = result["prob_real"]

    # More conservative threshold
    fake_threshold = float(os.getenv("FAKE_THRESHOLD", "0.8"))
    is_fake = prob_fake >= fake_threshold
    confidence = prob_fake if is_fake else prob_real

    reason = (
        f"AI fake-likelihood={prob_fake:.3f}, human-likelihood={prob_real:.3f}. "
        f"Threshold={fake_threshold:.2f}. "
        f"Model='{FAKE_IMAGE_MODEL_ID}'."
    )

    return FakeImageResponse(
        is_fake=is_fake,
        confidence=round(confidence, 3),
        reason=reason,
    )


# ============================================
# Incident prioritization / resource allocation (new schema)
# via Hugging Face Router (OpenAI-compatible chat API)
# ============================================

class GeoPoint(BaseModel):
    latitude: float
    longitude: float


class FireDepartment(BaseModel):
    id: str
    name: str
    location: GeoPoint
    available_responders: int = Field(..., ge=0)


class IncidentReport(BaseModel):
    id: str
    type: str = Field(..., description="e.g. wildfire, building_fire, flood")
    incident_geo_data: GeoPoint
    severity_score: int = Field(..., ge=1, le=10, description="1=low, 5=extreme")
    fire_departments_nearby: List[FireDepartment]


class AssignedDepartment(BaseModel):
    fire_department_id: str
    fire_department_name: str
    responders_dispatched: int = Field(..., ge=0)


class IncidentPriorityOutput(BaseModel):
    id: str
    assignments: List[AssignedDepartment]


class IncidentPrioritizationRequest(BaseModel):
    incidents: List[IncidentReport]


class IncidentPrioritizationResponse(BaseModel):
    incidents: List[IncidentPriorityOutput]


# --------------------------------------------
# LLM via Hugging Face Router (Featherless provider)
# --------------------------------------------

HF_API_TOKEN = os.getenv("HF_API_TOKEN", "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")
HF_LLM_MODEL_ID = os.getenv(
    "HF_LLM_MODEL_ID",
    "meta-llama/Meta-Llama-3.1-8B-Instruct",
)

if HF_API_TOKEN:
    hf_client = OpenAI(
        base_url="https://router.huggingface.co/featherless-ai/v1",
        api_key=HF_API_TOKEN,
    )
else:
    hf_client = None


async def call_llm_for_prioritization(
    incidents: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Call a Hugging Face-hosted LLM (via router / Inference Providers)
    to compute priorities and resource allocation.
    The LLM is expected to return valid JSON.
    """

    if hf_client is None:
        raise RuntimeError(
            "HF_API_TOKEN is not set. Please provide your Hugging Face API token "
            "via the HF_API_TOKEN environment variable."
        )

    system_prompt = """
    You are an expert disaster management AI assistant.

    You receive a list of incidents. Each incident contains:
    - id: string
    - type: string (e.g. wildfire, building_fire, flood)
    - incident_geo_data: { latitude: float, longitude: float }
    - severity_score: integer 1-5
    - fire_departments_nearby: list of:
        {
          "id": "FD-001",
          "name": "Central Fire Station",
          "location": { "latitude": float, "longitude": float },
          "available_responders": int (responders who can be dispatched from a given department)
        }

    Your task for EACH incident:
    1. Compute the TOTAL responders required as:
       total_required = severity_score * 10

    2. Distribute these responders across the fire_departments_nearby. if the nearest fire_department_id does not 
    have enough available_responders, get the rest of them from second nearest fire_department.

    IMPORTANT:
    - NEVER assign more responders from a department than its available_responders.
    - NEVER assign negative responders.
    - Never add extra departments.

    Return ONLY valid JSON with this exact structure:
    {
      "incidents": [
        {
          "id": "string",
          "assignments": [
            {
              "fire_department_id": "string",
              "fire_department_name": "string",
              "responders_dispatched": 0
            }
          ]
        }
      ]
    }
    No prose, no explanation, only JSON.
    """.strip()

    user_payload = {"incidents": incidents}

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": "Here is the incident input as JSON:\n" + json.dumps(user_payload),
        },
    ]

    try:
        # openai client is synchronous; calling it from async is fine for small load
        response = hf_client.chat.completions.create(
            model=HF_LLM_MODEL_ID,
            messages=messages,
            temperature=0.1,
            max_tokens=512,
        )
    except Exception as e:
        raise RuntimeError(f"Error calling Hugging Face router: {e}")

    raw_text = (response.choices[0].message.content or "").strip()

    # Strip ```json fences if the model adds them
    if raw_text.startswith("```"):
        lines = raw_text.splitlines()
        # drop first line (``` or ```json)
        lines = lines[1:]
        # drop last line if it's ```
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        raw_text = "\n".join(lines).strip()

    if not raw_text:
        raise RuntimeError("LLM returned empty response text")

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"LLM did not return valid JSON: {e}. Raw text (first 200 chars): {raw_text[:200]}"
        )

    return parsed


@app.post(
    "/resource-allocation",
    response_model=IncidentPrioritizationResponse,
)
async def prioritize_incidents(request: IncidentPrioritizationRequest):
    if not request.incidents:
        raise HTTPException(status_code=400, detail="No incidents provided")

    # Pydantic models -> plain dicts for the LLM
    incidents_as_dicts = [inc.model_dump() for inc in request.incidents]

    try:
        llm_result = await call_llm_for_prioritization(
            incidents=incidents_as_dicts,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM call failed: {e}")

    if "incidents" not in llm_result or not isinstance(llm_result["incidents"], list):
        raise HTTPException(status_code=500, detail="LLM response missing 'incidents' list")

    outputs: List[IncidentPriorityOutput] = []

    for item in llm_result["incidents"]:
        try:
            assignments_raw = item.get("assignments", []) or []

            assignments: List[AssignedDepartment] = []
            for ass in assignments_raw:
                assignments.append(
                    AssignedDepartment(
                        fire_department_id=str(ass.get("fire_department_id", "")),
                        fire_department_name=str(ass.get("fire_department_name", "")),
                        responders_dispatched=int(ass.get("responders_dispatched", 0)),
                    )
                )

            out = IncidentPriorityOutput(
                id=str(item["id"]),
                assignments=assignments,
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Invalid incident format in LLM response: {e}",
            )

        outputs.append(out)

    return IncidentPrioritizationResponse(incidents=outputs)
