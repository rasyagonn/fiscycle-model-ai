"""Main-backend example; no ML dependencies or image preprocessing."""
import os
from pathlib import Path
import httpx


def headers():
    service=os.environ['FISCYCLE_AI_API_KEY']
    proxy=os.getenv('FISCYCLE_HF_SPACE_TOKEN')
    return {'Authorization':'Bearer '+proxy,'X-Fiscycle-Service-Token':service} if proxy else {'Authorization':'Bearer '+service}


def analyze_photo(path):
    path=Path(path)
    with httpx.Client(base_url=os.environ['FISCYCLE_AI_API_URL'],headers=headers(),timeout=120) as client:
        with path.open('rb') as image:
            response=client.post('/api/v1/bsf/analyze-photo',files={'file':(path.name,image,'image/jpeg')})
        response.raise_for_status()
        return response.json()


def analyze_water(recorded_payload):
    with httpx.Client(base_url=os.environ['FISCYCLE_AI_API_URL'],headers=headers(),timeout=30) as client:
        response=client.post('/api/v1/water/analyze',json=recorded_payload)
        response.raise_for_status()
        return response.json()
