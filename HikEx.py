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
import sys
import boto3
import logging
import time
import uuid
from os import getenv
from optparse import OptionParser
from botocore.exceptions import ClientError

LOGGING_LEVEL = getenv('LOGGING_LEVEL', 'INFO')

logger = logging.getLogger(__name__)
if getenv('AWS_EXECUTION_ENV') is None:
  logging.basicConfig(stream=sys.stdout, level=LOGGING_LEVEL)
else:
  logger.setLevel(LOGGING_LEVEL)

ec2 = boto3.client('ec2', region_name="cn-northwest-1")
s3 = boto3.client('s3', region_name="cn-northwest-1")
iam = boto3.client('iam', region_name="cn-northwest-1")
ec2Resource = boto3.resource('ec2')

""" 
First above all, we need to create the credential file. By default, its location is at ~/.aws/credentials:

[default]
aws_access_key_id = YOUR_ACCESS_KEY
aws_secret_access_key = YOUR_SECRET_KEY
You may also want to set a default region. This can be done in the configuration file. By default, its location is at ~/.aws/config:

[default]
region=cn-northwest-1
"""

def create_keypair():
    # create key pair
    # create a file to store the key locally
    outfile = open('ec2-keypair.pem', 'w')
    # call boto3 do the create
    key_pair = ec2.create_key_pair(KeyName='ec2-keypair')
    # capture the key and store it in a file
    KeyPairOut = str(key_pair['KeyMaterial'])
    outfile.write(KeyPairOut)

def main():
    parser = OptionParser(usage="%prog [-e] [-m] [-n] [-g] [-p] [-t]", version="%prog 1.0")
    # param to create elastic ip, ec2 instance, s3 (by default)
    parser.add_option("-e", "--elasticIP", dest="eip", action="store", type="string", metavar="IP address",
                        help="elastic IP address like '1.2.3.4 5.6.7.8'")
    parser.add_option("-m", "--machineType", dest="machineType", action="store", type="string", metavar="EC2 type",
                        help="EC2 type to select")
    parser.add_option("-n", "--number", dest="number", action="store", type="string", metavar="EC2 instance number",
                        help="number of EC2 instance to select")

    # param passed into ec2 user data
    parser.add_option("-g", "--gatewayName", dest="gatewayName", action="store", type="string", metavar="gateway name",
                      help="custom gateway name")
    parser.add_option("-p", "--password", dest="password", action="store", type="string", metavar="password string",
                      help="user input password")
    parser.add_option("-t", "--timezone", dest="timezone", action="store", type="int", metavar="timezone offset (e.g. 8 for UTC+8:00)", help="local timezone")

    (options, args) = parser.parse_args()

    # assemble elastic ip address provided
    eipOptionList=[]
    for eip in options.eip.split(' '):
        eipOptionList.append(eip)

    # create_keypair()

    # create ec2 with fixed AMI assigned user data
    user_data = '<powershell>' + '\n'+ r'python C:\Users\Administrator\curl.py' + ' -g ' + options.gatewayName + ' -p ' + options.password + ' -t ' + str(options.timezone) + '\n' + '</powershell>'
    security_group_id = 'sg-xxxx'
    # search AMI by AMI name (provided during image creation).
    images = ec2.describe_images(
        Owners=['self'], 
        Filters=[
            {
                'Name': 'tag:version',
                'Values': [
                    # replace with your AMI name
                    'v1.1',
                ]
            },
        ]
    )

    # create security group
    response = ec2.describe_vpcs(
        Filters=[
            {
                'Name': 'isDefault',
                'Values': [
                    'true',
                ]
            },
        ]
    )
    vpc_id = response.get('Vpcs', [{}])[0].get('VpcId', '')
    logger.info(vpc_id)
    try:
        # uuid.uuid3(uuid.NAMESPACE_DNS, 'aws.amazon.com')
        response = ec2.create_security_group(GroupName=str(uuid.uuid1()),
                                            Description='customized Hikvision security group',
                                            VpcId=vpc_id)
        security_group_id = response['GroupId']
        logger.info('Security Group Created %s in vpc %s.' % (security_group_id, vpc_id))

        data = ec2.authorize_security_group_ingress(
            GroupId=security_group_id,
            IpPermissions=[
                {'IpProtocol': 'tcp',
                'FromPort': 80,
                'ToPort': 80,
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}]},

                {'IpProtocol': 'tcp',
                'FromPort': 443,
                'ToPort': 443,
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}]},

                {'IpProtocol': 'tcp',
                'FromPort': 554,
                'ToPort': 554,
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}]},

                {'IpProtocol': 'udp',
                'FromPort': 554,
                'ToPort': 554,
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}]},

                {'IpProtocol': 'tcp',
                'FromPort': 15000,
                'ToPort': 17000,
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}]},

                {'IpProtocol': 'tcp',
                'FromPort': 7661,
                'ToPort': 7666,
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}]},

                {"IpProtocol": "tcp",
                "FromPort": 3389,
                "ToPort": 3389,
                "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                "PrefixListIds": [
                    {"PrefixListId": "pl-1fa54076"}
                ],
                "UserIdGroupPairs": [],
                "Ipv6Ranges": []
                }
            ])
        logger.info('Ingress Successfully Set %s' % data)
    except ClientError as e:
        logger.info(e)

    instance = ec2Resource.create_instances(
        BlockDeviceMappings=[
            {
                'DeviceName': '/dev/sda1',
                'Ebs': {
                    'DeleteOnTermination': True,
                    'VolumeSize': 500,
                    'VolumeType': 'gp2'
                }
            },
        ],
        ImageId=images['Images'][0]["ImageId"],
        InstanceType=options.machineType,
        KeyName="ec2-keypair",
        MaxCount=int(options.number),
        MinCount=1,
        Monitoring={
            'Enabled': False
        },
        SecurityGroupIds=[
            security_group_id,# 'sg-07a3a422ed7d9c36a',
        ],
        # SubnetId='subnet-cf03d4b4',
        UserData=user_data,
        EbsOptimized=True,
        TagSpecifications=[
            {
                'ResourceType': 'instance',
                'Tags': [
                    {
                        'Key': 'Name',
                        'Value': 'HikDebug'
                    },
                ]
            },
        ],
        CpuOptions={
            'CoreCount': 2,
            'ThreadsPerCore': 2
        }
    )

    # waite ec2 instance running before attach elastic ip
    # TBD wait for more instance rather than instance[0] only
    waiteHandler = ec2Resource.Instance(instance[0].id)
    waiteHandler.wait_until_running()

    # list current elastic ip pool and allocate elatic ip if not match with option -e
    filters = [
        {'Name': 'domain', 'Values': ['vpc']}
    ]
    eipPool = ec2.describe_addresses(Filters=filters)
    logger.info(json.dumps(eipPool))

    allicationDict = {}
    eipFound = False
    for i in range(int(options.number)):
        if eipPool:
            for eip_dict in eipPool['Addresses']:
                if eip_dict['PublicIp'] == eipOptionList[i]:
                    allicationDict = eip_dict
                    eipFound = True
                    logger.info("elastic IP {} with AllocationId {} found in current pool for instance {}"
                    .format(eip_dict['PublicIp'], eip_dict['AllocationId'], instance[i].id))
        if not eipFound:
            allicationDict = ec2.allocate_address(Domain='vpc')
            logger.info("provided elastic IP {} NOT found in current pool or elastic IP pool is empty, allocate new one {} for instance {}"
            .format(eipOptionList[i], allicationDict['PublicIp'], instance[i].id))
        # associate to ec2 instance
        try:
            response = ec2.associate_address(AllocationId=allicationDict['AllocationId'], InstanceId=instance[i].id)
            logger.info(response)
        except ClientError as e:
            logger.info(e)
    """
    # release ec2 elastic ip
    try:
        response = ec2.release_address(AllocationId='ALLOCATION_ID')
        logger.info('Address released')
    except ClientError as e:
        logger.info(e)
    """

    session = boto3.session.Session()
    current_region = session.region_name
    s3.create_bucket(
        ACL='private', #|'public-read'|'public-read-write'|'authenticated-read',
        Bucket=str(uuid.uuid1()),
        CreateBucketConfiguration={
            'LocationConstraint': current_region
        },
        # GrantFullControl='Aaron',
        # GrantRead='string',
        # GrantReadACP='string',
        # GrantWrite='string',
        # GrantWriteACP='string',
        ObjectLockEnabledForBucket=False
    )

    # create ec2 instance profile to allow ec2 had full access s3 bucket
    response = iam.create_instance_profile(
        InstanceProfileName='S3FullAccessRoleInstanceProfile'
        # Path='string'
    )

    # create iam role with principal as ec2
    AssumeRolePolicyDocument = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                "Effect": "Allow",
                "Principal": {
                    "Service": "ec2.amazonaws.com.cn"
                },
                "Action": "sts:AssumeRole"
                }
            ]
        }
    )
    response = iam.create_role(
        # Path='string',
        RoleName='S3FullAccessRole',
        AssumeRolePolicyDocument=AssumeRolePolicyDocument,
        Description='nothing here',
        #MaxSessionDuration=123,
        #PermissionsBoundary='string',
        # Tags=[
        #     {
        #         'Key': 'string',
        #         'Value': 'string'
        #     },
        # ]
    )
    logger.info(response)

    # attach such role with full s3 access
    response = iam.attach_role_policy(
        RoleName='S3FullAccessRole',
        PolicyArn='arn:aws-cn:iam::aws:policy/AmazonS3FullAccess'
    )
    logger.info(response)

    # attach complete role with instance profile
    response = iam.add_role_to_instance_profile(
        InstanceProfileName='S3FullAccessRoleInstanceProfile',
        RoleName='S3FullAccessRole'
    )
    logger.info(response)
    # wait for instance fully complete
    time.sleep(5)

    response = ec2.associate_iam_instance_profile(
        IamInstanceProfile={
            #'Arn': 'string',
            # replace with option name TBD
            'Name': 'S3FullAccessRoleInstanceProfile'
        },
        InstanceId=instance[0].id
    )
    logger.info(response)

def test():
    pass
if __name__ == "__main__":
    main()
    # test()