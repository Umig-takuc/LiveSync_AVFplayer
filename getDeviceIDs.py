import AppKit
import ctypes
import ctypes.util

# 1. Macのコアドライバ（CoreAudio と CoreFoundation）を直接ロード
coreaudio_path = ctypes.util.find_library('CoreAudio')
cf_path = ctypes.util.find_library('CoreFoundation')

if not coreaudio_path or not cf_path:
    print("Macのコアシステムライブラリが見つかりません。")
    exit(1)

CoreAudio = ctypes.CDLL(coreaudio_path)
CF = ctypes.CDLL(cf_path)

# 2. CoreAudioの内部定数の定義 (4文字コードを数値に変換したもの)
kAudioObjectSystemObject = 1
kAudioHardwarePropertyDevices = 0x64657623            # 'dev#'
kAudioObjectPropertyScopeGlobal = 0x676c6f62          # 'glob'
kAudioObjectPropertyElementMaster = 0
kAudioDevicePropertyDeviceUID = 0x75696420            # 'uid '
kAudioDevicePropertyDeviceNameCFString = 0x6c6e616d    # 'lnam'

# 3. C言語の構造体をPython用に定義
class AudioObjectPropertyAddress(ctypes.Structure):
    _fields_ = [
        ("mSelector", ctypes.c_uint32),
        ("mScope", ctypes.c_uint32),
        ("mElement", ctypes.c_uint32)
    ]

# 4. C関数の引数と戻り値の型を厳密に指定 (64bit環境でのクラッシュ防止)
CoreAudio.AudioObjectGetPropertyDataSize.argtypes = [
    ctypes.c_uint32, ctypes.POINTER(AudioObjectPropertyAddress),
    ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)
]
CoreAudio.AudioObjectGetPropertyDataSize.restype = ctypes.c_int32

CoreAudio.AudioObjectGetPropertyData.argtypes = [
    ctypes.c_uint32, ctypes.POINTER(AudioObjectPropertyAddress),
    ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p
]
CoreAudio.AudioObjectGetPropertyData.restype = ctypes.c_int32

CF.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_ssize_t, ctypes.c_uint32]
CF.CFStringGetCString.restype = ctypes.c_bool

# 5. Mac独自の文字列（CFString）をPythonの文字列に変換するヘルパー
def cfstring_to_string(cf_str):
    if not cf_str:
        return "Unknown"
    buf = ctypes.create_string_buffer(1024)
    # 0x08000100 = kCFStringEncodingUTF8
    success = CF.CFStringGetCString(cf_str, buf, 1024, 0x08000100)
    return buf.value.decode('utf-8') if success else "Unknown"

def main():
    # システム全体のオーディオデバイス一覧の「データサイズ」を取得
    address = AudioObjectPropertyAddress(
        kAudioHardwarePropertyDevices,
        kAudioObjectPropertyScopeGlobal,
        kAudioObjectPropertyElementMaster
    )
    
    data_size = ctypes.c_uint32(0)
    status = CoreAudio.AudioObjectGetPropertyDataSize(
        kAudioObjectSystemObject, ctypes.byref(address), 0, None, ctypes.byref(data_size)
    )
    
    if status != 0:
        print("オーディオデバイス数の取得に失敗しました。")
        return

    # デバイスIDの配列を確保して、全デバイスIDを取得
    num_devices = data_size.value // ctypes.sizeof(ctypes.c_uint32)
    devices = (ctypes.c_uint32 * num_devices)()
    
    status = CoreAudio.AudioObjectGetPropertyData(
        kAudioObjectSystemObject, ctypes.byref(address), 0, None, ctypes.byref(data_size), ctypes.byref(devices)
    )
    
    if status != 0:
        print("オーディオデバイス一覧の取得に失敗しました。")
        return

    print(f"{'📢 デバイス名 (CoreAudio HAL)':<35} {'🆔 確実なUID'}")
    print("-" * 90)

    # 各デバイスの「名前」と「UID」を1つずつ剥ぎ取る
    for dev_id in devices:
        # 名前の取得
        addr_name = AudioObjectPropertyAddress(kAudioDevicePropertyDeviceNameCFString, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMaster)
        cf_name = ctypes.c_void_p()
        size = ctypes.c_uint32(ctypes.sizeof(ctypes.c_void_p))
        CoreAudio.AudioObjectGetPropertyData(dev_id, ctypes.byref(addr_name), 0, None, ctypes.byref(size), ctypes.byref(cf_name))
        
        # UIDの取得
        addr_uid = AudioObjectPropertyAddress(kAudioDevicePropertyDeviceUID, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMaster)
        cf_uid = ctypes.c_void_p()
        size = ctypes.c_uint32(ctypes.sizeof(ctypes.c_void_p))
        CoreAudio.AudioObjectGetPropertyData(dev_id, ctypes.byref(addr_uid), 0, None, ctypes.byref(size), ctypes.byref(cf_uid))
        
        # 変換と表示
        name = cfstring_to_string(cf_name)
        uid = cfstring_to_string(cf_uid)
        
        print(f"{name:<35} {uid}")
        
        # メモリ解放
        if cf_name: CF.CFRelease(cf_name)
        if cf_uid: CF.CFRelease(cf_uid)

def get_screen_indices():
    print("=== 🖥️ スクリーン (Index番号) ===")
    app = AppKit.NSApplication.sharedApplication()
    screens = AppKit.NSScreen.screens()
    
    if not screens:
        print("スクリーンが検出されませんでした。")
        return

    for i, screen in enumerate(screens):
        name = screen.localizedName() if hasattr(screen, 'localizedName') else "Unknown Display"
        frame = screen.frame()
        width = int(frame.size.width)
        height = int(frame.size.height)
        
        print(f"・Index [{i}]")
        print(f"  名前   : {name}")
        print(f"  解像度 : {width} x {height}\n")

if __name__ == "__main__":
    main()
    get_screen_indices()