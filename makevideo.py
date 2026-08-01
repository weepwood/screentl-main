import argparse
import datetime

from screentl.video import make_video


def main():
    today = datetime.date.today().strftime('%Y-%m-%d')
    parser = argparse.ArgumentParser(description='Turn screenshots into an MP4 video.')
    parser.add_argument('--folder', default=today, help='screenshot folder (default: today)')
    parser.add_argument('--fps', type=int, default=25, help='video frames per second')
    parser.add_argument('--audio', default='audio', help='audio folder; omit or use an empty folder for silent video')
    parser.add_argument('--text', default=today, help='title text; use an empty string to disable')
    args = parser.parse_args()
    output = make_video(folder=args.folder, fps=args.fps, audio_loc=args.audio, text=args.text)
    print(f'Video written to {output}')


if __name__ == '__main__':
    main()
