"""Process a whisper transcript request"""
import time
import requests
from tempfile import TemporaryDirectory
import whisper
from job_model import TranscriptionJob, TranscriptionState
from .whisper_model import WhisperOptions
import json
import sys
from io import StringIO
from whisper.utils import WriteJSON, WriteTXT, WriteVTT
from whisper.transcribe import transcribe
import subprocess
from config_model import ServerConfig
import logging
import torch

def process_whisper(job: TranscriptionJob, config: ServerConfig):
    """The heavy lifting.  This actually runs a whisper job based on
       the parameters."""
    # we're in a separate thread from the rest of the asyncio stuff, which
    # means we're not going to bog down the web interface.  Maybe.  It may
    # still need to be pushed into a different process, we'll see.    
    model = None
    try:        
        # Get our original request from the job
        req = WhisperOptions(**json.loads(job.request)['options'])
        with TemporaryDirectory() as tmpdir:
            # download the file
            with requests.get(url=req.input, stream=True) as r:
                if r.status_code == 403:
                    # it was denied.  Just assume the presigned URL has
                    # expired.
                    job.state = TranscriptionState.EXPIRED
                    job.message = "The Presigned URL has likely expired"
                    return                    
                r.raise_for_status()                    
                with open(tmpdir + "/input_audio.dat", 'wb') as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        f.write(chunk)


            # convert the file to wave.
            p = subprocess.run(['ffmpeg', '-i', tmpdir + "/input_audio.dat",
                            tmpdir + "/input_audio.wav"], stderr=subprocess.STDOUT,
                            stdout=subprocess.PIPE, check=True)

            # load the model
            #model = whisper.load_model(req.model, download_root=sys.path[0] + "/models/openai-whisper")
            logging.debug(f"Cuda is {'available' if torch.cuda.is_available() else 'not available'}.")
            model = whisper.load_model(req.model, download_root=config.files.models_dir + "/openai-whisper",
                                       device="cuda" if torch.cuda.is_available() else "cpu")

            # prep and load the file
            audio = whisper.load_audio(tmpdir + "/input_audio.dat", 16000)
            job.media_length = len(audio) / 16000
            start = time.time()
            lang = str(req.language)
            result = transcribe(model, audio, 
                                language=lang if lang != 'auto' else None,
                                word_timestamps=True)
            job.processing_time = time.time() - start
            job.language_used = req.language
            # produce the outputs and write them to the destinations
            for fmt, url, cls, opts in (('json', req.outputs.json_url, WriteJSON, {}),
                                        ('vtt', req.outputs.vtt_url, WriteVTT, {}),
                                        ('txt', req.outputs.txt_url, WriteTXT, {})):
                if url:
                    f = StringIO()
                    c = cls('/tmp')   
                    c.write_result(result, f, opts)                     
                    r = requests.put(url, data=f.getvalue(),)
                    if r.status_code == 403:
                        job.state = TranscriptionState.EXPIRED
                        job.message = f"Expired URL when uploading {fmt} to {url}"
                    r.raise_for_status()
            
            job.state = TranscriptionState.FINISHED
            job.message = "Transcription has completed successfully"    

            if req.outputs.meta_url:
                # try to write the metadata out.  I don't really care if it fails.
                r = requests.put(req.outputs.meta_url, data=job.model_dump_json())

    except Exception as e:
        job.state = TranscriptionState.ERROR
        job.message = str(e)
        logging.exception(f"Transcription Exception for job {job}: {e}")

    finally:
        if model:
            del model.encoder
            del model.decoder
            model = None
        torch.cuda.empty_cache()
