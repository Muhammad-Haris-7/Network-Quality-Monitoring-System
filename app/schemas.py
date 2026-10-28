import re
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.\-]{0,253}[A-Za-z0-9])?$")
URL_RE = re.compile(r"^https?://[^\s/]+\S*$")


class TargetBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    address: str = Field(min_length=1, max_length=255)
    check_type: str = Field(default="http", pattern="^(http|ping)$")
    interval_seconds: int = Field(default=60, ge=10, le=86400)
    warning_ms: int = Field(default=500, ge=1)
    critical_ms: int = Field(default=2000, ge=1)
    is_active: bool = True

    @field_validator("name", "address", mode="before")
    @classmethod
    def strip_spaces(cls, v):
        return v.strip() if isinstance(v, str) else v

    @model_validator(mode="after")
    def check_rules(self):
        if self.warning_ms >= self.critical_ms:
            raise ValueError("warning_ms must be less than critical_ms")
        if self.check_type == "http":
            if not URL_RE.match(self.address):
                raise ValueError("HTTP targets need an address starting with http:// or https://")
        else:
            if not HOST_RE.match(self.address):
                raise ValueError("Ping targets need a valid host name or IP, without http://")
        return self


class TargetOut(TargetBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime