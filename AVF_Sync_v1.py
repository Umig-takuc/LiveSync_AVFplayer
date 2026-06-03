import sys
import os
import traceback
import signal
import threading
import tty
import termios
import configparser
import unicodedata  # 🌟 これを追加

from Foundation import NSObject, NSURL, NSTimer
from AppKit import (NSApplication, NSWindow, NSMakeRect,
                    NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
                    NSWindowStyleMaskResizable, NSBackingStoreBuffered, NSApp,
                    NSScreen, NSWindowCollectionBehaviorFullScreenPrimary,
                    NSColor, NSViewWidthSizable, NSViewHeightSizable,
                    NSRunLoop, NSRunLoopCommonModes, NSWindowStyleMaskBorderless, NSWindowStyleMaskBorderless, NSMainMenuWindowLevel)
from AVFoundation import AVAsset, AVPlayerItem, AVPlayer, AVLayerVideoGravityResizeAspect
from AVKit import AVPlayerView
import CoreMedia
from PyObjCTools import AppHelper

# ---------------------------------------------------------
# 1. 設定項目（ここに必要な分だけ画面を追加してください）
# ---------------------------------------------------------
CONFIG_FILE = "config.ini"

# 初期化
PLAYER_CONFIGS = []
seek_points = {}

if os.path.exists(CONFIG_FILE):
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE, encoding='utf-8')

    # ---------------------------------------------------------
    # 1. プレイヤー設定の読み込み
    # ---------------------------------------------------------
    # "Player_" から始まるセクションを順番に探してリスト化
    for section in config.sections():
        if section.startswith("Player_"):
            file_path = config.get(section, "file", fallback="")
            screen_index = config.getint(section, "screen_index", fallback=0)
            audio_uid = config.get(section, "audio_uid", fallback="")
            
            if file_path:  # ファイルが設定されている場合のみ追加
                PLAYER_CONFIGS.append({
                    "file": file_path,
                    "screen_index": screen_index,
                    "audio_uid": audio_uid
                })

    # ---------------------------------------------------------
    # 2. シークポイント設定の読み込み
    # ---------------------------------------------------------
    if config.has_section('SeekPoints'):
        for key, value in config.items('SeekPoints'):
            try:
                parts = value.split('=', 1)
                if len(parts) == 2:
                    title = parts[0].strip(' "')
                    h, m, s, f = map(int, parts[1].strip().split(':'))
                    seek_points[key] = {'title': title, 'sec': h*3600 + m*60 + s + (f/60.0)}
            except: 
                pass

signal.signal(signal.SIGINT, signal.SIG_DFL)

class AppDelegate(NSObject):
    def applicationDidFinishLaunching_(self, notification):
        self.is_playing = False
        self.target_seek_sec = 0.0
        self.players = []
        self.items = []
        self.windows = []

        try:
            print(f"🚀 {len(PLAYER_CONFIGS)} 画面のセットアップを開始します...")
            
            for cfg in PLAYER_CONFIGS:
                path = os.path.abspath(cfg["file"])
                if not os.path.exists(path):
                    print(f"❌ ファイル欠落: {path}")
                    continue

                # アセットとプレイヤーの生成
                asset = AVAsset.assetWithURL_(NSURL.fileURLWithPath_(path))
                item = AVPlayerItem.playerItemWithAsset_(asset)
                player = AVPlayer.playerWithPlayerItem_(item)
                
                # 同期のための基本設定
                player.setAutomaticallyWaitsToMinimizeStalling_(False)
                if cfg["audio_uid"]:
                    player.setAudioOutputDeviceUniqueID_(cfg["audio_uid"])

                self.items.append(item)
                self.players.append(player)

                # ウィンドウの作成
                win = self.create_window(f"Display {cfg['screen_index']}", cfg['screen_index'], player)
                self.windows.append(win)

            self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                0.1, self, b'checkReady:', None, True
            )
            self.start_keyboard_listener()

        except Exception as e:
            traceback.print_exc()

    def create_window(self, title, screen_index, player):
        screens = NSScreen.screens()
        target_screen = screens[screen_index] if len(screens) > screen_index else screens[0]
        
        # 🌟 変更点: 画面のフレームサイズをそのまま使い、枠なし(Borderless)にする
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            target_screen.frame(),
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered, False
        )
        win.setTitle_(title)
        win.setBackgroundColor_(NSColor.blackColor())
        
        # 🌟 変更点: 別のアプリが来ても隠れないようにウインドウレベルを上げる（オプション）
        # 通常のアプリより少し手前に配置します
        win.setLevel_(NSMainMenuWindowLevel + 1) # ※必要ならこの行を有効化（NSAppKitのインポートが必要）

        view = AVPlayerView.alloc().initWithFrame_(win.contentView().bounds())
        view.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        view.setVideoGravity_(AVLayerVideoGravityResizeAspect)
        # 再生コントロールを非表示にする場合は以下を追加
        # view.setControlsStyle_(1) # AVPlayerViewControlsStyleNone
        view.setPlayer_(player)
            
        win.contentView().addSubview_(view)
        win.makeKeyAndOrderFront_(None)
        return win

    def checkReady_(self, timer):
        if all(item.status() == 1 for item in self.items):
            timer.invalidate()
            
            # 🌟 変更点: toggleFullScreen_ はもう呼ばない（最初から画面サイズになっているため）
            # print("\n📺 全画面フルスクリーン化中...")
            # for win in self.windows:
            #     win.toggleFullScreen_(None)

            print("✨ スタンバイ完了！ [Space] キーを押して再生を開始してください。\n")
            print("\r⏸️ 待機中... (再生: Space, シーク: S)       ", end="", flush=True)

    def togglePlayPause_(self, sender):
        if self.is_playing:
            for p in self.players: p.pause()
            self.is_playing = False
            print("\r⏸️ 一時停止中...                         ", end="", flush=True)
        else:
            # 1. 共通の起動時間を計算（0.5秒後の未来）
            host_clock = CoreMedia.CMClockGetHostTimeClock()
            start_host_time = CoreMedia.CMTimeAdd(CoreMedia.CMClockGetTime(host_clock), 
                                                CoreMedia.CMTimeMake(500000000, 1000000000))
            
            # 2. 🔥 1つ目のプレイヤー（マスター）の現在位置を取得
            # 誰が何と言おうと、全員これを基準に合わせます
            master_time = self.players[0].currentTime()
            
            # 3. 全プレイヤーに「0.5秒後に、master_timeから再生せよ」と命令
            for p in self.players:
                p.setRate_time_atHostTime_(1.0, master_time, start_host_time)
            
            self.is_playing = True
            print("\r▶️ 再生中 (同期: Master基準)               ", end="", flush=True)

    def performSeek_(self, sender):
        was_playing = self.is_playing
        for p in self.players: p.pause()
        self.is_playing = False

        cm_time = CoreMedia.CMTimeMakeWithSeconds(self.target_seek_sec, 60000)
        zero_tol = CoreMedia.CMTimeMake(0, 1)
        
        for p in self.players:
            p.seekToTime_toleranceBefore_toleranceAfter_(cm_time, zero_tol, zero_tol)

        if was_playing:
            NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                0.5, self, b'togglePlayPause:', None, False
            )

    def start_keyboard_listener(self):
        def listener_loop():
            print("\n" + "="*40)
            print(" 🎬 コントロールメニュー (AVFoundation)")
            print(" [Space] : 再生開始 / 一時停止")
            print(" [S]     : シークポイントから選択")
            print(" [Q]     : 終了")
            print("="*40 + "\n")
            
            fd = sys.stdin.fileno()
            
            while True:
                try:
                    old_settings = termios.tcgetattr(fd)
                    ch = ''
                    try:
                        tty.setraw(fd)
                        # マルチバイト文字の断片を読み込んでエラーになってもクラッシュさせない
                        ch = sys.stdin.read(1)
                    except Exception:
                        pass
                    finally:
                        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    
                    if not ch:
                        continue
                    
                    # 🌟 最重要：日本語入力（全角の「ｓ」や「　」）を強制的に半角（ASCII）に変換し、小文字にする
                    ch = unicodedata.normalize('NFKC', ch).lower()
                    
                    if ch == ' ':
                        self.performSelectorOnMainThread_withObject_waitUntilDone_(b'togglePlayPause:', None, False)
                        
                    elif ch == 's':
                        print("\n\n" + "-"*40)
                        print(" 📌 シークポイント一覧")
                        if not seek_points:
                            print("  ※ config.iniに [SeekPoints] が設定されていません。")
                        else:
                            for k in sorted(seek_points.keys()):
                                v = seek_points[k]
                                print(f"  [{k}] {v.get('title', 'Unknown')}")
                        print("-" * 40)
                        
                        target_key = input(" シーク先の番号を入力してEnter (キャンセルはそのままEnter): ").strip()
                        # 番号を全角で入力してしまった場合も半角に補正してあげる
                        target_key = unicodedata.normalize('NFKC', target_key)
                        
                        if target_key in seek_points:
                            self.target_seek_sec = seek_points[target_key]['sec']
                            print(f"\r⏩ '{seek_points[target_key]['title']}' にジャンプ中...\n")
                            self.performSelectorOnMainThread_withObject_waitUntilDone_(b'performSeek:', None, False)
                        else:
                            print("\r⚠️ キャンセルしました。\n")
                            if self.is_playing:
                                print("\r▶️ 再生中... (一時停止: Space, シーク: S)       ", end="", flush=True)
                            else:
                                print("\r⏸️ 一時停止中... (再開: Space, シーク: S)       ", end="", flush=True)

                    elif ch == 'q' or ch == '\x03':
                        print("\n\r⏹️ 終了処理中...                    ")
                        os.kill(os.getpid(), signal.SIGINT)
                        break
                        
                except Exception as e:
                    # 想定外のキー操作やエスケープシーケンスでエラーが出ても、スレッドをループに戻して生かす
                    continue

        threading.Thread(target=listener_loop, daemon=True).start()

if __name__ == "__main__":
    app = NSApplication.sharedApplication()
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.setActivationPolicy_(0)
    app.activateIgnoringOtherApps_(True)
    AppHelper.runEventLoop()