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
# Author: Yi, Ke (kyiamzn@amazon.com)
# Revision: v1.0

import os.path

from aws_cdk.aws_s3_assets import Asset
from aws_cdk.aws_lambda_event_sources import DynamoEventSource
import uuid

from aws_cdk.aws_events import Rule, Schedule
from aws_cdk.aws_events_targets import LambdaFunction

from aws_cdk import (
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_s3 as s3,
    aws_autoscaling as autoscaling,
    aws_dynamodb as ddb,
    aws_ssm as ssm,
    aws_lambda as _lambda,
    aws_ecs as ecs,
    aws_ecr as ecr,
    core
)

dirname = os.path.dirname(__file__)

# AMI for native
AMIImage = 'HikStageRho'

# AMI for global
# AMIImage = 'HikvisionGlobalDelta'

class EC2InstanceStack(core.Stack):

    def __init__(self, scope: core.Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # key pair won't be create by CF, create (ec2-keypair e.g.) before we launch

        # parameter here mapping from python version
        # elastic ip
        optionElasticIP = core.CfnParameter(self, "ElasticIP", default="192.168.1.1", description="elastic IP address like '1.2.3.4 5.6.7.8'", no_echo=None, type="String").value_as_string
        # machine type
        optionMachineType = core.CfnParameter(self, "MachineType", default="c5.xlarge", description="EC2 type to select'", no_echo=None, type="String").value_as_string
        # instance number, obsolete now
        # optionInstanceNumber = core.CfnParameter(self, "InstanceNumber", default="1", description="number of EC2 instance to select'", no_echo=None, type="Number").value_as_number

        # gateway name
        optionGatewayName = core.CfnParameter(self, "GatewayName", default="Hikvision", description="custom gateway name'", no_echo=None, type="String").value_as_string
        # password
        optionPassword = core.CfnParameter(self, "Password", default="Hikvision@AWS", description="user input password", no_echo=True, type="String").value_as_string
        # timezone
        optionTimezone = core.CfnParameter(self, "Timezone", default="8", description="timezone offset (e.g. 8 for UTC+8:00)", no_echo=None, type="String").value_as_string
        # segment
        optionSegmentDuration = core.CfnParameter(self, "SegmentDuration", default="900", description="video segment duration", no_echo=None, type="String").value_as_string
        # segment format
        optionSegmentFormat = core.CfnParameter(self, "SegmentFormat", default="copy", description="video segment format", no_echo=None, type="String").value_as_string
        # video sizing
        optionSegmentSizing = core.CfnParameter(self, "SegmentSizing", default="default", description="video segment sizing", no_echo=None, type="String").value_as_string
        # video transcoding method
        optionSegmentTranscoding = core.CfnParameter(self, "SegmentTranscoding", default="copy", description="video segment transcoding method", no_echo=None, type="String").value_as_string
        # bucket transition
        optionBucketTransition = core.CfnParameter(self, "BucketTransition", default=7, description="days before bucket transition to glacier", no_echo=None, type="Number").value_as_number

        # using default VPC
        # vpc = ec2.Vpc.from_lookup(self, "VPC",
        #     # This imports the default VPC but you can also
        #     # specify a 'vpcName' or 'tags'.
        #     is_default=True
        # )

        # don't create private network to save cost of NAT gateway, using 11.0.0.0/16 to avoid possible subnet confliction
        vpc = ec2.Vpc(self, "VPC", max_azs=2, cidr="11.0.0.0/16", nat_gateways=0,
            subnet_configuration=[ec2.SubnetConfiguration(name="public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24),
                                ec2.SubnetConfiguration(name="private", subnet_type=ec2.SubnetType.ISOLATED, cidr_mask=24)])

        vpc.add_s3_endpoint("s3VpcEndpoint")
        vpc.add_dynamo_db_endpoint("dynamoDBEndpoint")
        vpc.add_interface_endpoint("ssmVpcEndpoint", service=ec2.InterfaceVpcEndpointAwsService.SSM, lookup_supported_azs=None, open=None, private_dns_enabled=None, security_groups=None, subnets=None)
        vpc.add_interface_endpoint("ec2VpcEndpoint", service=ec2.InterfaceVpcEndpointAwsService.EC2, lookup_supported_azs=None, open=None, private_dns_enabled=None, security_groups=None, subnets=None)

        # find specific Hikvision image, filters={'name': ['tag:version'], 'value': ['v1.1',]}
        HikAMI = ec2.MachineImage.lookup(name=AMIImage, owners=['self'], windows=True)

        # create security group to allow RDP access
        HikSG = ec2.SecurityGroup(self, "HikvisionSG", vpc=vpc, allow_all_outbound=True, description="Hikvision SG for RDP access")
        HikSG.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80), 'HTTP from anywhere');
        HikSG.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(443), 'HTTPs from anywhere');
        HikSG.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(554), 'RTSP from anywhere');
        HikSG.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.udp(554), 'RTSP from anywhere');
        HikSG.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp_range(7661, 7666), 'Hikvision custom port from anywhere');
        HikSG.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp_range(15000, 17000), 'Hikvision custom port from anywhere');
        HikSG.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(3389), 'RDP access from anywhere');

        # create and attach instance role for full s3 access
        role = iam.Role(self, "S3SQSDDB", assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"))
        role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name(managed_policy_name="AmazonS3FullAccess"))
        role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name(managed_policy_name="AmazonSQSFullAccess"))
        role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name(managed_policy_name="AmazonDynamoDBFullAccess"))
        # method 1, using auto scaling group, not support elastic ip association natively, consider using user data do the elastic ip association
        # user_data = '\n'+ r'python C:\Users\Administrator\curl.py' + ' -g ' + optionGatewayName + ' -p ' + optionPassword + ' -t ' + optionTimezone + '\n'
        # asg = autoscaling.AutoScalingGroup(self, "ASG",
        #                                     instance_type=ec2.InstanceType(optionMachineType),
        #                                     machine_image=HikAMI,
        #                                     vpc=vpc,
        #                                     role=role,
        #                                     # security_group=HikSG,
        #                                     #ser_data=user_data,
        #                                     associate_public_ip_address=None,
        #                                     desired_capacity=optionInstanceNumber,
        #                                     max_capacity=optionInstanceNumber,
        #                                     min_capacity=optionInstanceNumber,
        #                                     key_name="ec2-keypair"
        #                                     # vpc_subnets=
        #                                     )

        # asg.add_user_data(user_data)
        # asg.add_security_group(HikSG)

        # method 2, using cfn auto scaling group, to retrieve instance_id and associate elastic ip accordingly
        # classaws_cdk.aws_autoscaling.CfnAutoScalingGroup

        # method 3, using ec2.instance method to launch instance seperately
        # for i in range(int(optionInstanceNumber)):
        # instanceId = "Instance" + str('i')
        # lanuch the instance
        instance = ec2.Instance(self, 'HikvisionMediaGateway',
            instance_type=ec2.InstanceType(optionMachineType),
            machine_image=HikAMI,
            vpc = vpc,
            # key_name = "ec2-keypair",
            security_group=HikSG,
            role = role,
            # by default ENIs will preferentially be placed in subnets not connected to the Internet
            vpc_subnets = ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC)
        )
        core.Tag.add(instance, "Application", "Hikvision")
        # allocate elastic IP and assciate to instance, TBD consider optionElasticIP was provided, using user data to associate elastic
        # ec2.CfnEIP(self, "HikvisionElaticIP", instance_id=instance.instance_id)

        ec2.CfnEIPAssociation(self, "HikvisionElaticIP", eip=optionElasticIP, instance_id=instance.instance_id)
        # user data assemble
        # user_data = '\n'+ r'python C:\Users\Administrator\curl.py' + ' -g ' + optionGatewayName + ' -p ' + optionPassword + ' -t ' + optionTimezone + '\n'
        user_data = '\n'+ r'python C:\Users\Administrator\curl.py' + '\n'
        instance.user_data.add_commands(user_data)

        '''using script in s3 as asset'''
        # asset = Asset(self, "Asset", path=os.path.join(dirname, "configure.ps1"))
        # local_path = instance.user_data.add_s3_download_command(
        #     bucket=asset.bucket,
        #     bucket_key=asset.s3_object_key
        # )

        # # Userdata executes script from S3
        # instance.user_data.add_execute_file_command(
        #    file_path=local_path
        # )

        # asset.grant_read(instance.role)

        '''create S3 bucket'''
        bucket = s3.Bucket(self, 'HikvisionBucket', bucket_name='hikvisionmedia'+str(uuid.uuid1()), removal_policy=core.RemovalPolicy.DESTROY)

        transition = s3.Transition(storage_class=s3.StorageClass.GLACIER, transition_after=core.Duration.days(optionBucketTransition))
        bucket.add_lifecycle_rule(enabled=True, id='Hikvision', transitions=[transition,])

        '''create dynamoDB, make sure all resource are created in cdk not in AMI python script'''
        dynamoDBTable = ddb.Table(self, 'HikvisionDynamoDB', table_name='deviceMediaURL', partition_key=ddb.Attribute(name="deviceUUID", type=ddb.AttributeType.STRING),
        sort_key=ddb.Attribute(name="channel", type=ddb.AttributeType.STRING), read_capacity=10, removal_policy=core.RemovalPolicy.DESTROY, stream=ddb.StreamViewType.NEW_AND_OLD_IMAGES, write_capacity=10)

        dynamoDBTableBack = ddb.Table(self, 'HikvisionDynamoDBBack', table_name='ip-camera', partition_key=ddb.Attribute(name="deviceUUID", type=ddb.AttributeType.STRING), read_capacity=10, removal_policy=core.RemovalPolicy.DESTROY, stream=ddb.StreamViewType.NEW_AND_OLD_IMAGES, write_capacity=10)

        # create SSM parameters. note currently CloudFormation NOT support creation of SecureString parameter, means password are stored in SSM as plaintext that my led minor security issue, and we can only create SecureString with AWS CLI/SDK and refer in CloudFormation as parameter
        # aws kms create-key --description "A key to encrypt-decrypt secrets" (note the KeyId in output)
        # aws ssm put-parameter --name "/your/path/key" --value "your password" --type SecureString --key-id "KeyId" --description "This is a secret parameter"
        ParamGatewayName = ssm.StringParameter(self, 'ParamGatewayName', string_value=optionGatewayName, type=ssm.ParameterType.STRING, description="device gateway name", 
        parameter_name="GatewayName", simple_name=None, tier=None)
        ParamGatewayName.grant_read(role)

        ParamPassword = ssm.StringParameter(self, 'ParamPassword', string_value=optionPassword, type=ssm.ParameterType.STRING, description="device gateway password", 
        parameter_name="Password", simple_name=None, tier=None)
        ParamPassword.grant_read(role)

        ParamTimezone = ssm.StringParameter(self, 'ParamTimezone', string_value=optionTimezone, type=ssm.ParameterType.STRING, description="device gateway timezone", 
        parameter_name="Timezone", simple_name=None, tier=None)
        ParamTimezone.grant_read(role)

        '''ECS cluster creation
        If using the Fargate launch type, the awsvpc network mode is required, If the network mode is awsvpc:
        - Task is allocated an elastic network interface, and you must specify a NetworkConfiguration when you create a service or run a task with the task definition
        - For task definitions that use the awsvpc network mode, you should only specify the containerPort. The hostPort can be left blank or it must be the same value as the containerPort.
        - Tasks and services that use the awsvpc network mode require the Amazon ECS service-linked role to provide Amazon ECS with the permissions to make calls to other AWS services on your behalf. This role is created for you automatically when you create a cluster
        - Currently, only Linux variants of the Amazon ECS-optimized AMI, or other Amazon Linux variants with the ecs-init package, support task networking.
        - Tasks that use the awsvpc network mode are associated with an ENI, not with an Amazon EC2 instance.
        - Fargate launch type, task placement constraints are not supported. By default Fargate tasks are spread across Availability Zones.
        '''

        '''create ecs cluster'''
        cluster = ecs.Cluster(
            self, 'HikvisionEcsCluster',
            container_insights=True,
            vpc=vpc
        )

        '''create auto scaling group and ec2 capacity'''
        # # asg = autoscaling.AutoScalingGroup(
        # #     self, "HikvisionFleet",
        # #     instance_type=ec2.InstanceType("t2.xlarge"),
        # #     machine_image=ecs.EcsOptimizedAmi(),
        # #     associate_public_ip_address=True,
        # #     update_type=autoscaling.UpdateType.REPLACING_UPDATE,
        # #     desired_capacity=3,
        # #     vpc=vpc,
        # #     vpc_subnets={'subnet_type': ec2.SubnetType.PUBLIC},
        # # )
        # # cluster.add_auto_scaling_group(asg)

        # cluster.add_capacity(id: str, *, instance_type: InstanceType, machine_image=None, can_containers_access_instance_role=None,spot_instance_draining=None, task_drain_time=None, allow_all_outbound=None, associate_public_ip_address=None, auto_scaling_group_name=None, block_devices=None, cooldown=None, desired_capacity=None, health_check=None, ignore_unmodified_size_properties=None, instance_monitoring=None, key_name=None, max_capacity=None, max_instance_lifetime=None, min_capacity=None, notifications=None, notifications_topic=None, replacing_update_min_successful_instances_percent=None, resource_signal_count=None, resource_signal_timeout=None, rolling_update_configuration=None, spot_price=None, update_type=None, vpc_subnets=None)
        # cluster.add_capacity("DefaultAutoScalingGroup", instance_type=ec2.InstanceType("t2.micro"))

        '''create a task definition'''
        # create task role to had s3 access
        ecsTaskRole = iam.Role(self, "Hikvision ECS Task Role", assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"), description="grant ECS task full access to access S3", role_name="HikvisionECSTaskRole")
        ecsTaskRole.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name(managed_policy_name="AmazonS3FullAccess"))
        task_definition = ecs.FargateTaskDefinition(self, "HikvisionTaskDef", cpu=256, memory_limit_mib=512, execution_role=None, family=None, proxy_configuration=None, task_role=ecsTaskRole, volumes=None)

        # need to push ecs docker image to ecr first
        ecrRepo = ecr.Repository.from_repository_name(self, 'HikvisionECR', 'ip-camera')
        # ecr.Repository.from_repository_arn()
        container = task_definition.add_container(
            "ip-camera",
            image=ecs.ContainerImage.from_ecr_repository(repository=ecrRepo, tag=None),
            # image=ecs.ContainerImage.from_registry("nginx:latest"),
            # container env passed into shell scripts
            environment=
            {
                "BUCKET_NAME":bucket.bucket_name, 
                "CAMERA_NAME":"CAMERA_NAME", 
                "INPUT_URL":"INPUT_URL", 
                "SEGMENT_TIME":optionSegmentDuration, 
                "SEGMENT_FORMAT":optionSegmentFormat, 
                "SIZING":optionSegmentSizing, 
                "TRANSCODING":optionSegmentTranscoding, 
                "LOG_LEVEL":"info",
                "REGION":os.environ["CDK_DEFAULT_REGION"], 
            },
            logging=ecs.LogDriver.aws_logs(stream_prefix="ecs", datetime_format=None, log_group=None, log_retention=None, multiline_pattern=None),
            memory_limit_mib=256,
        )

        '''create lambda to trigger such ecs cluster'''
        # create Lambda and associate with dynamoDB stream
        fnRole = iam.Role(self, "Hikvision Lambda Role", assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"), description="grant Lambda full access to backend ECS cluster", role_name="HikvisionLambda")
        fnRole.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name(managed_policy_name="AmazonECS_FullAccess"))
        # managed CloudWatch policy
        fnRole.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name(managed_policy_name="CloudWatchFullAccess"))
        fnRole.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name(managed_policy_name="AmazonDynamoDBFullAccess"))
        # customer System Manager policy
        ssmPolicy = iam.Policy(self, "SSMFullAccess", statements=[iam.PolicyStatement(actions=["ssm:*"], resources=["*"]),])
        fnRole.attach_inline_policy(ssmPolicy)

        fn = _lambda.Function(self, "Hikvision Lambda", code=_lambda.Code.from_asset('ecs/ip-camera/lambda'), handler="index.handler", runtime=_lambda.Runtime.NODEJS_12_X, allow_all_outbound=None,current_version_options=None, dead_letter_queue=None, dead_letter_queue_enabled=None, description="lambda to trigger backend ecs", 
        environment={
            "BUCKET_NAME":bucket.bucket_name, 
            "ECS_CLUSTER_NAME":cluster.cluster_name, 
            "ECS_CONTAINER_NAME":"ip-camera", 
            "ECS_SUBNET_ID_1":vpc.public_subnets[0].subnet_id, 
            "ECS_SUBNET_ID_2":vpc.public_subnets[1].subnet_id, 
            "ECS_TASK_NAME":task_definition.task_definition_arn, 
            "SEGMENT_TIME":optionSegmentDuration, 
            "SEGMENT_FORMAT":optionSegmentFormat, 
            "SIZING":optionSegmentSizing, 
            "TRANSCODING":optionSegmentTranscoding, 
            "LOG_LEVEL":"info", 
            "REGION":os.environ["CDK_DEFAULT_REGION"], 
            "TABLE_NAME":"ip-camera" 
        }, 
        events=None, function_name="HikvisionLambda", initial_policy=None, layers=None, log_retention=None, log_retention_retry_options=None, log_retention_role=None, memory_size=128, reserved_concurrent_executions=None, role=fnRole, security_group=None, security_groups=None, timeout=core.Duration.minutes(15), tracing=None, vpc=None, vpc_subnets=None, max_event_age=None, on_failure=None, on_success=None, retry_attempts=None)
        fn.add_event_source(DynamoEventSource(dynamoDBTable, starting_position=_lambda.StartingPosition.LATEST, batch_size=None, bisect_batch_on_error=None, max_batching_window=None, max_record_age=None, on_failure=None, parallelization_factor=10, retry_attempts=10))

        '''create port mapping and service'''
        # port_mapping = ecs.PortMapping(
        #     container_port=80,
        #     # host_port=8080,
        #     protocol=ecs.Protocol.TCP
        # )
        # container.add_port_mappings(port_mapping)

        # service = ecs.FargateService(
        #     self, "HikvisionService",
        #     cluster=cluster,
        #     task_definition=task_definition,
        # )

        '''************************ phase2 ************************'''
        '''create lambda to execute health check function'''
        fnRoleHealthCheck = iam.Role(self, "Hikvision Lambda Health Check Role", assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"), description="grant Lambda full access to monitor EC2", role_name="HikvisionLambdaHc")
        fnRoleHealthCheck.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name(managed_policy_name="AmazonEC2FullAccess"))
        fnRoleHealthCheck.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name(managed_policy_name="AmazonDynamoDBFullAccess"))
        fnRoleHealthCheck.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name(managed_policy_name="CloudWatchFullAccess"))
        # customer System Manager policy
        fnRoleHealthCheck.attach_inline_policy(ssmPolicy)

        fnHealthCheck = _lambda.Function(self, "Hikvision Lambda Health Check", code=_lambda.Code.from_asset('package'), handler="lambda_function.lambda_handler", runtime=_lambda.Runtime.PYTHON_3_7, allow_all_outbound=None, current_version_options=None, dead_letter_queue=None, dead_letter_queue_enabled=None, description="lambda to execute health check function", environment=None, events=None, function_name="HikvisionLambdaHealthCheck", initial_policy=None, layers=None, log_retention=None, log_retention_retry_options=None, log_retention_role=None, memory_size=None, reserved_concurrent_executions=None, role=fnRoleHealthCheck, security_group=None, security_groups=None, timeout=core.Duration.minutes(3), tracing=None, vpc=vpc, vpc_subnets=None, max_event_age=None, on_failure=None, on_success=None, retry_attempts=None)

        # cloudwatch event
        cloudwatchRule = Rule(self, "cloudwatchRule", description="cloudwatch event to trigger lambda", enabled=True, event_bus=None, event_pattern=None, rule_name="cloudwatchEventRule", schedule=Schedule.cron(minute='15'))

        cloudwatchRule.add_target(LambdaFunction(fnHealthCheck))

        '''cfn output'''
        core.CfnOutput(self, "media gateway elastic IP address", value=optionElasticIP, description="media gateway elastic IP address")
        core.CfnOutput(self, "media gateway machine type", value=optionMachineType, description="media gateway machine type")
        core.CfnOutput(self, "media gateway name", value=optionGatewayName, description="media gateway name")
        core.CfnOutput(self, "media gateway password", value=optionPassword, description="media gateway password")
        core.CfnOutput(self, "media gateway instance id", value="HikvisionMediaGateway", description="media gateway instance id")
        core.CfnOutput(self, "media gateway vpc id", value=vpc.vpc_id, description="media gateway vpc id")

        core.CfnOutput(self, "s3 bucket name", value=bucket.bucket_name, description="bucket to store transcoded video clips")
        core.CfnOutput(self, "s3 transition", value="check for BucketTransition in Parameters panel", description="days before object transit to glacier layer")

        core.CfnOutput(self, "ecs cluster name", value=cluster.cluster_name, description="docker cluster to handle video transcoding and archive")
        core.CfnOutput(self, "ecs task arn", value=task_definition.task_definition_arn, description="task per video channel to execute video transcoding and archive job")
        core.CfnOutput(self, "ecs video transcoding format", value=optionSegmentFormat, description="output video segement format")
        core.CfnOutput(self, "ecs video transcoding size", value=optionSegmentSizing, description="output video segement size")
        core.CfnOutput(self, "ecs video transcoding duration", value=optionSegmentSizing, description="output video segement time")

app = core.App()
EC2InstanceStack(app, "Hikvision", env=core.Environment(account=os.environ["CDK_DEFAULT_ACCOUNT"], region=os.environ["CDK_DEFAULT_REGION"]))
app.synth()
