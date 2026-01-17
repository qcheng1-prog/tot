from abc import ABC, abstractmethod
from typing import Optional
from auth.models import CurrentUser

class OAuthProvider(ABC):

    @abstractmethod
    def start_login(self) -> str:
        pass

    @abstractmethod
    def handle_callback(self) -> Optional[CurrentUser]:
        pass
