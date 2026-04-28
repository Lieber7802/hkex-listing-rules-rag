from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseTool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass
    
    @abstractmethod
    def run(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        pass
