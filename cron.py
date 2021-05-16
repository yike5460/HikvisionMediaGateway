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

import json
from optparse import OptionParser
import requests
from requests.auth import HTTPDigestAuth
from datetime import datetime, timedelta, timezone

import boto3
import botocore.session
from boto3.dynamodb.conditions import Key, Attr

import time

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

sqs = boto3.resource('sqs', region_name=region)
ddb = boto3.resource('dynamodb', region_name=region)
ssm = boto3.client('ssm', region_name=region)

# fetch password pass from user data
url = "http://169.254.169.254/latest/user-data"
response = requests.request("GET", url, headers=headers, data = payload)
# original user data is similar to 
# <powershell>
# python C:\Users\Administrator\curl.py -g xxx -p xxx -t xx
# </powershell>
USER = "admin"
#PASSWORD = response.text.split('-p')[1].split(' ')[1]
PASSWORD = ssm.get_parameter(Name='Password')['Parameter']['Value']
DeviceList = "/ISAPI/ContentMgmt/DeviceMgmt/deviceList?format=json"
DeviceChannelList = "/ISAPI/ContentMgmt/DeviceMgmt/channelInfo?format=json&devIndex="
MediaURLOperation = "/ISAPI/System/streamMedia?format=json&devIndex="

def main():
    # found existing sqs and dynamoDB here
    table = ddb.Table('deviceMediaURL')

    """new added code start"""
    """ get all device list """
    url = "http://" + privateIP + DeviceList

    payload = "{\r\n    \"SearchDescription\": {\r\n        \"position\": 0,\r\n        \"maxResult\": 10000\r\n    }\r\n}"
    headers = {
      'Content-Type': 'application/json'
    }

    responseDevice = requests.request("POST", url, headers=headers, data = payload, auth=HTTPDigestAuth(USER, PASSWORD))
    # fix NoneType here
    print("=====process for comparing all current devices (online & offline) with DDB=====")
    allDeviceList = []
    if json.loads(responseDevice.text)['SearchResult']["MatchList"]:
      # generate deviceUUID list of all current devices (online & offline)
      for i in range(len(json.loads(responseDevice.text)['SearchResult']["MatchList"])):
        deviceUUID = json.loads(responseDevice.text)['SearchResult']["MatchList"][i]["Device"]["devIndex"]
        allDeviceList.append(deviceUUID)
    print("current device list (online & offline) is {}".format(allDeviceList))

    # scan and purging items that not exising in current deviceUUID list, case that device are removed from GUI directly without any online & offline status left
    result = table.scan()
    with table.batch_writer() as batch:
      for each in result['Items']:
        print("current deviceUUID {}".format(each['deviceUUID']))
        if str(each['deviceUUID']) not in allDeviceList:
          print("and such one are not in allDeviceList {}".format(each['deviceUUID']))
          batch.delete_item(
              Key={
                  'deviceUUID': each['deviceUUID'],
                  'channel': each['channel']
              }
          )
    """new added code end"""

    """ get all online device list """
    url = "http://" + privateIP + DeviceList

    payload = "{\r\n    \"SearchDescription\": {\r\n        \"position\": 0,\r\n        \"maxResult\": 10000,\r\n        \"Filter\": {\r\n            \"devStatus\": [\"online\"]\r\n        }\r\n    }\r\n}"
    headers = {
      'Content-Type': 'application/json'
    }

    responseDevice = requests.request("POST", url, headers=headers, data = payload, auth=HTTPDigestAuth(USER, PASSWORD))

    # fix NoneType here
    print("=====process for add online devices=====")
    if json.loads(responseDevice.text)['SearchResult']["MatchList"]:
      print("adding new online devices")
      for i in range(len(json.loads(responseDevice.text)['SearchResult']["MatchList"])):
        deviceUUID = json.loads(responseDevice.text)['SearchResult']["MatchList"][i]["Device"]["devIndex"]
        mediaURLDict = {}
        tmpDict = {}
        mediaURLDict[deviceUUID] = deviceUUID

        # archive to dynamoDB if item not exist, and pass directly if items exist, note this process can be change to record update process depend on actual requirements
        response = table.query(
          KeyConditionExpression=Key("deviceUUID").eq(deviceUUID)
        )
        if response['Count']:
          # response = table.update_item(
          #   Key={
          #     'deviceUUID': deviceUUID
          #   },
          #   UpdateExpression='SET mediaURL = :val',
          #   ExpressiononAttributeValues={
          #     ':val':str(mediaURLDict[deviceUUID])
          #   }
          # )
          print('item found in dynamoDB, pass directly')
          continue

        # get all channel id per deviceUUID
        url = "http://" + privateIP + DeviceChannelList + deviceUUID
        payload = {}
        headers= {}

        response = requests.request("GET", url, headers=headers, data = payload, auth=HTTPDigestAuth(USER, PASSWORD))

        # parse channel value, note here j is not actually channel value and what we store into dynamoDB are just 
        # incremental number list
        if (json.loads(response.text)["ChannelInfo"]["VideoChannel"]):
          for j in range(len(json.loads(response.text)["ChannelInfo"]["VideoChannel"])):
            channelID = json.loads(response.text)["ChannelInfo"]["VideoChannel"][j]["Channel"]["id"]

            # get media url per device uuid and channel
            url = "http://" + privateIP + MediaURLOperation + deviceUUID

            payload = "{\r\n    \"StreamInfo\": {\r\n        \"id\": \"" + str(channelID) + "\",\r\n        \"streamType\": \"main\",\r\n        \"method\": \"preview\"\r\n    }\r\n}"
            headers = {
              'Content-Type': 'application/json'
            }

            response = requests.request("POST", url, headers=headers, data = payload, auth=HTTPDigestAuth(USER, PASSWORD))
            tmpDict[j] = json.loads(response.text)["MediaAccessInfo"]["URL"].split("//")[1].split("?")[0]

        mediaURLDict[deviceUUID] = tmpDict

        # mediaURLDict[deviceUUID] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

        for k in range(len(mediaURLDict[deviceUUID])):
          response = table.put_item(
            Item={
              'deviceUUID': str(deviceUUID),
              'channel': str(k),
              'mediaURL': str(mediaURLDict[deviceUUID][k]),
              'retryThreshold': "5",
            }
          )
          time.sleep(1)
          print('item NOT found in dynamoDB, create item with response {}'.format(json.dumps(response)))

    print("=====process for purge offline devices=====")

    """ get all offline device list for successive purge """
    url = "http://" + privateIP + DeviceList

    payload = "{\r\n    \"SearchDescription\": {\r\n        \"position\": 0,\r\n        \"maxResult\": 10000,\r\n        \"Filter\": {\r\n            \"devStatus\": [\"offline\"]\r\n        }\r\n    }\r\n}"
    headers = {
        'Content-Type': 'application/json'
    }
    responseDeviceOff = requests.request("POST", url, headers=headers, data = payload, auth=HTTPDigestAuth(USER, PASSWORD))

    if (json.loads(responseDeviceOff.text)['SearchResult']["MatchList"]):
      for i in range(len(json.loads(responseDeviceOff.text)['SearchResult']["MatchList"])):
        deviceUUID = json.loads(responseDeviceOff.text)['SearchResult']["MatchList"][i]["Device"]["devIndex"]
        print("purging offline device {}".format(deviceUUID))
        # purge existing device that had been offline
        scan = table.scan()
        with table.batch_writer() as batch:
            for each in scan['Items']:
              if each['deviceUUID'] == deviceUUID:
                batch.delete_item(
                    Key={
                        'deviceUUID': each['deviceUUID'],
                        'channel': each['channel']
                    }
                )
              time.sleep(1)
      # responseQuery = table.query(
      #   KeyConditionExpression=Key("deviceUUID").eq(deviceUUID)
      # )
      # if responseQuery['Count']:
      #   for j in range(responseQuery['Count']):
      #     response = table.delete_item(
      #         Key={
      #             'deviceUUID': str(deviceUUID),
      #             'channel': str(j)
      #         }
      #     )
      #     print('purge all offline items with key {}, status {}'.format(deviceUUID, json.dumps(response)))

    # note sqs logic will be obsolete in future
    #   # now send message to sqs queue
    #   queue.send_message(MessageBody=str(deviceUUID)+":"+str(mediaURLDict[deviceUUID]), MessageAttributes = {
    #     'Author': {
    #       'StringValue': 'Aaron',
    #       'DataType': 'String'
    #     }
    #   })
if __name__ == "__main__":
  main()