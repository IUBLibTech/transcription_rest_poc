#!/bin/env python3
"""
Create a presigned upload (put) link for something on S3
"""
import argparse
import logging
from datetime import timedelta
from os import environ
import boto3
from botocore.config import Config

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", default=False, action="store_true", help="Turn on debugging")
    parser.add_argument("method", choices=['get', 'put'], help="Request method")    
    parser.add_argument("url", help="Endpoint URL")
    parser.add_argument("bucket", help="Bucket")
    parser.add_argument("object", help="object")
    parser.add_argument("--expires", default=7, type=int, help="Expiration in days")
    
    args = parser.parse_args()
    logging.basicConfig(format="%(asctime)s [%(name)s:%(levelname)s]: %(message)s",
                        level=logging.DEBUG if args.debug else logging.INFO)
    
    expires = timedelta(days=args.expires).total_seconds()

    root_access_key = environ['ROOT_ACCESS_KEY']
    root_secret_key = environ['ROOT_SECRET_KEY']
    
    print(gen_presigned(root_access_key, root_secret_key, args.url, args.method, args.bucket, args.object, expires))


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
