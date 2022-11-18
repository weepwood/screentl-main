# Screenshot Time-lapse



#### 介绍
定时截屏，并生成视频，回顾一天的工作。

下载链接：

- https://gitee.com/alvinfeng/screentl 


#### 安装教程

1. 安装依赖库pyautogui, moviepy:

   > pip install pyautogui moviepy

2. 下载本目录下所有文件

#### 使用说明

1. 需要开启定时截屏时，请运行screenshot.py文件

   - folder: 设置存储截屏图片的目录名，默认按照今天日期命名

   - interval: 截屏的时间间隔，以秒为单位，默认为25s

2.  通过Ctrl+c或者关闭窗口来停止截屏程序；

3.  生成视频前可以将不想呈现的图片直接删除；

4. 需要生成视频时，请运行makevideo.py文件

   - folder: 存储截屏图片的文件夹名字，默认是今天的日期

   - fps: 每秒的帧数，默认25帧

   - audio_folder: 音频文件夹的名字

     > 程序会从大于视频时长的所有音乐文件中随机选取一首作为视频的背景音乐





