#!/bin/env python3
import argparse
import logging
import uvicorn
from pathlib import Path
import yaml
import rest_server
from config_model import ServerConfig
import sys

def main():
    global server_conf    
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", default=False, action="store_true", help="Enable debug logging")
    parser.add_argument("--reload", default=False, action="store_true", help="Automatically reload the app if it changes")
    parser.add_argument("config", type=Path, help="Configuration file path")
    args = parser.parse_args()

    with open(args.config) as f:
        server_conf = ServerConfig(**yaml.safe_load(f))
    
    # inject the server root
    server_conf.server.root = str(Path(sys.path[0], '..').resolve().absolute())

    # inject the server configuration into the app object.  This is a little gross
    # but there we are.    
    rest_server.app.server_config = server_conf

    # logging configuration with fastapi and uvicorn is hard, but here's one inline
    logging_conf = {'version': 1,
                    'disable_existing_loggers': False,
                    'formatters': {
                        'uv_default': {'class': 'uvicorn.logging.DefaultFormatter', 'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'},
                        'access': {'class': 'uvicorn.logging.AccessFormatter', 'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'},
                        'default': {'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'}
                    },
                    'handlers': {
                        'uv_default': {'formatter': 'uv_default', 
                                       'class': 'logging.FileHandler', 
                                       'filename': server_conf.files.log_dir + "/uvicorn.log"},
                        'access': {'formatter': 'access', 
                                   'class': 'logging.FileHandler', 
                                   'filename': server_conf.files.log_dir + "/uvicorn-access.log"},
                        'default': {'formatter': 'default',
                                    'class': 'logging.FileHandler',
                                    'filename': server_conf.files.log_dir + "/default.log"
                                    }
                    },
                    'loggers': {
                        'uvicorn.error': {'level': 'INFO',
                                          'handlers': ['uv_default'],
                                          'propagate': False},
                        'uvicorn.access': {'level': 'INFO',
                                           'handlers': ['access'],
                                           'propagate': False},
                        'urllib3.connectionpool': {'level': 'INFO',
                                                   'handlers': ['default'],
                                                   'propagate': False}
                    },
                    'root': {
                        'level': 'DEBUG' if args.debug else 'INFO',
                        'handlers': ['default'],
                        'propagate': False
                    }
    }



    # run the application
    uvicorn.run(rest_server.app, 
                host=server_conf.server.host,
                port=server_conf.server.port,
                reload=args.reload,
                reload_dirs=sys.path[0],
                log_config=logging_conf,                
                )

if __name__ == "__main__":
    main()