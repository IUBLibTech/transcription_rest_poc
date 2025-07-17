from typing import Literal, Optional, Self
from pydantic import BaseModel, model_validator
from sqlmodel import SQLModel, Field

from enum import StrEnum
from engines.whisper_model import WhisperOptions
from engines.whispercpp_model import WhisperCPPOptions


TranscriptionState = StrEnum("TranscriptionState", 
                             "QUEUED RUNNING CANCELED FINISHED ERROR EXPIRED")
TranscriptionEngine = StrEnum("TranscriptionEngine", 
                              "openai-whisper whisper.cpp")
TranscriptionNotificationType = StrEnum("TranscriptionNotificationType",
                                        "poll expire url")

class TranscriptionRequest(BaseModel):
    """Make a request for a new transcription"""
    version: Literal['1'] = '1'
    notification_type: TranscriptionNotificationType = Field(default="poll", 
                                                             description="Type of notification to use when the job has finished")
    notification_url: str | None = Field(default=None, 
                                         description="If the notification_type is 'url', issue a PUT to this URL with the job as the payload")
    expiration: float = Field(default=3600.0,
                              description="After the job has completed remove the database entry after this many seconds (reading the job info after completion will also remove it)")
    options: WhisperOptions | WhisperCPPOptions = Field(discriminator="engine",
                                                        description="Engine-specific options")

    @model_validator(mode='after')
    def check_for_a_url(self) -> Self:
        if self.notification_type == TranscriptionNotificationType.url:
            if self.notification_url is None or self.notification_url == '':
                raise ValueError("A url must be provided if url notification is selected")
        return self


class TranscriptionJob(SQLModel, table=True):
    """A transcription job"""
    id: Optional[int] = Field(default=None, primary_key=True,
                              description="Transcription job id")
    owner: str = Field(index=True, description='Job owner')
    state: TranscriptionState = Field(description="State of the transcription job")
    message: str = Field(description="Message accompanying the state")
    media_length: float = Field(default=0.0, description="Duration of media in seconds")    
    language_used: str = Field(default="", description="Language used")
    request: str = Field(description="Original request")   
    queue_time: float = Field(default=0.0, description="Time the job was queued")
    start_time: float = Field(default=0.0, description="Time the job was started")
    finish_time: float = Field(default=0.0, description="Time the job completed")
    processing_time: float = Field(default=0.0, description="Time to process the job")
    url_notified: bool = Field(default=False,
                               description="If notification_type is 'url', Whether or not the notification_url has been notified")