#!/bin/bash

echo $(date +%F" "%H:%M:%S)"|Begining convert ${INPUT_URL} of ${CAMERA_NAME} to ${BUCKET_NAME}"

if [ -z "$REGION" ]
then
aws s3 ls ${BUCKET_NAME}
else
aws s3 ls ${BUCKET_NAME} --region=${REGION}
fi

nohup ./copyfiles.sh ${BUCKET_NAME} ${CAMERA_NAME} >> ./output.log 2>&1 &
./recordCam.sh ${INPUT_URL}