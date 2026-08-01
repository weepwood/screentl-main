import argparse
import datetime

from screentl.utils import screenshot


def main():
    today = datetime.date.today().strftime('%Y-%m-%d')
    parser = argparse.ArgumentParser(description='Capture periodic screenshots.')
    parser.add_argument('--folder', default=today, help='output folder (default: today)')
    parser.add_argument('--interval', type=int, default=30, help='seconds between captures')
    args = parser.parse_args()
    screenshot(folder=args.folder, interval=args.interval)


if __name__ == '__main__':
    main()
