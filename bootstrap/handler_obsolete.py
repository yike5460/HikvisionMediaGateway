#!/usr/bin/env python
"""
Very simple HTTP server in python.
Usage::
    ./handler.py [<port>]
Send a GET request::
    curl http://localhost
Send a HEAD request::
    curl -I http://localhost
Send a POST request::
    curl -d "foo=bar&bin=baz" http://localhost
"""

import os
import cgi
import http
import threading
from socketserver import ThreadingMixIn
from http.server import BaseHTTPRequestHandler, HTTPServer, SimpleHTTPRequestHandler

class CORSRequestHandler(SimpleHTTPRequestHandler):
    def _set_headers(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_header('Access-Control-Allow-Origin', '*')
        SimpleHTTPRequestHandler.end_headers(self)
        # self.end_headers()

    def do_GET(self):
        self._set_headers()
        self.wfile.write(("<html><body><h1>mini Python Server is working</h1></body></html>").encode())

    def do_POST(self):
        form = cgi.FieldStorage(
            fp = self.rfile,
            headers = self.headers,
            environ = {'REQUEST_METHOD': 'POST'}
        )

        # 获取 POST 过来的 Value
        value = form.getvalue("key")
        print("POST value is {}".format(value))
        self._set_headers()
        self.wfile.write(value.encode())


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """ This class allows to handle requests in separated threads.
        No further content needed, don't touch this. """


def run(server_class=HTTPServer, handler_class=CORSRequestHandler, port=8081):
    server_address = ('', port)
    httpd = ThreadedHTTPServer(server_address, handler_class)
    print('Starting httpd on 8081...')
    httpd.serve_forever()


if __name__ == "__main__":
    from sys import argv
    if len(argv) == 2:
        run(port=int(argv[1]))
    else:
        run()