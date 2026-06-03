# LiveSync_AVFplayer
simultaneous multi file player using AVFoundation

## 1. Usage
- `config.ini`のシークタイムリストと、`AVF_Sync_v1.py`内部の`Settings`セクションを書き換える。
- その際モニターのIDとスピーカーのUIDが必要なので、先に`getDeviceIDs.py`を実行しIDをメモする

## 2. Notice
- `caffeinate -d`により画面の終了やサインアウトを防止することを推奨する

## Version
### Version 1.0
initial version
