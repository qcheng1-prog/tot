from dataclasses import dataclass
from typing import Optional

@dataclass
class CurrentUser:
    email: str
    name: str
    provider: str
    picture: Optional[str] = None
    sub: Optional[str] = None
