#!/bin/bash
# recordCam.sh
BASEpath='/app/videos'
mkdir -p $BASEpath

if [ -z "$INPUT_URL" ]
then
      : ${INPUT_URL:="wowzaec2demo.streamlock.net/vod/mp4:BigBuckBunny_175k.mov"} 
fi

if [ -z "$SEGMENT_FORMAT" ]
then
      : ${SEGMENT_FORMAT:="Video"} 
fi

if [ -z "$SEGMENT_TIME" ]
then
      : ${SEGMENT_TIME:=30} 
fi

if [ -z "$LOGLEVEL" ]
then
  : ${LOGLEVEL:=verbose} 
fi
: ${SIZING:=960} 
cmd="ffmpeg -loglevel ${LOGLEVEL} -rtsp_transport tcp -abort_on empty_output -stimeout 10000000 -stream_loop -1 -i rtsp://${INPUT_URL} "

  if [[ $SEGMENT_FORMAT = "image" ]]; 
      then 
        echo $(date +%F" "%H:%M:%S)"---convert rtsp stream to picture"
        cmd=$cmd" -vf fps=1/${SEGMENT_TIME}  -strict -2 \
        -strftime 1 $BASEpath/capture-%Y-%m-%d_%H-%M-%S.jpg"
      else 
#改变分辨率（transsizing） 480
        if [[ $SIZING != "default" ]]; 
          then
        cmd="${cmd} -s ${SIZING} "
        fi
#转换视频编码格式 libx264
        if [ -n "$TRANSCODING" ]
        then
        cmd=$cmd" -c:v $TRANSCODING "
        else
        cmd=$cmd" -c:v copy "
        fi
        echo  $(date +%F" "%H:%M:%S)"---convert rtsp stream to video"
        cmd=$cmd" -c:a copy -map 0 -reconnect 1 -reconnect_at_eof 1 -reconnect_streamed 1 \
        -f segment -segment_time ${SEGMENT_TIME} -segment_format mp4 -strict -2 \
        -strftime 1 $BASEpath/capture-%03d-%Y-%m-%d_%H-%M-%S.mp4"
fi
  
while true
do 
    echo $cmd
    $cmd
    echo  $(date +%F" "%H:%M:%S)"......Restarting ffmpeg command in 60 seconds......"
    sleep 60
done