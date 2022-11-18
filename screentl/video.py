import datetime
import random
import re

from moviepy.editor import *


TODAY = datetime.date.today().strftime('%Y-%m-%d')


def make_video(folder: str = TODAY,
               fps: int = 25,
               audio_loc: str = 'audio',
               text: str = TODAY
               ):
    """
    make the video
    :param folder: folder where to store the file. By default the folder name is the date.
    :param fps: fps
    :param audio_loc: audio file folder location
    :param text: what you want to display in the video
    :return: None
    """
    files = os.listdir(folder)
    # ensure the time sequence
    num_list = [int(re.findall(r"\d+", file)[0]) for file in files if file.startswith('screenshot')]
    num_list.sort()

    images_list = []
    for i in num_list:
        images_list.append(f'{folder}/screenshot_{i}.png')

    duration = len(num_list)/fps

    # randomly select an music from a set where the music duration is longer than video
    audio_candidates = []
    for audio_file in os.listdir(audio_loc):
        audio_clip = AudioFileClip(f'{audio_loc}/{audio_file}')
        if duration <= audio_clip.end:
            audio_candidates.append(f'{audio_loc}/{audio_file}')

    audio_file = random.choice(audio_candidates)
    video_clip = ImageSequenceClip(images_list, fps=fps)

    # To use the text video, you have to install "ImageMagick". One can refer to "Other optional but
    # useful dependencies" at https://zulko.github.io/moviepy/install.html
    try:
        txt = TextClip(f"{text}", color='whi', fontsize=60)
        txt_mov = txt.set_pos('center').set_duration(3)
        final = CompositeVideoClip([video_clip, txt_mov])
    except:
        final = CompositeVideoClip([video_clip])

    background_music = AudioFileClip(audio_file)
    final = final.set_audio(background_music)
    # to compress the video, one can give a string like '2000k' to bitrate.
    final.set_duration(duration).write_videofile(f'{folder}/video.mp4', bitrate=None)


