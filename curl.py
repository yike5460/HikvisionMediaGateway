# Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at
#
# http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.
#
# Author: kyiamzn@amazon.com
# Revision: v1.0
import time
import json
from optparse import OptionParser
import requests
from requests.auth import HTTPDigestAuth
from datetime import datetime, timedelta, timezone

import boto3
# from boto3.dynamodb.conditions import Key, Attr

# from crontab import CronTab

# sqs = boto3.resource('sqs', region_name="cn-northwest-1")
# ddb = boto3.resource('dynamodb', region_name="cn-northwest-1")

url = ""
payload = {}
headers = {}

# fetch local private & public IP address & region
url = "http://169.254.169.254/latest/meta-data/local-ipv4"
response = requests.request("GET", url, headers=headers, data = payload)
privateIP = response.text
url = "http://169.254.169.254/latest/meta-data/public-ipv4"
response = requests.request("GET", url, headers=headers, data = payload)
publicIP = response.text
url = "http://169.254.169.254/latest/meta-data/placement/region"
response = requests.request("GET", url, headers=headers, data = payload)
region = response.text

# define our marco here
USER = "admin"
DefaultPASSWORD = "Hikvision@AWS"

# change this marco to new value accordingly
PASSWORD = "Hikvision@AWS"
DeviceGatewayName = "AWS"

UserOperation = "/ISAPI/Security/users?format=json"
DeviceOperation = "/ISAPI/System/deviceInfo?format=json"
DeviceList = "/ISAPI/ContentMgmt/DeviceMgmt/deviceList?format=json"
GatewayPortMap = "/ISAPI/System/Network/PortMaps/contentMgmt?format=json"
DevicePortMap = "/ISAPI/System/Network/PortMaps/devMgmt?format=json"
DeviceReboot = "/ISAPI/System/reboot?format=json"
TimeOperation = "/ISAPI/System/time?format=json"
MediaURLOperation = "/ISAPI/System/streamMedia?format=json&devIndex="

ssm = boto3.client('ssm', region_name=region)

def main():

    OptionGATEWAYNAME = ssm.get_parameter(Name='GatewayName')['Parameter']['Value']
    OptionPASSWORD = ssm.get_parameter(Name='Password')['Parameter']['Value']
    OptionTIMEZONE = int(ssm.get_parameter(Name='Timezone')['Parameter']['Value'])
    print('password fetch from SSM is {}'.format(OptionPASSWORD))
    print('gateway name fetch from SSM is {}'.format(OptionGATEWAYNAME))
    print('timezone fetch from SSM is {}'.format(OptionTIMEZONE))
    # parser = OptionParser(usage="%prog [-g] [-p] [-t]", version="%prog 1.0")
    # parser.add_option("-g", "--gatewayName", dest="gatewayName", action="store", type="string", metavar="file name", help="custom gateway name")
    # parser.add_option("-p", "--password", dest="password", action="store", type="string", metavar="password string", help="user input password")
    # parser.add_option("-t", "--timezone", dest="timezone", action="store", type="int", metavar="timezone offset (e.g. 8 for UTC+8:00)", help="local timezone")
    # (options, args) = parser.parse_args()
  
    # change initial password to customized one, remember initial password need to be set in AMI first
    url = "http://" + privateIP + UserOperation
    payload = "{\r\n    \"UserList\": [\r\n        {\r\n            \"User\": {\r\n                \"id\": 1,\r\n                \"userName\": \"admin\",\r\n                \"password\": \"" + OptionPASSWORD + "\",\r\n                \"loginPassword\": \""+ DefaultPASSWORD +"\"\r\n            }\r\n        }\r\n    ]\r\n}"
    headers = {
      'Content-Type': 'application/json'
    }

    response = requests.request("PUT", url, headers=headers, data = payload, auth=HTTPDigestAuth(USER, DefaultPASSWORD))
    PASSWORD = OptionPASSWORD

    # DefaultPASSWORD = OptionPASSWORD
    print('password set status %s' % json.dumps(response.text))

    """
    # show current user
    url = "http://" + privateIP + UserOperation
    response = requests.request("GET", url, headers=headers, data = payload, auth=HTTPDigestAuth(USER, PASSWORD))
    print(json.dumps(response.text))
    """

    # change gateway name
    url = "http://" + privateIP + DeviceOperation

    payload = "{\r\n    \"DeviceInfo\": {\r\n        \"deviceName\": \"" + OptionGATEWAYNAME + "\"\r\n    }\r\n}"
    headers = {
      'Content-Type': 'application/json'
    }
    # json.loads(payload)[]
    response = requests.request("PUT", url, headers=headers, data = payload, auth=HTTPDigestAuth(USER, PASSWORD))
    print('gateway name set status %s' % json.dumps(response.text))

    # get platform port mapping
    url = "http://" + privateIP + GatewayPortMap
    payload  = {}
    headers= {}
    response = requests.request("GET", url, headers=headers, data = payload, auth=HTTPDigestAuth(USER, PASSWORD))
    postPayload = json.loads(response.text)

    # setting for succussive POST
    postPayload['MgmtPortMaps']['PortList'][0]["externalPort"] = postPayload['MgmtPortMaps']['PortList'][0]["internalPort"]
    postPayload['MgmtPortMaps']['PortList'][1]["externalPort"] = postPayload['MgmtPortMaps']['PortList'][1]["internalPort"]
    postPayload['MgmtPortMaps']['PortList'][2]["externalPort"] = postPayload['MgmtPortMaps']['PortList'][2]["internalPort"]
    postPayload['MgmtPortMaps']['AddrList'][0]["externalIPAddress"] = publicIP
    postPayload['MgmtPortMaps']['enabled'] = True

    # set platform port mapping
    url = "http://" + privateIP + GatewayPortMap
    payload = json.dumps(postPayload)
    headers = {
      'Content-Type': 'application/json'
    }
    response = requests.request("PUT", url, headers=headers, data = payload, auth=HTTPDigestAuth(USER, PASSWORD))
    print('platform port mapping set status %s' % json.dumps(response.text))


    # get device port mapping
    url = "http://" + privateIP + DevicePortMap

    payload = {}
    headers= {}
    response = requests.request("GET", url, headers=headers, data = payload, auth=HTTPDigestAuth(USER, PASSWORD))
    postPayload = json.loads(response.text)

    # setting for succussive POST
    postPayload['DevPortMaps']['PortList'][0]["Single"]["externalPort"] = postPayload['DevPortMaps']['PortList'][0]["Single"]["internalPort"]
    postPayload['DevPortMaps']['PortList'][1]["Single"]["externalPort"] = postPayload['DevPortMaps']['PortList'][1]["Single"]["internalPort"]
    postPayload['DevPortMaps']['PortList'][2]["Range"]["maxExternalPort"] = postPayload['DevPortMaps']['PortList'][2]["Range"]["maxInternalPort"]
    postPayload['DevPortMaps']['PortList'][2]["Range"]["minExternalPort"] = postPayload['DevPortMaps']['PortList'][2]["Range"]["minInternalPort"]
    postPayload['DevPortMaps']['PortList'][3]["Single"]["externalPort"] = postPayload['DevPortMaps']['PortList'][3]["Single"]["internalPort"]
    postPayload['DevPortMaps']['PortList'][4]["Single"]["externalPort"] = postPayload['DevPortMaps']['PortList'][4]["Single"]["internalPort"]
    postPayload['DevPortMaps']['PortList'][5]["Single"]["externalPort"] = postPayload['DevPortMaps']['PortList'][5]["Single"]["internalPort"]
    postPayload['DevPortMaps']['PortList'][6]["Single"]["externalPort"] = postPayload['DevPortMaps']['PortList'][6]["Single"]["internalPort"]
    postPayload['DevPortMaps']['enabled'] = True

    # set device port mapping
    url = "http://" + privateIP + DevicePortMap
    payload = json.dumps(postPayload)
    headers = {
      'Content-Type': 'application/json'
    }
    response = requests.request("PUT", url, headers=headers, data = payload, auth=HTTPDigestAuth(USER, PASSWORD))
    print('device port mapping set status %s' % json.dumps(response.text))

    # set timezone
    url = "http://" + privateIP + TimeOperation

    # timezone string concatenation according to Hikvision format
    utc_tz = datetime.utcnow().replace(tzinfo=timezone.utc)
    tmp_tz = utc_tz.astimezone(timezone(timedelta(hours=OptionTIMEZONE)))
    tmpString = str(tmp_tz).split(" ")[1]
    cur1 = str(tmp_tz).split(" ")[1].find('.')
    cur2 = str(tmp_tz).split(" ")[1].find('+')

    dest_tz = str(tmp_tz).split(" ")[0] + "T" + tmpString[:cur1]+tmpString[cur2:]
    payload = "{\r\n    \"Time\": {\r\n        \"localTime\": \"" + dest_tz + "\",\r\n        \"timeMode\": \"manual\"\r\n    }\r\n}"
    headers = {
      'Content-Type': 'text/plain'
    }

    response = requests.request("PUT", url, headers=headers, data = payload, auth=HTTPDigestAuth(USER, PASSWORD))
    print('timezone set status %s' % json.dumps(response.text))

    # we need to restart gateway for all configuration take effect (device port mapping etc.)
    url = "http://" + privateIP + DeviceReboot

    payload = {}
    headers= {}

    response = requests.request("PUT", url, headers=headers, data = payload, auth=HTTPDigestAuth(USER, PASSWORD))
    print('device reboot status %s' % json.dumps(response.text))

    # # init sqs and dynamoDB here
    # queue = sqs.create_queue(QueueName='deviceMediaUrlList', Attributes = {'DelaySeconds':'5'})
    # table = ddb.create_table(
    #   TableName='deviceMediaURL',
    #   #Partition key
    #   KeySchema=[
    #       {
    #         'AttributeName': 'deviceUUID',
    #         'KeyType': 'HASH'
    #       },
    #   ],
    #   AttributeDefinitions=[
    #       {
    #         'AttributeName': 'deviceUUID',
    #         'AttributeType': 'S'
    #       },
    #   ],
    #   ProvisionedThroughput={
    #     'ReadCapacityUnits': 10,
    #     'WriteCapacityUnits': 10
    #   }
    # )
    # table.meta.client.get_waiter('table_exists').wait(TableName='deviceMediaURL')


def test():
    url = "http://localhost/ISAPI/Event/notification/subscribeDeviceMgmt?format=json"

    payload = "{\r\n    \"SubscribeDeviceMgmt\": {\r\n        \"eventMode\": \"all\",\r\n        \"defenceMode\": \"all\"\r\n    }\r\n}"
    headers = {
      'Content-Type': 'text/plain'
    }
    session = requests.Session()
    session.auth = HTTPDigestAuth("admin", "Aws@Hikvision")

    r = session.post(url, headers=headers, data=payload, stream=True)
    for line in r.iter_lines():
      if line:
        print(line.decode("utf8"))

if __name__ == "__main__":
  main()
  # test()
