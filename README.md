# transcription_rest_poc
A transcription REST service proof of concept

## Goals
The goal is to determine the difficulty of writing a lightweight, 
production-capable, REST-based transcription service.

It should be able to be containerized easily, expandable to handle 
multiple different engines, support S3, and minimally stateful.

Yeah, turns out it's substantially more trivial that I anticipated.

## Core Components
The core of the service is based around FastAPI.  It provides several features
which allow the creation of production-ready services:
* Entirely asynchronous, so it avoids contention with the GIL
* Endpoint documentation is generated automatically from the code and presented
  in the `/docs` endpoint.
* Utilizes the `pydantic` library so all of the JSON structures are validated
  when read and are available as python object properties to facilitate 
  code completion

For an ORM, SQLModel is used on top of a SQLite3 database
* SQLModel is created by the same developers as FastAPI so it plays well with
  the environment
* Built on top of SQLAlchemy, so many database engines are available

For the POC, two different transcription engines were used:
* The OpenAI Whisper python module was used since we're familiar with it,
  but since the module is used it's worth testing how an in-process module
  would behave when combined with asyncio and whether the models would clear
  successfully from the GPU as jobs completed
* Whisper.cpp is an out-of-process transcription program that we've been 
  wanting to experiment with.  Since it's called via subprocess.run, it allows
  us to test the impacts on subprocesses when combined with asyncio.

## Architecture
There is a single server process which implements the REST endpoints and
schedules transcription jobs in a FIFO fashion.  Since there is no advantage
to scheduling multiple transcriptions to a single GPU they are processed one
at a time.

A client is assigned a token when is used to create an Authentication Bearer 
string consisting of a `user:token` pair.

There are five endpoints:
* GET /docs - automatically generated documentation and a try-it-yourself
  interface for the service
* GET /transcription/ - will return all of the transcription requests which are
  in the system owned by the user (or if the user an admin, all of them)
* POST /transcription/ - will create a new transcription request which will 
  return a transcription json object which will include the newly created id
* DELETE /transcription/{id} - will delete a queued transcription job or 
  cancel one that's already running
* GET /transcription/{id} - will return the transcription data for the given
  id.  
  


### Creating a new transcription request
Using the POST method will create a new post request with the given engine,
model and language, and outputs.  The model and outputs vary by engine.  In
the future other engine-specific parameters may be added.

The POST data looks something like this:

```
{
  "version": "1",
  "options": {
    "engine": "openai-whisper",
    "language": "en",
    "model": "small.en",
    "input": "https://example.com/",
    "outputs": {
      "json_url": "https://example.com/",
      "vtt_url": "https://example.com/",
      "txt_url": "https://example.com/",
      "meta_url": "https://example.com/"
    }
  }
}
```
    
The `input` parameter can be any http(s) URL -- content may be read from an
open webserver or an S3 presigned GET may be supplied.  The content is loaded
at the time the processing starts so there is a possibility that the request
may happen after the presigned URL has timed out.  If that happens the status
of the job will be set to `expired` indicating that it needs to be resubmitted
with fresh URLs.

If an output format is not desired it can be omitted, but at least one
output must be present for the request to be valid.  The http(s) URL must
support a PUT operation -- such as S3 presigned PUT URL.  As with the input
URL, if the URL is unusable the job may fail and be set to `expired`.

All engines support the 'meta' type -- which is a dump of the job data which
includes the timing information.

Once the request is made it is put into the transcription job queue and the
job entry is returned to the client. It looks something like this:

```
{
  "id": 3233,
  "owner": "bdwheele",
  "state": "queued",
  "message": "Job has been queued",
  "media_length": 0,  
  "language_used": "",
  "request": "json-serialized version of the request string",
  "queue_time": 17532423423.433,
  "start_time": 0,
  "finish_time": 0,
  "processing_time": 0,
  "url_notified": false
}
```

Most of the fields will be updated as the processing proceeds.  

The status of the job can be checked by getting `/transcription/{id}`.  By
default reading the status after the job has completed will remove the job
from the database.  There are two other `notification_type` parameters that
the request can add:
* `expire` - the job will remain in the database until it expires
* `url` - with an additional parameter `notification_url` which will issue
  a put to the URL with the job data as the body.

In either of these cases, the job will remain in the database until it expires,
which is an hour after the job completed.

## Using the service from the command line

There are two components needed to use the service from the command line:
* `bin/transcription_rest_client.py`
* An S3 endpoint

NOTE: The client can be run on any recent python and doesn't have any 
dependencies on the transcription service code.  It does have a dependency on 
`boto3` to generate presigned URLs so it may need to run in a virtual 
environment or have the library installed either system-wide or in the user's 
directory.  

These environment variables need to be set to use the client:
* TRANSCRIPTION_TOKEN - the username:token for the service
* S3_ACCESS_KEY - the access key for the S3 endpoint 
* S3_SECRET_KEY - the secret key for the S3 endpoint 

The last two are only needed when creating a new job.


The client's main help page:
```
usage: transcription_rest_client.py [-h] endpoint {list,purge,info,delete,whisper,whispercpp} ...

positional arguments:
  endpoint              REST Service Endpoint
  {list,purge,info,delete,whisper,whispercpp}
    list                List all jobs in the service
    purge               Purge any jobs where the client never finalized it
    info                Information about a job
    delete              Cancel a job
    whisper             Submit a new whisper job
    whispercpp          Submit a new whispercpp job

options:
  -h, --help            show this help message and exit

```

The last two commands are used to submit new transcription jobs and they're
the most interesting:
```
usage: transcription_rest_client.py endpoint whisper [-h] [--output_bucket OUTPUT_BUCKET] [--language {auto,en,es,fr,de}]
                                                     [--model {tiny.en,tiny,base.en,base,small.en,small,medium.en,medium,large-v1,large-v2,large-v3,large-v3-turbo}]
                                                     [--json JSON] [--vtt VTT] [--txt TXT] [--meta META]
                                                     s3_endpoint input_bucket input_object

positional arguments:
  s3_endpoint           S3 server endpoint
  input_bucket          Bucket containing the input file
  input_object          Object key for the input file

options:
  -h, --help            show this help message and exit
  --output_bucket OUTPUT_BUCKET
                        Bucket containing the output files (if different than input bucket)
  --language {auto,en,es,fr,de}
                        Language to use
  --model {tiny.en,tiny,base.en,base,small.en,small,medium.en,medium,large-v1,large-v2,large-v3,large-v3-turbo}
                        Model to use for transcription
  --json JSON           Object name for json output
  --vtt VTT             Object name for vtt output
  --txt TXT             Object name for txt output
  --meta META           Object name for meta output

```



### Setting up a test environment with an S3 Proxy

First, let's set up a versity gateway S3 proxy to make the data accessible
to the transcription server.  We will run it in single user mode and proxying
only our data to the rack-only network.

We will need a directory structure that will be proxied as S3.  Assuming
that everything is based on a directory `$S3_ROOT`, these directories
should be present:
* `$S3_ROOT/input` - this is the input bucket where the source material resides
* `$S3_ROOT/output` - transcripts and metadata will be written here.

The proxy will need a few pieces of information:
* The listen address.  This address needs to be accessible by the REST server,
  but we don't want to make it public.  For our environment, 
  `<hostname>-private` is a rack-only network address and a port somewhere in 
  the 10000-20000 range.  Combine the two with a colon and store them in 
  `$VGW_PORT`.  An example value might look like `budgie-private:10323`
* The root access key.  This will be the "username" for S3 access. It should
  be stored in `$ROOT_ACCESS_KEY`
* The root secret key.  This is the "password" for S3 access.  It will be
  stored in `$ROOT_SECRET_KEY`

Now the versity S3 proxy can be started:
```
/srv/shared/vesitygw/versitygw-v1.0.15.sif --debug posix $S3_ROOT
```

At this point you now have an S3 server that is proxying your data, with an
`input` bucket and an `output` bucket.  Put your source content into the
input bucket.

Now we need to set up the environment needed for the client.  Copy the client
script somewhere convenient on the server the server with the data.  

By default boto3 isn't installed, but you can install it for your user by
running 
```
python3.12 -mpip install boto3
``` 

NOTE: The script defaults to running whatever `python3` is pointing to, which
may end up being a really old python (3.6.8).  You can either prefix the
script invocation with `python3.12` or change the shebang line to force it
to use `python3.12`.


Set up the environment variables to their appropriate values:
* TRANSCRIPTION_TOKEN - username:password for the REST server
* S3_ACCESS_KEY - the same value as the ROOT_ACCESS_KEY
* S3_SECRET_KEY - the same value as the ROOT_SECRET_KEY

Let's submit one job and see what happens.  Copy a file to the `$S3_ROOT/input`
directory.  For documentation purposes, let's call it `gettysburg.wav`.

We'll also need to know the endpoint for the rest service.  Let's call 
that `$REST_URL`. 


```
python3.12 transcription_rest_client.py $REST_URL \
    whisper http://$VGW_PORT input gettysburg.wav \
    --output_bucket output --language en --model small.en \
    --json gettysburg.json --txt gettysburg.txt --meta gettsyburg.meta
```

That should submit an openai whisper job using the small.en model with english
as the default language.  The three outputs will be stored in the output 
bucket.

It should print out the JSON of the object.  Assuming that it gave back an
id of 200, one might see something like this:

```
$ python3.12 transcription_rest_client.py $REST_URL info 200
{
  "id": 200,
  "language_used": "",
  "media_length": 0.0,
  "message": "Job has been queued",
  "owner": "bdwheele",
  "processing_time": 0.0,
  "request": "{\"version\":\"1\",\"options\":{\"engine\":\"openai-whisper\",\"language\":\"en\",\"model\":\"small.en\",\"input\":\"http://server-private:10323/input/gettysburg.wav?<aws-stuff>\",\"outputs\":{\"json_url\":\"http://server-private:10323/output/gettysburg.wav-whisper-small.en.json?<aws-stuff>\",\"txt_url\":\"http://server-private:10323/output/gettysburg.wav-whisper-small.en.txt?<aws-stuff>\",\"meta_url\":\"http://server-private:10323/output/gettysburg.wav-whisper-small.en.meta?<aws-stuff>"}}}",
  "state": "queued"
}
```

After a while the state will change to "processing" and eventually 
"finished", "expired", or "error", with a corresponding message.  If the state
ends up "finished", your files will be in the output directory.

When requesting the status and it returns something other than "queued" or 
"running" the database record (and thus the id) for this job will be removed.

## What I've learned
FastAPI is cool.  Lots of power, easy to manipulate.   The entire server 
portion of this is less than 300 lines of code (not counting the data
structures) and that's pretty incredible really.  Shoulders of giants, I
know, but still.

Pydantic is cool.  Validating data structures on the fly along with error
messages telling you where your input stucture was wrong -- big fan.  It
also helps that it means the IDE is context aware so code completion works
for these complex structures.

SQLModel is...less cool, but still kinda cool.  

My biggest beef with SQLModel is that it's not really easy to have nested
data classes and have them serialized.  I get it, it's not an easy thing to
generalize -- so that's why the request field in the object is really the
serialized request rather than it being the data structure itself.  I suppose
I could reconstitute it when validating the model.  It's not like I was 
doing queries on it anyway.  I really like the way MongoDB does it better, but
this isn't bad for trying to force a square-peg-data-structure into a 
round-hole-sql-schema.

The Uvicorn server does pretty well but getting it to log in a way that's
production-y is a little irritating.  Now that I know how it works, it's not
something that's a blocker.  It's a capable server.

Sqlite3 is great.  With the way this is constructed if we need to change the
schema in the future it's just a matter of letting everything finish, 
shutting the app down, deleting the database file, and restarting the server.

asyncio is still something that I'm trying to wrap my computer science-y 
brain around.  Coroutines in general seem like an abomination, but I've got
to admit that this works well.

Python is a joy.  Today alone I ended up writing (or tracing) code in python,
perl, java, and shell script.  Python is by far the easiest to deal with.
