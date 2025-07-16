"""Process a whisper.cpp transcript request"""
import time
import requests
from tempfile import TemporaryDirectory
from job_model import TranscriptionJob, TranscriptionState
from .whispercpp_model import WhisperCPPOptions
import json
import sys
import subprocess
from pathlib import Path
import re
from config_model import ServerConfig

def process_whispercpp(job: TranscriptionJob, config: ServerConfig):
    """The heavy lifting.  This actually runs a whisper.cpp job based on
       the parameters."""   
    p = None
    try:
        # Get our original request from the job
        req = WhisperCPPOptions(**json.loads(job.request)['options'])
        with TemporaryDirectory() as tmpdir:
            try:
                print(f"starting whisper.cpp for {job.id}")    
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
                #rest_dir = Path(sys.path[0])
                #model_file = rest_dir / "models/whisper.cpp" / ('ggml-' + req.model + ".bin")
                #whispercpp = rest_dir / "whisper.cpp/whisper-cli"
                model_file = Path(config.files.models_dir, 'whisper.cpp', f"ggml-{req.model}.bin")
                whispercpp = config.server.root + "/whisper.cpp/whisper-cli"
                start = time.time()
                p = subprocess.run([str(whispercpp), 
                                    tmpdir + "/input_audio.wav",
                                    '--model', str(model_file),
                                    '-of', tmpdir + "/output",
                                    '-ojf', '-otxt', '-ovtt', '-ocsv', 
                                    '-t', '8', '-l', req.language], 
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                    encoding='utf-8',
                                    check=True)

                job.processing_time = time.time() - start
                for fmt, url in (('json', req.outputs.json_url),
                                 ('vtt', req.outputs.vtt_url),
                                 ('csv', req.outputs.csv_url),
                                 ('txt', req.outputs.txt_url)):
                    if url:
                        data = Path(tmpdir, f"output.{fmt}").read_text()                            
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
                    print(p.stdout)

                job.state = TranscriptionState.FINISHED
                job.message = "Transcription has completed successfully"    

                if req.outputs.meta_url:
                    # try to write the metadata out.  I don't really care if it fails.
                    r = requests.put(req.outputs.meta_url, data=job.model_dump_json())

            except Exception as e:
                job.state = TranscriptionState.ERROR
                job.message = str(e)
                print("interior exception", e)
                print(job)
                if p:
                    print(p.stdout)
    except Exception as e:
        print(f"EGADS, it failed!: {e}")
        job.state = TranscriptionState.ERROR
        job.message = str(e)