"""Process a faster-whisper transcript request"""
import time
import requests
from tempfile import TemporaryDirectory
from job_model import TranscriptionJob, TranscriptionState
from .faster_whisper_model import FasterWhisperOptions
import json
from io import StringIO
from faster_whisper import WhisperModel
from config_model import ServerConfig
import logging
import torch
import json
import textwrap

def process_fasterwhisper(job: TranscriptionJob, config: ServerConfig):
    """The heavy lifting.  This actually runs a whisper job based on
       the parameters."""
    # we're in a separate thread from the rest of the asyncio stuff, which
    # means we're not going to bog down the web interface.  Maybe.  It may
    # still need to be pushed into a different process, we'll see.    
    model = None
    try:        
        # Get our original request from the job
        req = FasterWhisperOptions(**json.loads(job.request)['options'])
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


            # load the model            
            logging.debug(f"Cuda is {'available' if torch.cuda.is_available() else 'not available'}.")
            model = WhisperModel(req.model, download_root=config.files.models_dir + "/faster-whisper",
                                 #device="cuda" if torch.cuda.is_available() else "cpu",
                                 device="cpu",
                                 compute_type=req.compute_type)

            # run the transcription
            start = time.time()
            lang = str(req.language)
            segments, info = model.transcribe(tmpdir + "/input_audio.dat", 
                                              language=lang if lang != 'auto' else None,
                                              word_timestamps=True)
            # segments is really an iterator that does the transcription, so we have
            # to iterate through them to do the actual work.
            data = {'info': vars(info),
                    'segments': [{'start': float(s.start), 
                                    'end': float(s.end),
                                    'text': s.text,
                                    'words': [{'start': float(w.start),
                                               'end': float(w.end),
                                               'word': w.word} for w in s.words]}  
                                  for s in segments]}
            data['info']['transcription_options'] = vars(data['info']['transcription_options'])                    
            
            job.processing_time = time.time() - start
            job.language_used = info.language
            job.media_length = info.duration

            for fmt, url in (('json', req.outputs.json_url),
                             ('vtt', req.outputs.vtt_url),
                             ('txt', req.outputs.txt_url)):
                if url:
                    if fmt == 'json':
                        result = json.dumps(data, indent=4)
                
                    if fmt == 'txt':
                        words = []
                        for s in data['segments']:            
                            for w in s['words']:
                                words.append(w['word'])
                        text = ("".join(words)).strip() + "\n"
                        result = "\n".join(textwrap.wrap(text))

                    if fmt == 'vtt':
                        result = "WEBVTT\n\n"
                        for x in data['segments']:
                            result += f"{timestamp(x['start'])} --> {timestamp(x['end'])}\n{x['text']}\n\n"

                    f = StringIO()
                    f.write(result)
                    r = requests.put(url, data=f.getvalue(),)
                    if r.status_code == 403:
                        job.state = TranscriptionState.EXPIRED
                        job.message = f"Expired URL when uploading {fmt} to {url}"
                    r.raise_for_status()

            job.state = TranscriptionState.FINISHED
            job.message = "Transcription has completed successfully"                
            job.finish_time = time.time()
            if req.outputs.meta_url:
                # try to write the metadata out.  I don't really care if it fails.
                r = requests.put(req.outputs.meta_url, data=job.model_dump_json())

    except Exception as e:
        job.state = TranscriptionState.ERROR
        job.message = str(e)
        logging.exception(f"Transcription Exception for job {job}: {e}")

    finally:
        if model:            
            model = None            
        torch.cuda.empty_cache()



def timestamp(t: float):
    hours = int(t / 3600)
    t -= hours * 3600
    mins = int(t / 60)
    t -= mins * 60
    secs = float(t)
    return f"{hours:02d}:{mins:02d}:{secs:0.3f}"
    