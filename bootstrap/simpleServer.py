import http.server
import os
import sys
import io
import subprocess
FILE = 'bootstrap.html'
PORT = 8081


class DeployHandler(http.server.SimpleHTTPRequestHandler):

    # def _set_headers(self):
    #     self.send_response(200)
    #     self.send_header('Content-type', 'text/html')
    #     self.end_headers()

    def _set_headers(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.send_header('Access-Control-Allow-Origin', '*')
        http.server.SimpleHTTPRequestHandler.end_headers(self)

    def do_GET(self):
        print("GET received!")
        print("get body {}".format(self))
        if self.path == '/':
            self.path = '/bootstrap.html'
        return http.server.SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        print("POST received!")

        content_length = int(self.headers.get_all('content-length')[0])
        post_content = self.rfile.read(content_length).decode()
        accessKey = post_content.strip().split("&")[0].split("=")[1]
        securityKey = post_content.strip().split("&")[1].split("=")[1]
        regionDeploy = post_content.strip().split("&")[2].split("=")[1]
        print("POST contents are accessKey:{}, securityKey {}, regionDeploy {}".format(accessKey, securityKey, regionDeploy))
        self._set_headers()

        self.wfile.write("generating AWS profile...\n".encode())

        configCommand = "cat > ~/.aws/configbk <<EOF" + "\n" + "[default]" + "\n" + "region=" + regionDeploy + "\n" + "EOF"
        credentialCommand = "cat > ~/.aws/credentialsbk <<EOF" + "\n" + "[default]" + "\n" + "aws_access_key_id=" + accessKey + "\n" + "aws_secret_access_key=" + securityKey + "\n" + "EOF"
        # check https://docs.python.org/3/library/subprocess.html#popen-constructor for more details
        # generate profile automatically
        deployResult = subprocess.Popen(configCommand, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.wfile.write(deployResult.stdout.read())
        deployResult = subprocess.Popen(credentialCommand, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.wfile.write(deployResult.stdout.read())

        self.wfile.write("generating AWS profile complete\n".encode())
        self.wfile.flush()

        # cdk bootstrap
        self.wfile.write("bootstrapping CDK enviroment...\n".encode())
        deployResult = subprocess.Popen('cdk bootstrap', shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        # transform to byte obects
        # while True:
        #     line = deployResult.stdout.readlines()
        #     if not line:
        #         break
        #     print(line)

        for line in io.TextIOWrapper(deployResult.stdout, encoding="utf-8"):
            print(line)
            # self.send_response(200)
            # self.send_header('Content-type', 'text/plain')
            # self.send_header('Access-Control-Allow-Origin', '*')
            # self.send_header('Content-Length', len(line))
            # http.server.SimpleHTTPRequestHandler.end_headers(self)
            self.wfile.write(line.encode())
        #self.wfile.write(deployResult.stdout.read())
        self.wfile.write("bootstrapping CDK enviroment complete\n".encode())
        self.wfile.flush()

        # start to deploy cdk assets
        self.wfile.write("start to execute CDK deployment...\n".encode())
        deployCommand = 'cdk deploy --require-approval=never'
        deployResult = subprocess.Popen(deployCommand, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for line in io.TextIOWrapper(deployResult.stdout, encoding="utf-8"):
            print(line)
            # self.send_response(200)
            # self.send_header('Content-type', 'text/plain')
            # self.send_header('Access-Control-Allow-Origin', '*')
            # self.send_header('Content-Length', len(line))
            # http.server.SimpleHTTPRequestHandler.end_headers(self)
            self.wfile.write(line.encode())
        # # transform to byte obects
        # self.wfile.write(deployResult.stdout.read())
        self.wfile.write("CDK deployment complete\n".encode())
        self.wfile.flush()


def start_server():
    """Start the server."""
    server_address = ("", PORT)
    server = http.server.HTTPServer(server_address, DeployHandler)
    server.serve_forever()

start_server()