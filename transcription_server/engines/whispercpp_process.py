"""Process a whisper.cpp transcript request"""
import time
import requests
from tempfile import TemporaryDirectory
from job_model import TranscriptionJob, TranscriptionState
from .whispercpp_model import WhisperCPPOptions
import json
import subprocess
from pathlib import Path
import re
from config_model import ServerConfig
import logging

def process_whispercpp(job: TranscriptionJob, config: ServerConfig):
    """The heavy lifting.  This actually runs a whisper.cpp job based on
       the parameters."""   
    try:
        # Get our original request from the job
        req = WhisperCPPOptions(**json.loads(job.request)['options'])
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

            # get the rest service root directory 
            model_file = Path(config.files.models_dir, 'whisper.cpp', f"ggml-{req.model}.bin")
            if not model_file.exists():
                # download the file.                
                logging.info(f"Downloading whisper.cpp model {req.model}")
                model_file.parent.mkdir(parents=True, exist_ok=True)
                src = "https://huggingface.co/ggerganov/whisper.cpp"
                prefix = "resolve/main/ggml"
                r = requests.get(f"{src}/{prefix}-{req.model}.bin")
                r.raise_for_status()
                with open(model_file, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1048576):
                        if chunk:
                            f.write(chunk)

            whispercpp = config.server.root + "/whisper.cpp/whisper-cli"
            start = time.time()
            p = subprocess.run([str(whispercpp), 
                                tmpdir + "/input_audio.wav",
                                '--model', str(model_file),
                                '-of', tmpdir + "/output",
                                '-ojf', '-otxt', '-ovtt', '-ocsv', 
                                '-t', '8', '-l', str(req.language)], 
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                encoding='utf-8')
            if p.returncode != 0:
                logging.error(f"Cannot run {p.args}: {p.stdout}")
                raise Exception(f"returned non-zero return code {p.returncode}")

            job.processing_time = time.time() - start
            for fmt, url in (('json', req.outputs.json_url),
                                ('vtt', req.outputs.vtt_url),
                                ('csv', req.outputs.csv_url),
                                ('txt', req.outputs.txt_url)):
                if url:
                    data = Path(tmpdir, f"output.{fmt}").read_bytes()  # was read_text() and it'd fail.
                    r = requests.put(url, data=data)
                    if r.status_code == 403:
                        job.state = TranscriptionState.EXPIRED
                        job.message = f"Expired URL when uploading {fmt} to {url}"
                    r.raise_for_status()
            
            # fill in the language and media time.
            m = re.search(r'samples, (\d+\.\d+) sec\),.+, lang = (..)', p.stdout)
            if m:
                job.language_used = m.group(2)
                job.media_length = float(m.group(1))
            else:
                logging.warning(f"Cannot parse sample data! {p.stdout}")

            job.state = TranscriptionState.FINISHED
            job.message = "Transcription has completed successfully"    

            if req.outputs.meta_url:
                # try to write the metadata out.  I don't really care if it fails.
                r = requests.put(req.outputs.meta_url, data=job.model_dump_json())

    except Exception as e:
        logging.exception(f"Transcription Exception for job {job}: {e}")
        job.state = TranscriptionState.ERROR
        job.message = str(e)

