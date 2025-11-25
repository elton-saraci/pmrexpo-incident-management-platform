import io
import json
import os
from functools import lru_cache
from typing import List, Dict, Any, Optional

import httpx
import torch
from PIL import Image
from fastapi import FastAPI, UploadFile, File, HTTPException
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
    Run inference with the Hugging Face fake-image model and return probabilities
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


@app.post("/detect_fake_image", response_model=FakeImageResponse)
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
# via LLM (e.g. LLaMA through Ollama)
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
    severity_score: int = Field(..., ge=1, le=10, description="1=low, 10=extreme")
    estimated_people_affected: int = Field(..., ge=0)
    description: Optional[str] = Field(
        None, description="Free-text description from dispatcher / caller"
    )
    fire_departments_nearby: List[FireDepartment]


class AssignedDepartment(BaseModel):
    fire_department_id: str
    fire_department_name: str
    responders_dispatched: int = Field(..., ge=0)


class IncidentPriorityOutput(BaseModel):
    id: str
    priority_score: float
    priority_level: str
    assignments: List[AssignedDepartment]


class IncidentPrioritizationRequest(BaseModel):
    incidents: List[IncidentReport]


class IncidentPrioritizationResponse(BaseModel):
    incidents: List[IncidentPriorityOutput]


# --------------------------------------------
# LLM call (e.g. Ollama in a separate container)
# --------------------------------------------

LLM_ENDPOINT = os.getenv("LLM_ENDPOINT", "http://localhost:11434/api/generate")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "llama3")


async def call_llm_for_prioritization(
    incidents: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Call a small LLM (e.g. LLaMA via Ollama) to compute priorities and resource allocation.
    The LLM is expected to return valid JSON.
    """

    system_prompt = """
You are an expert disaster management AI assistant.

You receive a list of incidents. Each incident contains:
- id: string
- type: string (e.g. wildfire, building_fire, flood)
- incident_geo_data: { latitude: float, longitude: float }
- severity_score: integer 1..10
- estimated_people_affected: integer
- description: optional free-text
- fire_departments_nearby: list of:
    {
      "id": "FD-001",
      "name": "Central Fire Station",
      "location": { "latitude": float, "longitude": float },
      "available_responders": int
    }

Your tasks:
1. Assign a priority_score between 0 and 1 (float, 3 decimals) for each incident.
2. Classify each incident into one of: "critical", "high", "medium", "low".
   - Higher severity_score and more people_affected -> higher priority.
   - If there are many available_responders nearby, the priority can be handled faster.
   - Incidents with no nearby responders or very few resources should still be flagged as critical if severity is high.
3. Decide how many responders to dispatch from which nearby fire departments.
   - Never dispatch more responders from a department than its available_responders.
   - You decide per incident independently (you don't have to coordinate between incidents).
   - Prefer closer departments (same city/area) if multiple are available.
   - For very low severity incidents, you may dispatch 0 or few responders.

Return ONLY valid JSON with this exact structure:
{
  "incidents": [
    {
      "id": "string",
      "priority_score": 0.0,
      "priority_level": "critical | high | medium | low",
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
"""

    user_payload = {
        "incidents": incidents,
    }

    prompt = system_prompt + "\n\nINPUT:\n" + json.dumps(user_payload)

    body = {
        "model": LLM_MODEL_NAME,
        "prompt": prompt,
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(LLM_ENDPOINT, json=body)
            resp.raise_for_status()
        except Exception as e:
            raise RuntimeError(f"Error calling LLM endpoint {LLM_ENDPOINT}: {e}")

        data = resp.json()

    # Ollama standard format: {"response": "...", ...}
    raw_text = data.get("response", "")
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"LLM did not return valid JSON: {e}. Raw text: {raw_text[:200]}"
        )

    return parsed


# --------------------------------------------
# Endpoint: prioritize incidents (LLM-based)
# --------------------------------------------

@app.post(
    "/prioritize_incidents",
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
                priority_score=float(item["priority_score"]),
                priority_level=str(item["priority_level"]),
                assignments=assignments,
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Invalid incident format in LLM response: {e}",
            )

        outputs.append(out)

    return IncidentPrioritizationResponse(incidents=outputs)
