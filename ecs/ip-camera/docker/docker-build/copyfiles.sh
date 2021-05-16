#!/usr/bin/env bash
basePath=/app/videos
mkdir -p $basePath
cd $basePath

inotifywait -m -q -e close_write --format %f . | while IFS= read -r file; do
   year=`date +%Y`
   month=`date +%m`
   day=`date +%d`
   echo "----Move  $basePath/$file to s3://${BUCKET_NAME}/${CAMERA_NAME}/$year/$month/$day/$file"
if [ -z "$REGION" ]
then
 aws s3 mv "$basePath/$file" s3://${BUCKET_NAME}/${CAMERA_NAME}/$year/$month/$day/$file
else
 aws s3 mv "$basePath/$file" s3://${BUCKET_NAME}/${CAMERA_NAME}/$year/$month/$day/$file  --region=${REGION}
fi
done
