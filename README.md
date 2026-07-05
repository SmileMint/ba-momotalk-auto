# BA MomoTalk Auto

## 项目简介

BA MomoTalk Auto 是一个面向 MuMu Player 12 的《Blue Archive / 碧蓝档案》MomoTalk 自动化脚本。

它通过 MuMu 自带 ADB 获取游戏截图并发送点击指令，自动处理 MomoTalk 未读消息、回复角色对话、进入羁绊剧情、跳过剧情并领取羁绊剧情奖励。脚本采用偏保守的状态判断流程：每一步都会基于当前截图识别界面状态，遇到网络错误、异常弹窗、无法识别的画面或可能涉及购买/消耗资源的界面时会停止，方便用户重启游戏后继续运行。

这个项目只用于清理 MomoTalk 与羁绊剧情奖励，不包含抽卡、购买商店物品、修改账号设置、领取邮箱或其他可能消耗资源的操作。

## Project Overview

BA MomoTalk Auto is an automation script for handling MomoTalk content in *Blue Archive* on MuMu Player 12.

It uses MuMu's built-in ADB interface to capture screenshots and send tap commands. The script can process unread MomoTalk messages, choose reply options, enter relationship stories, skip story scenes, and claim relationship story rewards. It follows a conservative state-based workflow: every action is decided from the current screenshot, and the script stops when it detects network errors, unexpected dialogs, unrecognized screens, or anything that may involve purchases or resource spending.

This project is only intended for clearing MomoTalk and relationship story rewards. It does not perform recruitment, shop purchases, account setting changes, mailbox claiming, or any action designed to spend premium currency or paid resources.

## 功能

- 连接 MuMu Player 12 的 ADB 实例。
- 自动进入主界面左上角 MomoTalk。
- 打开未读讯息列表并选择带红色未读数字的角色。
- 自动点击任意回复选项，直到触发羁绊剧情入口。
- 进入羁绊剧情后打开菜单并跳过剧情。
- 领取奖励界面的 `TOUCH TO CONTINUE`。
- 完成一个角色后返回主界面重新进入 MomoTalk 刷新状态。
- 支持滚动未读列表继续寻找后续角色。
- 保存最后截图与调试截图，便于排查卡住的位置。

## 使用前准备

1. 安装并启动 MuMu Player 12。
2. 在模拟器中打开《Blue Archive / 碧蓝档案》，进入可点击 MomoTalk 的主界面。
3. 确认 MuMu 的 ADB 路径存在，默认路径为：

   ```text
   D:\MuMuPlayer-12.0\shell\adb.exe
   ```

4. 安装 Python 依赖：

   ```bash
   pip install -r requirements.txt
   ```

## 运行

```bash
python ba_momotalk_auto.py
```

如果你的 MuMu ADB 路径或端口不同，可以显式传入：

```bash
python ba_momotalk_auto.py --adb "D:\MuMuPlayer-12.0\shell\adb.exe" --serial 127.0.0.1:16384
```

常用参数：

```bash
python ba_momotalk_auto.py --max-rewards 20 --max-steps 300
```

- `--adb`：ADB 可执行文件路径。
- `--serial`：ADB 设备序列号，MuMu Player 12 常见为 `127.0.0.1:16384`。
- `--debug-dir`：调试截图输出目录，默认 `ba_momotalk_debug`。
- `--max-rewards`：单次最多领取奖励次数。
- `--max-steps`：单次最多执行状态机步数。
- `--dry-run`：只截图和判断，不实际点击。

## 安全边界

脚本设计目标是尽量保守地处理 MomoTalk 和羁绊剧情奖励。它不会主动执行以下操作：

- 抽卡或招募。
- 购买商店物品。
- 消耗青辉石或其他付费资源。
- 修改账号设置。
- 领取邮箱或任务奖励。

如果脚本遇到网络错误、重连提示、异常弹窗、点击无效、无法识别当前画面等情况，会停止并输出日志。通常重启游戏后再次运行即可。

## 免责声明

本项目是非官方工具，与 Nexon、Yostar、NAT Games 或《Blue Archive / 碧蓝档案》官方无关。

使用自动化脚本可能违反游戏服务条款或带来账号风险。请自行判断并承担使用后果。建议只在你完全理解脚本行为、接受风险，并确认不会影响他人或破坏游戏环境的前提下使用。

## License

MIT License
