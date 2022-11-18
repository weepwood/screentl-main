from screentl.video import make_video
import datetime


today = datetime.date.today().strftime('%Y-%m-%d')

# argument 'folder' can be replaced by whatever you want. For example, you can name it
# by your project name. In this way you could organize your screenshots in the folders
# categorised by your work.
make_video(
    folder=today,
    fps=25,
    audio_loc='audio',
)
