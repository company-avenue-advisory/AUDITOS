import hashlib
from typing import Dict, Any, List

class LayoutMemory:
    """
    Stage 8: Stores and matches layout fingerprints deterministically.
    No ML. Uses coordinate bounding boxes and header hashes to match layouts.
    """
    def __init__(self):
        self.memory: Dict[str, Dict[str, Any]] = {}

    def generate_fingerprint(self, headers: List[str], column_coordinates: List[float]) -> str:
        """
        Creates a deterministic hash representing the spatial and textual layout of columns.
        """
        raw_string = "|".join(sorted(str(h).lower().strip() for h in headers))
        raw_coords = "|".join(f"{coord:.2f}" for coord in sorted(column_coordinates))
        combined = f"{raw_string}::{raw_coords}"
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    def store_layout(self, vendor: str, headers: List[str], coords: List[float], 
                     semantic_mapping: Dict[str, str], accepted_path: str) -> str:
        """
        Persists a layout mapping deterministically.
        """
        fingerprint = self.generate_fingerprint(headers, coords)
        self.memory[fingerprint] = {
            "vendor": vendor,
            "headers": headers,
            "coordinates": coords,
            "semantic_mapping": semantic_mapping,
            "accepted_path": accepted_path
        }
        return fingerprint

    def lookup_layout(self, headers: List[str], coords: List[float]) -> Dict[str, Any]:
        """
        Retrieves layout mappings if coordinates and headers match fingerprint.
        """
        fingerprint = self.generate_fingerprint(headers, coords)
        return self.memory.get(fingerprint, {})
