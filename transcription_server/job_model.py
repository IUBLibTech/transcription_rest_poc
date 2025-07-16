from typing import Literal, Optional
from pydantic import BaseModel, HttpUrl
from sqlmodel import SQLModel, Field

from enum import StrEnum
from engines.whisper_model import WhisperOptions
from engines.whispercpp_model import WhisperCPPOptions


TranscriptionState = StrEnum("TranscriptionState", 
                             "QUEUED RUNNING CANCELED FINISHED ERROR EXPIRED")
TranscriptionEngine = StrEnum("TranscriptionEngine", 
                              "openai-whisper whisper.cpp")

class TranscriptionRequest(BaseModel):
    """Make a request for a new transcription"""
    version: Literal['1'] = '1'
    options: WhisperOptions | WhisperCPPOptions = Field(discriminator="engine",
                                                        description="Engine-specific options")

class TranscriptionJob(SQLModel, table=True):
    """A transcription job"""
    id: Optional[int] = Field(default=None, primary_key=True,
                              description="Transcription job id")
    owner: str = Field(index=True, description='Job owner')
    state: TranscriptionState = Field(description="State of the transcription job")
    message: str = Field(description="Message accompanying the state")
    media_length: float = Field(default=0.0, description="Duration of media in seconds")
    processing_time: float = Field(default=0.0, description="Time to process the media")
    language_used: str = Field(default="", description="Language used")
    request: str = Field(description="Original request")    
