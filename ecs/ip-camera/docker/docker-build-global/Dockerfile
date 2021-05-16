# Use python3 image
#FROM python:3-alpine
FROM alpine
# Set working directory
WORKDIR /app

# Update apk
RUN apk update

# Install dependencies
#RUN apk add --no-cache live-media-utils
RUN apk add --no-cache bash
RUN apk add  --no-cache aws-cli
RUN apk add --no-cache inotify-tools
RUN apk add --no-cache ffmpeg
RUN apk add --no-cache tzdata \
&& ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \ 
&& echo "Asia/Shanghai" > /etc/timezone


# Create virtual environment
# RUN python -m venv /opt/venv
# ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements file
#COPY requirements.txt /app/requirements.txt

COPY copyfiles.sh /app/copyfiles.sh
COPY recordCam.sh /app/recordCam.sh
COPY main.sh /app/main.sh


#ENABLE SERVICE
RUN chmod 777 /app/recordCam.sh 
RUN chmod 777 /app/copyfiles.sh
RUN chmod 777 /app/main.sh


ENTRYPOINT ./main.sh ${INPUT_URL} ${BUCKET_NAME} ${CAMERA_NAME} ${SEGMENT_TIME}