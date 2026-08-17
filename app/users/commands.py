from dataclasses import dataclass


@dataclass
class UpdateUserCommand:
    name: str | None
    email: str | None
