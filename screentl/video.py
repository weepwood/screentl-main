import datetime
import random
from pathlib import Path

from moviepy.editor import AudioFileClip, CompositeVideoClip, ImageSequenceClip, TextClip

from .storage import list_screenshots


TODAY = datetime.date.today().strftime('%Y-%m-%d')


def make_video(folder: str = TODAY,
               fps: int = 25,
               audio_loc: str = 'audio',
               text: str = TODAY) -> Path:
    """
    make the video
    :param folder: folder where to store the file. By default the folder name is the date.
    :param fps: fps
    :param audio_loc: audio file folder location
    :param text: what you want to display in the video
    :return: None
    """
    if fps <= 0:
        raise ValueError('fps must be greater than zero')

    folder_path = Path(folder)
    if not folder_path.is_dir():
        raise FileNotFoundError(f'screenshot folder does not exist: {folder_path}')

    screenshots = list_screenshots(folder_path)
    if not screenshots:
        raise FileNotFoundError(f'no screenshot_*.png files found in: {folder_path}')

    images_list = [str(image) for image in screenshots]

    duration = len(images_list) / fps

    # randomly select an music from a set where the music duration is longer than video
    video_clip = ImageSequenceClip(images_list, fps=fps)
    output = folder_path / 'video.mp4'
    audio_clip = None
    final = video_clip

    # To use the text video, you have to install "ImageMagick". One can refer to "Other optional but
    # useful dependencies" at https://zulko.github.io/moviepy/install.html
    if text:
        try:
            txt = TextClip(str(text), color='white', fontsize=60)
            txt_mov = txt.set_pos('center').set_duration(min(3, duration))
            final = CompositeVideoClip([video_clip, txt_mov])
        except Exception as exc:
            print(f'Warning: title overlay disabled: {exc}')

    audio_path = Path(audio_loc)
    if audio_path.is_dir():
        candidates = []
        for path in audio_path.iterdir():
            if path.suffix.lower() not in {'.mp3', '.m4a', '.wav', '.aac', '.ogg'}:
                continue
            try:
                clip = AudioFileClip(str(path))
                candidates.append((path, clip.duration))
                clip.close()
            except Exception as exc:
                print(f'Warning: unable to inspect audio {path}: {exc}')

        suitable = [path for path, length in candidates if length >= duration]
        if suitable:
            selected_audio = random.choice(suitable)
            audio_clip = AudioFileClip(str(selected_audio)).subclip(0, duration)
            final = final.set_audio(audio_clip)
        elif candidates:
            print('Warning: no audio track is long enough; video will be silent.')
        else:
            print(f'Warning: no supported audio files found in {audio_path}; video will be silent.')
    else:
        print(f'Warning: audio folder not found: {audio_path}; video will be silent.')

    try:
        final.set_duration(duration).write_videofile(str(output), bitrate=None)
    finally:
        if audio_clip is not None:
            audio_clip.close()
        final.close()
        if final is not video_clip:
            video_clip.close()
    return output
