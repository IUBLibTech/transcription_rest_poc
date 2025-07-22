#!/bin/env python3
from typing import Annotated
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import SQLModel, Session, create_engine, select
from contextlib import asynccontextmanager
import asyncio
from job_model import TranscriptionJob, TranscriptionState, TranscriptionRequest
from engines.whisper_process import process_whisper
from engines.whispercpp_process import process_whispercpp
from config_model import ServerConfig
import json
import logging
import time
import requests

engine = None

security = HTTPBearer()

@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine
    # things at startup
    # -- create the database as needed
    # -- restart any background processes that need it
    app.server_lock = False  # start with the service accepting jobs
    config: ServerConfig = app.server_config
    engine = create_engine("sqlite:///" + config.files.database,
                           connect_args={'check_same_thread': False})
    SQLModel.metadata.create_all(engine)
    t = asyncio.create_task(process_transcription_queue())
    yield
    # things at shutdown
    t.cancel()


def get_session():
    """Bind a session to the underlying ORM"""
    with Session(engine) as session:
        yield session

# Create a session dependency for the API calls.
SessionDep = Annotated[Session, Depends(get_session)]

app = FastAPI(lifespan=lifespan)

def validate_credentials(credentials: HTTPAuthorizationCredentials):
    """Validate the bearer token against the ones we know."""
    if credentials.scheme != 'Bearer':
        raise HTTPException(401, "Invalid authorization token")    
    try:        
        config: ServerConfig = app.server_config
        with open(config.files.users) as f:
            for l in f.readlines():
                is_admin, user, token = l.strip().split(':')
                if f"{user}:{token}" == credentials.credentials:
                    return user, is_admin.lower()[0] == 'y'
    except Exception as e:
        logging.warning(f"Cannot read credentials file: {e}.  Will deny access")
    raise HTTPException(401, "Invalid authorization token")


@app.get("/transcription/lock")
async def lock_transcription_queue(session: SessionDep,
                                   credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]):
    "Block new jobs from being submitted (admin only)"
    user, is_admin = validate_credentials(credentials)
    if not is_admin:
        raise HTTPException(401, "Unauthorized")
    app.server_lock = True    
    return {"ok": True}
    

@app.get("/transcription/unlock")
async def unlock_transcription_queue(session: SessionDep,
                                   credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]):
    "Allow new jobs to be submitted (admin only)"
    user, is_admin = validate_credentials(credentials)
    if not is_admin:
        raise HTTPException(401, "Unauthorized")
    app.server_lock = False
    return {"ok": True}


@app.get("/transcription/")
async def get_transcription_list(session: SessionDep, 
                                 credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
                                 offset: int = 0,
                                 limit: Annotated[int, Query(le=100)]= 100) -> list[TranscriptionJob]:
    """Return a list of all of the transcription jobs"""
    user, is_admin = validate_credentials(credentials)    
    results = []
    for x in session.exec(select(TranscriptionJob).offset(offset).limit(limit)).all():
        if is_admin or x.owner == user:
            results.append(x)
    return results

@app.post("/transcription/")
async def new_transcription_job(req: TranscriptionRequest, 
                                session: SessionDep,
                                credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]) -> TranscriptionJob:
    """Create a new transcription job"""
    # Basically, we're going to convert the request into json and store it in the
    # database so we can reconsitute it at processing time.  The rest of the data
    # is the processing/status information that the processing will fill in.
    user, is_admin = validate_credentials(credentials)  
    if app.server_lock:
        raise HTTPException(503, "Submitting new jobs is prohibited")
    job = TranscriptionJob(owner=user,
                           state=TranscriptionState.QUEUED,
                           message="Job has been queued",
                           request=req.model_dump_json(),
                           priority=int(req.priority),
                           queue_time=time.time())
    
    session.add(job)
    session.commit()
    session.refresh(job)    
    return job


@app.delete("/transcription/{id}")
async def delete_transcription_job(id: int, 
                                   session: SessionDep,
                                   credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]):
    """Delete a transcription job.  If it is queued we'll delete it
       from the database, otherwise we'll set it to canceled"""
    user, is_admin = validate_credentials(credentials)  
    job = session.get(TranscriptionJob, id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not is_admin and job.owner != user:
        raise HTTPException(status_code=403, detail="Unauthorized")

    if job.state != TranscriptionState.RUNNING:
        session.delete(job)        
    else:
        job.state = TranscriptionState.CANCELED
    session.commit()
    return {"ok": True}


@app.get("/transcription/{id}")
async def get_transcript_job(id: int, 
                             session: SessionDep,
                             credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]) -> TranscriptionJob:
    """Return the information about a given transcription job"""
    user, is_admin = validate_credentials(credentials)  
    job = session.get(TranscriptionJob, id)    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not is_admin and job.owner != user:
        raise HTTPException(status_code=403, detail="Unauthorized")
    if job.state in (TranscriptionState.FINISHED, TranscriptionState.CANCELED, 
                     TranscriptionState.ERROR, TranscriptionState.EXPIRED):
        # clean up the database row -- they got their status so we can remove the job.
        req = TranscriptionRequest(**json.loads(job.request))
        if req.notification_type == 'poll':
            # the polling notification clears early
            session.delete(job)
            session.commit()
    
    return job


async def process_transcription_queue():
    """This is a background thread that runs whisper jobs in order"""
    while True:
        try:
            with Session(engine) as session:
                # we're just starting up so we need to do some maintenance
                # reset anything that's running to queued.         
                for running in session.exec(select(TranscriptionJob).where(TranscriptionJob.state == TranscriptionState.RUNNING)):
                    running.state = TranscriptionState.QUEUED
                session.commit()
            
                # now time for the core of this monstrosity.                
                config: ServerConfig = app.server_config
                while True:      
                    # if some jobs have been canceled since we last ran our check, let's clean them up.
                    for canceled in session.exec(select(TranscriptionJob).where(TranscriptionJob.state == TranscriptionState.CANCELED)):
                        session.delete(canceled)                
                    session.commit()

                    # do the database cleanup, and handle any outstanding notifications
                    for outstanding in session.exec(select(TranscriptionJob)):
                        if outstanding.state in (TranscriptionState.FINISHED, TranscriptionState.EXPIRED, TranscriptionState.ERROR):
                            req = TranscriptionRequest(**json.loads(outstanding.request))
                            if req.notification_type == 'url' and not outstanding.url_notified:
                                r = requests.put(req.notification_url, json=outstanding.model_dump())
                                if r.status_code == 200:
                                    outstanding.url_notified = True
                            if time.time() > req.expiration + outstanding.finish_time:
                                session.delete(outstanding)

                    # TODO: handle if the cancel happens while we're running.  The processing needs to finish, but
                    # we should throw away the database row.  Not sure how to track it.
                    #for queued in session.exec(select(TranscriptionJob).where(TranscriptionJob.state == TranscriptionState.QUEUED)):

                    queued = session.exec(select(TranscriptionJob)
                                            .where(TranscriptionJob.state == TranscriptionState.QUEUED)
                                            .order_by(TranscriptionJob.priority.desc(), TranscriptionJob.queue_time)
                                            .limit(1)).first()
                    if queued:                    
                        queued.state = TranscriptionState.RUNNING
                        queued.message = "Transcription started"
                        queued.start_time = time.time()
                        session.commit()
                        # The engine to use is embedded in the request field, so we need to
                        # extract it and make our choice.
                        req = TranscriptionRequest(**json.loads(queued.request))
                        xscript_engine = req.options.engine
                        # real work would happen here.  
                        processors = {'openai-whisper': process_whisper,
                                      'whisper.cpp': process_whispercpp}
                        if xscript_engine in processors:
                            parms = {}
                            for k, v in req.options.model_dump().items():
                                if k not in ('input', 'outputs'):
                                    parms[k] = v

                            logging.info(f"Starting transcription job {queued.id} ({queued.priority}, {queued.queue_time}) on {xscript_engine}: {parms}")
                            await asyncio.to_thread(processors[xscript_engine], queued, config)
                            logging.info(f"Finished transcribing {queued.id}, {queued.state}: {queued.message}")
                        else:
                            logging.warning(f"Client has requested an invalid transcription engine for job {queued.id}: {xscript_engine}")
                            queued.state = TranscriptionState.ERROR
                            queued.message = f"Selected transcription engine {xscript_engine} is not available"
                        
                        queued.finish_time = time.time()    

                        # attempt to notify the client if the url notification scheme was selected
                        if req.notification_type == 'url':
                            r = requests.put(req.notification_url, json=queued.model_dump())
                            if r.status_code == 200:
                                queued.url_notified = True

                        session.commit()
                    # give some time before polling the queue again.
                    await asyncio.sleep(10)
        except Exception as e:
            logging.exception(f"Something sploded: {e}")                
            # wait for 10 seconds in case it's a logic/syntax error so we can 
            # actually kill it from the command line
            await asyncio.sleep(10)

