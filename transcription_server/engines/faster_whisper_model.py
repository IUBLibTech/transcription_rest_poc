"""All things needed for modeling FasterWhisper transcript requests"""

from typing import Literal, Optional, Self
from pydantic import BaseModel, HttpUrl, model_validator, Field
from enum import StrEnum


class FasterWhisperOutputs(BaseModel):
    """URIs for FasterWhisper Output"""    
    json_url: Optional[HttpUrl] = Field(default=None, description="URL for Whisper JSON output")
    vtt_url: Optional[HttpUrl] = Field(default=None, description="URL for Whisper VTT output")
    txt_url: Optional[HttpUrl] = Field(default=None, description="URL for Whisper Text output")
    meta_url: Optional[HttpUrl] = Field(default=None, description="URL for processing metadata")

    @model_validator(mode="after")
    def check_for_at_least_one_output(self) -> Self:
        for v in (self.json_url, self.vtt_url, self.txt_url):
            if v is not None and v != '':                
                return self        
        raise ValueError("At least one output must be selected")
        
FasterWhisperLanguage = StrEnum("FasterWhisperLanguage", "AUTO EN ES DE FR")
FasterWhisperModel = StrEnum("FasterWhisperModel", """tiny tiny.en small small.en medium medium.en                             
            distil-small.en distil-medium.en large-v2 large-v3 large-v3-turbo 
            distil-large-v2 distil-large-v3""")

FasterWhisperComputeType = StrEnum("FasterWhisperComputeType", "default fp32 int8")

class FasterWhisperOptions(BaseModel):
    """Options for the openai-whisper engine"""
    engine: Literal['faster-whisper'] = 'faster-whisper'
    language: FasterWhisperLanguage = Field(default=FasterWhisperLanguage.EN,
                                       description="Language to use for transcription")    
    model: FasterWhisperModel = Field(default=FasterWhisperModel['small.en'],
                                 description="Model to use for transcription")
    compute_type: FasterWhisperComputeType = Field(default=FasterWhisperComputeType.default,
                                                   description="Computation data type")
    input: HttpUrl = Field(description="URI of input media")
    outputs: FasterWhisperOutputs = Field(description="Format Output URLS")