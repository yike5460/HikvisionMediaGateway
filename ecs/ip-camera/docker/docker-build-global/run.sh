#!/bin/bash
docker run -e INPUT_URL='admin:Aws@Hikvision@161.189.214.195:554/dac/realplay/D92E907C-E6E0-4CF9-96BC-68EF8703E1591/MAIN/TCP' \
    -e BUCKET_NAME='hikvisionipcamera' \
    -e CAMERA_NAME='cam01' \
    -e SEGMENT_TIME='30' \
    ip-camera