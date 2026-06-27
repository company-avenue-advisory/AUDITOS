from abc import ABC, abstractmethod
from typing import List
from backend.core.validation.base import BaseRule

class BaseValidationPack(ABC):
    """
    Abstract validation pack representing a grouped, installable collection of CA validation rules.
    """
    pack_name: str
    description: str

    @abstractmethod
    def get_rules(self) -> List[BaseRule]:
        """
        Returns all rule instances contained in this pack.
        """
        pass
