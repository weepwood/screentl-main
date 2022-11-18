from screentl.utils import screenshot
import datetime
import time


today = datetime.date.today().strftime('%Y-%m-%d')

# argument 'folder' can be replaced by whatever you want. For example, you can name it
# by your project name. In this way you could organize your screenshots in the folders
# categorised by your work.
# interval: how many seconds will you capture the screen.
screenshot(folder='D:\\Root\\Pictures\\Day\\'+today, interval=10)

