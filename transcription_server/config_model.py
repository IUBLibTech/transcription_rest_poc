from pydantic import BaseModel, Field, field_validator
from pathlib import Path
import sys

class Server(BaseModel):
    port: int = 8000
    host: str = "0.0.0.0"
    root: str | None  = None

class Files(BaseModel):
    database: str = "var/transcription.db"
    log_dir: str = "var"
    models_dir: str = "models"
    users: str = "etc/users.txt"

    # all of the files are to be treated relative to the service root,
    # i.e. the repo, if they are relative paths.
    @field_validator('*', mode='after')
    @classmethod
    def make_abspath(cls, value: str) -> str:
        p = Path(value)
        if not p.is_absolute():
            # the repo path is one directory up from the script path, so
            # we're going to back up one.
            value = str(Path(sys.path[0], "..", value).resolve().absolute())
        return value
    
    

class ServerConfig(BaseModel):
    server: Server = Field(default_factory=Server, description="Server configuration")
    files: Files = Field(default_factory=Files, description="File locations")
