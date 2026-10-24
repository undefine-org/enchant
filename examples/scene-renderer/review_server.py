#!/usr/bin/env python3
"""Small developer review server with single byte-range video requests."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re

class Handler(SimpleHTTPRequestHandler):
    protocol_version='HTTP/1.1'

    def send_head(self):
        self.remaining=None
        path=self.translate_path(self.path)
        if not os.path.isfile(path):return super().send_head()
        try:source=open(path,'rb')
        except OSError:
            self.send_error(404,'File not found');return None
        stat=os.fstat(source.fileno());size=stat.st_size
        start,end=0,size-1;range_header=self.headers.get('Range')
        if range_header is not None:
            match=re.fullmatch(r'bytes=(\d*)-(\d*)',range_header.strip())
            try:
                if not match or not any(match.groups()) or size==0:raise ValueError()
                first,last=match.groups()
                if first:
                    start=int(first);end=min(int(last),size-1) if last else size-1
                else:
                    suffix=int(last)
                    if suffix<=0:raise ValueError()
                    start=max(0,size-suffix)
                if start>=size or start>end:raise ValueError()
            except ValueError:
                source.close();self.send_response(416)
                self.send_header('Content-Range',f'bytes */{size}')
                self.send_header('Content-Length','0');self.end_headers();return None
        length=max(0,end-start+1);self.remaining=length
        self.send_response(206 if range_header is not None else 200)
        self.send_header('Content-Type',self.guess_type(path))
        self.send_header('Content-Length',str(length))
        self.send_header('Accept-Ranges','bytes')
        self.send_header('Last-Modified',self.date_time_string(stat.st_mtime))
        if range_header is not None:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.end_headers();source.seek(start);return source

    def copyfile(self,source,outputfile):
        try:
            if self.remaining is None:return super().copyfile(source,outputfile)
            left=self.remaining
            while left:
                block=source.read(min(left,65536))
                if not block:break
                outputfile.write(block);left-=len(block)
        except (BrokenPipeError,ConnectionResetError):pass # browser changed seek target

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path)
    parser.add_argument('--bind',default='127.0.0.1');parser.add_argument('--port',default=4050,type=int)
    args=parser.parse_args()
    with ThreadingHTTPServer((args.bind,args.port),partial(Handler,directory=str(args.directory.resolve()))) as server:
        server.serve_forever()
