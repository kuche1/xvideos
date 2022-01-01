#! /usr/bin/env python3

# TODO get rid of the sixel shit (MAKEPKG included)

# TODO
# include "more" option
# make the external player possible to take arguments
# make image viewer possible to change
# save video metadata
# make running multiple instances possible

import requests
import os
import shlex
import tempfile
import subprocess
import shutil

import bs4


HERE = os.path.dirname(os.path.realpath(__file__))

SETTINGS_DIR = os.path.expanduser('~/.config/minq_xvideos/')
CACHE_DIR = os.path.expanduser('~/.cache/minq_xvideos/')

VIDEO_CACHE_DIR = CACHE_DIR+'videos/{}/'
SETTING_BLACKLISTED_VIDEOS_FILE = SETTINGS_DIR+'video_blacklist.blacklist'
SETTING_VIDEO_PLAYER_FILE = SETTINGS_DIR+'video_player'

DONE_POSTFIX = '.done'
SIXEL_POSTFIX = '.sixel'

def alert(msg):
    print(msg)
    input("PRESS ENTER")

def get_temp_file(prefix=None):
    with tempfile.NamedTemporaryFile(delete=False, prefix=prefix) as f:
        return f.name

def download_raw(url, save_directory=None):
    if save_directory == None:
        name = get_temp_file()
    else:
        name = save_directory
    with open(name, 'wb') as f:
        page = requests.get(url)
        assert page.ok
        f.write(page.content)
    return name

def run_in_terminal(cmd:list, capture_output=False):
    cmd_fixed = shlex.join(cmd)
    res = subprocess.run(cmd_fixed, shell=True, check=True, capture_output=capture_output)
    return res

def display_image(path):
    run_in_terminal(['viu', path]) # not: viu supports sixel graphics
    #viu -h 12 -w 24 1.jpg -f

def play_video(player, path):
    if player == '':
        os.environ['CACA_DRIVER'] = 'ncurses'
        run_in_terminal(['mplayer', '-really-quiet', '-vo', 'caca', path])
        os.environ['CACA_DRIVER'] = ''
    else:
        run_in_terminal([player, path]) # TODO alert if command fails



class XVideo:
    
    def __init__(s, id, link, title, thumb, resolution, views, uploader, duration):
        s.id = id
        s.link = link
        s.title = title
        s.thumb_url = thumb
        s.resolution = resolution
        s.views = views
        s.uploader = uploader
        s.duration = duration

        assert VIDEO_CACHE_DIR.endswith('/')
        cache_dir = VIDEO_CACHE_DIR.format(id)

        s.thumb = cache_dir + 'thumb'
        s.thumb_cached = os.path.isfile(s.thumb + DONE_POSTFIX)

        s.video = cache_dir + 'video' 
        s.video_cached = os.path.isfile(s.video + DONE_POSTFIX)

    def download_video(s):
        s.video_cached = False
        
        dir_ = s.video + DONE_POSTFIX
        if os.path.isfile(dir_):
            os.remove(dir_)

        video_temp = '/tmp/' + s.id
        run_in_terminal(['yt-dlp', '--output', video_temp, s.link])

        dir_ = os.path.dirname(s.video)
        if not os.path.isdir(dir_):
            os.makedirs(dir_)

        shutil.move(video_temp, s.video)
        with open(s.video + DONE_POSTFIX, 'w') as f: pass

        s.video_cached = True

    def show_preview(s):
        print(s.title)
        print(f'{s.duration} | {s.resolution}')
        print(f'Views: {s.views} | Uploader: {s.uploader}')
        print(s.link)

        if not s.thumb_cached:
            os.makedirs(os.path.dirname(s.thumb))
            s.thumb = download_raw(s.thumb_url, save_directory=s.thumb)
            with open(s.thumb + DONE_POSTFIX, 'w') as f: pass
            s.thumb_cached = True

        print(f"Video cached: {s.video_cached}")

        display_image(s.thumb)

    def play(s, player):
        if not s.video_cached:
            s.download_video()

        play_video(player, s.video)



class XVideos:
    url = 'https://www.xvideos.com/'
    first_page_url = url
    nth_page_url = first_page_url + 'new/{}/'
    search_url = url + '?k={}&p={}' # first is term to search; second is page number (starts at 0)
    search_term = ''

    def __init__(s):
        s.reset_video_counter()

        if not os.path.isdir(SETTINGS_DIR):
            os.makedirs(SETTINGS_DIR)

        # video player
        if not os.path.isfile(SETTING_VIDEO_PLAYER_FILE):
            with open(SETTING_VIDEO_PLAYER_FILE, 'w') as f:
                pass
        with open(SETTING_VIDEO_PLAYER_FILE, 'r') as f:
            s.video_player = f.read()

        # cache
        cache_dir = os.path.dirname(os.path.dirname(VIDEO_CACHE_DIR))
        if not os.path.isdir(cache_dir):
            os.makedirs(cache_dir)

        # blacklist
        if not os.path.isfile(SETTING_BLACKLISTED_VIDEOS_FILE):
            with open(SETTING_BLACKLISTED_VIDEOS_FILE, 'w') as f:
                pass
        with open(SETTING_BLACKLISTED_VIDEOS_FILE) as f:
            videos = f.read().splitlines()
            while '' in videos:
                videos.remove('')
            s.blacklisted_videos = videos

    def reset_video_counter(s):
        s.videos = []
        s.video_ind = 0
        s.last_scrapped_page = 0

    def get_page_url(s, page_num):
        if s.search_term == '':
            return s.first_page_url if page_num == 1 else s.nth_page_url.format(page_num)
        else:
            return s.search_url.format(s.search_term, page_num-1)

    def extend_videos(s, videos):
        if len(videos) == 0:
            return
        
        videos = [video for video in videos if video.id not in s.blacklisted_videos and video.id not in s.videos]
        
        s.videos.extend(videos)

    def scrape_another_page(s):
        assert s.url.endswith('/')

        page_num = s.last_scrapped_page + 1
        page_url = s.get_page_url(page_num)

        page = requests.get(page_url)
        assert page.ok

        soup = bs4.BeautifulSoup(page.content, "lxml")

        videos = []
        metadatas1 = soup.find_all(class_='thumb-under')
        images = soup.find_all(class_='thumb')
        metadatas2 = soup.find_all(class_='metadata')

        assert len(metadatas1) == len(images) == len(metadatas2)
        
        for data, image, data2 in zip(metadatas1, images, metadatas2):

            duration = data.next.find(class_='duration').text
        
            data = data.find(class_='title')     
            data = data.next

            id = data['href'].split('/')[1]
            if id in s.blacklisted_videos:
                continue

            href_ = data['href']
            assert href_.startswith('/')
            link = s.url + href_[1:]
            title = data['title']

            # this doesn't change a thing
            #if '/THUMBNUM/' in link:
            #    assert link.count('/THUMBNUM/') == 1
            #    link = link.replace('/THUMBNUM/', '/')
            
            image = image.next.next['data-src']
            if 'THUMBNUM' in image:
                assert image.count('THUMBNUM') == 1
                image = image.replace('THUMBNUM', '20')

            resolution = data2.next.next.text
            views = data2.next.text.split(' -  ')[-1].split(' - ')[0].split(' ')[0]
            uploader = data2.next.find(class_='name').text
            
            videos.append(XVideo(id, link, title, image, resolution, views, uploader, duration))

        s.extend_videos(videos)
        s.last_scrapped_page = page_num

    def blacklist_a_video(s, video):
        s.blacklisted_videos.append(video.id)
        with open(SETTING_BLACKLISTED_VIDEOS_FILE, 'a') as f:
            f.write(video.id)
            f.write('\n')
        s.videos.remove(video)

    def set_video_player(s, player):
        s.video_player = player
        with open(SETTING_VIDEO_PLAYER_FILE, 'w') as f:
            f.write(player)

    def interactive(s):
        running = True
        while running:
            print()
            print()
            
            if s.video_ind < 0:
                s.video_ind = 0
                alert('This is the first video')
            elif s.video_ind >= len(s.videos):
                s.scrape_another_page()

            video = s.videos[s.video_ind]

            video.show_preview()

            try:
                cmd = input('> ')
            except KeyboardInterrupt:
                cmd = ''
                running = False

            CMDS = []
            CMD_DEFAULT = ['default action', '']
            CMDS.append(CMD_DEFAULT)
            CMD_QUIT = ['quit application', 'quit', 'q', 'exit']
            CMDS.append(CMD_QUIT)
            CMD_NEXT = ['next video', 'next', 'n']
            CMDS.append(CMD_NEXT)
            CMD_PREV = ['previous video', 'previous', 'prev', 'p']
            CMDS.append(CMD_PREV)
            CMD_DOWNLOAD = ['download video', 'download', 'd']
            CMDS.append(CMD_DOWNLOAD)
            CMD_PLAY = ['play video', 'play', 'watch']
            CMDS.append(CMD_PLAY)
            CMD_SEARCH = ['search for a video', 'search', 's']
            CMDS.append(CMD_SEARCH)
            CMD_BLACKLIST = ['blacklist a video', 'backlist', 'black', 'block']
            CMDS.append(CMD_BLACKLIST)
            CMD_CHANGE_PLAYER = ['change video player', 'player']
            CMDS.append(CMD_CHANGE_PLAYER)
            CMD_DEBUG = ['debug']
            CMDS.append(CMD_DEBUG)
            

            if cmd in CMD_DEFAULT:
                cmd = CMD_NEXT[0]

            if cmd in CMD_QUIT:
                running = False
            
            elif cmd in CMD_NEXT:
                s.video_ind += 1
            elif cmd in CMD_PREV:
                s.video_ind -= 1

            elif cmd in CMD_DOWNLOAD:
                video.download_video()
                continue
            elif cmd in CMD_PLAY:
                video.play(s.video_player)

            elif cmd in CMD_SEARCH:
                to_search = input("Term to search | Leave empty to go back to front page >> ")
                s.reset_video_counter()
                s.search_term = to_search

            elif cmd in CMD_BLACKLIST:
                s.blacklist_a_video(video)
                continue
            elif cmd in CMD_CHANGE_PLAYER:
                player = input("Set video player | Leave empty for default >> ")
                s.set_video_player(player)

            elif cmd in CMD_DEBUG:
                breakpoint()

            else:
                print()
                print("List of available commands:")
                for c in CMDS:
                    print(c)
                alert(f'Unknown command: {cmd}')
                continue


if __name__ == '__main__':
    xvideos = XVideos()
    xvideos.interactive()

