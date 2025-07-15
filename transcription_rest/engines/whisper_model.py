"""All things needed for modeling whisper transcript requests"""

from typing import Literal, Optional, Self
from pydantic import BaseModel, HttpUrl, model_validator, Field
from enum import StrEnum


class WhisperOutputs(BaseModel):
    """URIs for Whisper Output"""
    json_url: Optional[HttpUrl] = Field(default=None, description="URL for Whisper JSON output")
    vtt_url: Optional[HttpUrl] = Field(default=None, description="URL for Whisper VTT output")
    text_url: Optional[HttpUrl] = Field(default=None, description="URL for Whisper Text output")

    @model_validator(mode="after")
    def check_for_at_least_one_output(self) -> Self:
        for v in (self.json_url, self.vtt_url, self.text_url):
            if v is not None and v != '':                
                return self        
        raise ValueError("At least one output must be selected")
        

WhisperLanguage = StrEnum("WhisperLanguages", "AUTO EN ES DE FR")
WhisperModel = StrEnum("WhisperModels", "tiny.en tiny base.en base small.en small medium.en medium large-v1 large-v2 large-v3 large-v3-turbo")

class WhisperOptions(BaseModel):
    """Options for the openai-whisper engine"""
    engine: Literal['openai-whisper'] = 'openai-whisper'
    language: WhisperLanguage = Field(default=WhisperLanguage.EN,
                                       description="Language to use for transcription")
    
    model: WhisperModel = Field(default=WhisperModel['small.en'],
                                 description="Model to use for transcription")
    input: HttpUrl = Field(description="URI of input media")
    outputs: WhisperOutputs = Field(description="Format Output URLS")



