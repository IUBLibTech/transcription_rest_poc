"""All things needed for modeling whispercpp transcript requests"""

from typing import Literal, Optional, Self
from pydantic import BaseModel, HttpUrl, model_validator, Field
from enum import StrEnum


class WhisperCPPOutputs(BaseModel):
    """URIs for WhisperCPP Output"""    
    json_url: Optional[HttpUrl] = Field(default=None, description="URL for Whisper JSON output")
    vtt_url: Optional[HttpUrl] = Field(default=None, description="URL for Whisper VTT output")
    txt_url: Optional[HttpUrl] = Field(default=None, description="URL for Whisper Text output")
    csv_url: Optional[HttpUrl] = Field(default=None, description="URL for Whisper.cpp CSV output")
    meta_url: Optional[HttpUrl] = Field(default=None, description="URL for processing metadata")

    @model_validator(mode="after")
    def check_for_at_least_one_output(self) -> Self:
        for v in (self.json_url, self.vtt_url, self.txt_url):
            if v is not None and v != '':                
                return self        
        raise ValueError("At least one output must be selected")
        
WhisperCPPLanguage = StrEnum("WhisperCPPLanguage", "AUTO EN ES DE FR")
WhisperCPPModel = StrEnum("WhisperCPPModel", """tiny tiny.en tiny-q5_1 tiny.en-q5_1 tiny-q8_0 
             base base.en base-q5_1 base.en-q5_1 base-q8_0 
             small small.en small.en-tdrz small-q5_1 small.en-q5_1 small-q8_0 
             medium medium.en medium-q5_0 medium.en-q5_0 medium-q8_0 
             large-v1 
             large-v2 large-v2-q5_0 large-v2-q8_0 
             large-v3 large-v3-q5_0 large-v3-turbo large-v3-turbo-q5_0 large-v3-turbo-q8_0""")

class WhisperCPPOptions(BaseModel):
    """Options for the openai-whisper engine"""
    engine: Literal['whisper.cpp'] = 'whisper.cpp'
    language: WhisperCPPLanguage = Field(default=WhisperCPPLanguage.EN,
                                       description="Language to use for transcription")    
    model: WhisperCPPModel = Field(default=WhisperCPPModel['small.en'],
                                 description="Model to use for transcription")
    input: HttpUrl = Field(description="URI of input media")
    outputs: WhisperCPPOutputs = Field(description="Format Output URLS")