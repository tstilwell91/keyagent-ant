"""Evidence schemas for model visual prediction and taxonomic KB reasoning integration.

Defines standard library dataclasses with defensive validation logic for 
handling visual candidate outputs, model inputs, and structured evidence packets.
"""

from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional


@dataclass
class VisualCandidate:
    """Represents a single taxonomic visual prediction candidate from a CNN model."""
    taxon_id: Optional[str]
    scientific_name: Optional[str]
    score: float
    rank: int

    def validate(self) -> None:
        """Strictly validates the visual candidate fields."""
        if not self.taxon_id and not self.scientific_name:
            raise ValueError("VisualCandidate must specify either taxon_id or scientific_name.")
        if self.taxon_id is not None and not isinstance(self.taxon_id, str):
            raise TypeError("VisualCandidate taxon_id must be a string.")
        if self.scientific_name is not None and not isinstance(self.scientific_name, str):
            raise TypeError("VisualCandidate scientific_name must be a string.")
        if not isinstance(self.score, (int, float)):
            raise TypeError("VisualCandidate score must be a float or int.")
        if not isinstance(self.rank, int):
            raise TypeError("VisualCandidate rank must be an integer.")
        if self.score < 0.0 or self.score > 1.0:
            raise ValueError(f"VisualCandidate score '{self.score}' must be in the range [0.0, 1.0].")
        if self.rank < 1:
            raise ValueError(f"VisualCandidate rank '{self.rank}' must be >= 1.")


@dataclass
class ModelEvidenceInput:
    """Represents the raw visual prediction output package combined with observed physical traits."""
    image_id: str
    view_type: Optional[str]
    visual_candidates: List[VisualCandidate]
    observed_traits: Dict[str, Any]
    metadata: Dict[str, Any]

    def validate(self) -> None:
        """Strictly validates the model evidence input fields and candidates."""
        if not self.image_id:
            raise ValueError("ModelEvidenceInput image_id is required and cannot be empty.")
        if not isinstance(self.image_id, str):
            raise TypeError("ModelEvidenceInput image_id must be a string.")
        if self.view_type is not None and not isinstance(self.view_type, str):
            raise TypeError("ModelEvidenceInput view_type must be a string.")
        if not isinstance(self.visual_candidates, list) or not self.visual_candidates:
            raise ValueError("ModelEvidenceInput visual_candidates must be a non-empty list.")
        
        for idx, vc in enumerate(self.visual_candidates):
            if not isinstance(vc, VisualCandidate):
                raise TypeError(f"visual_candidates[{idx}] must be a VisualCandidate object.")
            vc.validate()

        if not isinstance(self.observed_traits, dict):
            raise TypeError("ModelEvidenceInput observed_traits must be a dictionary.")
        if not isinstance(self.metadata, dict):
            raise TypeError("ModelEvidenceInput metadata must be a dictionary.")


@dataclass
class ReasoningEvidencePacket:
    """The fully assembled integration packet containing visual predictions, KB reasoning, and comparisons."""
    image_id: str
    view_type: Optional[str]
    visual_candidates: List[Dict[str, Any]]
    observed_traits: Dict[str, Any]
    key_reasoning: Dict[str, Any]
    agreement_summary: Dict[str, Any]
    conflict_summary: List[Dict[str, Any]]
    missing_trait_summary: List[Dict[str, Any]]
    recommended_next_action: Dict[str, Any]
    limitations: Dict[str, Any]
    final_identification: Optional[str] = None
    identification_decision_policy: str = "not_applied"

    def to_dict(self) -> Dict[str, Any]:
        """Converts the reasoning evidence packet into a JSON-serializable dictionary."""
        return asdict(self)
