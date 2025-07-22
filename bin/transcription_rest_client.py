#!/bin/env python3

import argparse
from os import environ
import requests
import json
import boto3
from botocore.config import Config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("endpoint", help="REST Service Endpoint")
    subparsers = parser.add_subparsers(dest="action", required=True)
    
    list_parser = subparsers.add_parser("list", help="List all jobs in the service")
    
    purge_parser = subparsers.add_parser("purge", help="Purge any jobs where the client never finalized it")

    info_parser = subparsers.add_parser("info", help="Information about a job")    
    info_parser.add_argument("id", type=int, help="Job ID")

    delete_parser = subparsers.add_parser("delete", help="Cancel a job")
    delete_parser.add_argument("id", type=int, help="Job ID")

    submit = subparsers.add_parser("whisper", help="Submit a new whisper job")
    submit.add_argument("s3_endpoint", type=str, help="S3 server endpoint")
    submit.add_argument("input_bucket", type=str, help="Bucket containing the input file")
    submit.add_argument("input_object", type=str, help="Object key for the input file")
    submit.add_argument("--output_bucket", type=str, default=None, help="Bucket containing the output files (if different than input bucket)")
    submit.add_argument('--priority', default=1, type=int, choices=[0, 1, 2], help="Job priority")
    submit.add_argument("--language", default="en", 
                        choices=['auto', 'en', 'es', 'fr', 'de'], 
                        help="Language to use")    
    submit.add_argument("--model", default="small.en", 
                        choices=["tiny.en", "tiny", "base.en", "base", 
                                 "small.en", "small", "medium.en", "medium", 
                                 "large-v1", "large-v2", "large-v3", "large-v3-turbo"],
                        help="Model to use for transcription")
    for fmt in ('json', 'vtt', 'txt', 'meta'):
        submit.add_argument(f"--{fmt}", type=str, help=f"Object name for {fmt} output")

    submit = subparsers.add_parser("whispercpp", help="Submit a new whispercpp job")
    submit.add_argument("s3_endpoint", type=str, help="S3 server endpoint")
    submit.add_argument("input_bucket", type=str, help="Bucket containing the input file")
    submit.add_argument("input_object", type=str, help="Object key for the input file")
    submit.add_argument("--output_bucket", type=str, default=None, help="Bucket containing the output files (if different than input bucket)")
    submit.add_argument('--priority', default=1, type=int, choices=[0, 1, 2], help="Job priority")
    submit.add_argument("--language", default="en", 
                        choices=['auto', 'en', 'es', 'fr', 'de'], 
                        help="Language to use")    
    submit.add_argument("--model", default="small.en", 
                        choices=["tiny", "tiny.en", "tiny-q5_1", "tiny.en-q5_1", "tiny-q8_0", 
                                 "base", "base.en", "base-q5_1", "base.en-q5_1", "base-q8_0", "small", 
                                 "small.en", "small.en-tdrz", "small-q5_1", "small.en-q5_1", "small-q8_0", 
                                 "medium", "medium.en", "medium-q5_0", "medium.en-q5_0", "medium-q8_0", 
                                 "large-v1", 
                                 "large-v2", "large-v2-q5_0", "large-v2-q8_0", 
                                 "large-v3", "large-v3-q5_0", 
                                 "large-v3-turbo", "large-v3-turbo-q5_0", "large-v3-turbo-q8_0"],
                        help="Model to use for transcription")
    for fmt in ('json', 'vtt', 'txt', 'csv', 'meta'):
        submit.add_argument(f"--{fmt}", type=str, help=f"object name for {fmt} output")

    lock = subparsers.add_parser("lock", help="Lock/Unlock the submission queue")
    lock.add_argument("state", choices=["on", "off"], help="Turn on/off the submission queue lock")

    args = parser.parse_args()

    # check environment variables
    args.token = environ.get('TRANSCRIPTION_TOKEN', None)
    if args.token is None:
        print("You must set the TRANSCRIPTION_TOKEN environment variable")
        exit(1)

    if args.action in ('whisper', 'whispercpp'):
        # we need to have S3_ACCESS_KEY and S3_SECRET_KEY environment
        # variables to talk to S3
        args.access_key = environ.get('S3_ACCESS_KEY', None)
        args.secret_key = environ.get('S3_SECRET_KEY', None)
        if args.access_key is None or args.secret_key is None:
            print("You must have S3_ACCESS_KEY and S3_SECRET_KEY environment variables set")
            exit(1)

    try:
        {'list': list_jobs,
         'purge': purge_jobs,
        'info': job_info,
        'delete': delete_job,
        'whisper': whisper,
        'whispercpp': whisper_cpp,
        'lock': manage_lock}[args.action](args)
    except Exception as e:
        print(f"Error: {e}")    


def list_jobs(args):
    r = requests.get(args.endpoint + "/transcription/",
                     headers={'Authorization': f'Bearer {args.token}'})
    r.raise_for_status()
    dump_json(r.json())


def purge_jobs(args):
    r = requests.get(args.endpoint + "/transcription/",
                     headers={'Authorization': f"Bearer {args.token}"})
    for j in r.json():
         r = requests.get(args.endpoint + f"/transcription/{j['id']}",
                     headers={'Authorization': f"Bearer {args.token}"})   

    print("Extraneous rows should be purged")


def job_info(args):    
    r = requests.get(args.endpoint + f"/transcription/{args.id}",
                     headers={'Authorization': f'Bearer {args.token}'})
    r.raise_for_status()
    dump_json(r.json())
    

def delete_job(args):
    r = requests.delete(args.endpoint + f"/transcription/{args.id}",
                     headers={'Authorization': f'Bearer {args.token}'})
    r.raise_for_status()
    dump_json(r.json())


def whisper(args):
    # build the base options for a whisper submit.
    options = {'engine': 'openai-whisper',
               'language': args.language,
               'model': args.model,
               'input': '',
               'outputs': {}
               }
    vargs = vars(args)
    for fmt in ('json', 'txt', 'vtt', 'meta'):
        out_obj = vargs.get(fmt, None)
        if out_obj is not None:
            options['outputs'][f"{fmt}_url"] = out_obj
    if not options['outputs']:
        raise ValueError("At least one output format must be selected")
    submit_job(args, options)


def whisper_cpp(args):
    # build the base options for a whispercpp submit.
    options = {'engine': 'whisper.cpp',
               'language': args.language,
               'model': args.model,
               'input': '',
               'outputs': {}
               }
    vargs = vars(args)
    for fmt in ('json', 'txt', 'vtt', 'csv', 'meta'):
        out_obj = vargs.get(fmt, None)
        if out_obj is not None:
            options['outputs'][f"{fmt}_url"] = out_obj
    if not options['outputs']:
        raise ValueError("At least one output format must be selected")
    submit_job(args, options)


def submit_job(args, options):
    "Here's where the submission magic happens"
    # first, we need to generate a presigned get url for the input...
    if args.input_object.startswith('http://') or args.input_object.startswith('https://'):
        options['input'] = args.input_object
    else:
        options['input'] = gen_presigned(args.access_key, args.secret_key,
                                        args.s3_endpoint, 'get', args.input_bucket,
                                        args.input_object, 7*24*3600-1)
    # and then generate presigned put urls for the outputs...
    if args.output_bucket is None:
        args.output_bucket = args.input_bucket
    new_outputs = {}
    for k in options['outputs']:
        if options['outputs'][k].startswith('http://') or options['outputs'][k].startswith('https://'):
            pass  # already a URL
        else:
            new_outputs[k] = gen_presigned(args.access_key, args.secret_key,
                                           args.s3_endpoint, 'put', args.output_bucket,
                                           options['outputs'][k], 7*24*3600-1)
    options['outputs'] = new_outputs
    options['priority'] = args.priority

    dump_json(options)
    r = requests.post(args.endpoint + f"/transcription/",
                        headers={'Authorization': f'Bearer {args.token}'},
                        json={'version': '1',
                              'options': options})
    if r.status_code == 422:
        print(r.content)
    r.raise_for_status()
    dump_json(r.json())


def manage_lock(args):
    "Turn on/off the job queue lock"
    if args.state == "on":
        r = requests.get(args.endpoint + "/transcription/lock")
    else:
        r = requests.get(args.endpoint + "/transcription/unlock")
    r.raise_for_status()
    

def dump_json(data):
    print(json.dumps(data, indent=2, sort_keys=True))


def gen_presigned(access_key, secret_key, endpointurl, method, bucket, object, expires):
    s3_client = boto3.client('s3',
                             endpoint_url=endpointurl,
                             use_ssl=endpointurl.startswith("https:"),
                             aws_access_key_id=access_key,
                             aws_secret_access_key=secret_key,
                             region_name="us-east-1",
                             config=Config(s3={'addressing_style': 'path'},
                                           signature_version='s3v4')
                             )
    return s3_client.generate_presigned_url(f'{method}_object', 
                                           Params={'Bucket': bucket, 
                                                   'Key': object},
                                           ExpiresIn=int(expires)
                                           )


if __name__ == "__main__":
    main()