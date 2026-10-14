# 🐣 简易安装指南（Windows）

[English](GUIDE.md) | **简体中文** | [日本語](GUIDE.ja.md)

本指南写给从没装过这类程序的人。你只需要 **下载、解压、双击**，其余全部自动完成。

## 需要准备

- 一台 Windows 10 或 Windows 11 电脑
- 能上网
- 第一次大约 10 分钟（之后几秒就能启动）

## 第 1 步 — 下载

1. 打开这个链接：<https://github.com/OneJan111/multi-platform-chat/archive/refs/heads/main.zip>
   会自动开始下载。（也可以打开 <https://github.com/OneJan111/multi-platform-chat>，点绿色的 **Code** 按钮，再点 **Download ZIP**。）
2. 打开 **下载** 文件夹（按 Windows 键，输入 `下载` 或 `Downloads`，回车）。
3. **右键** 文件 `multi-platform-chat-main.zip` → **全部解压缩…** → **解压**。
   会打开一个新文件夹 `multi-platform-chat-main`。
   > ⚠️ 不要跳过这一步。在 ZIP 文件里面直接运行是不行的。
4. 可选：把 `multi-platform-chat-main` 文件夹移到好找的地方，比如 **文档**。

## 第 2 步 — 启动

1. 在 `multi-platform-chat-main` 文件夹里，**双击 `Start Dashboard`**（图标是带齿轮的小窗口；如果显示扩展名，则叫 `Start_Dashboard.bat`）。
2. 如果出现蓝色窗口 **“Windows 已保护你的电脑”**，点 **更多信息** → **仍要运行**。
   这是因为文件来自网络。它只是一个文本脚本，可以右键 → **编辑** 查看内容。
3. 会打开一个 **黑色窗口**，这就是仪表板程序。
   - 第一次会自动安装 Python 和所需组件。**会滚动很多文字，这是正常的**，需要 3–10 分钟。
   - 如果 Windows 询问 *“你要允许此应用对你的设备进行更改吗？”*，点 **是**。
4. 浏览器会自动打开仪表板：<http://localhost:8501>。
5. 桌面上会多一个 **Live Chat Dashboard** 快捷方式，下次直接用它。

> 🖤 使用期间 **不要关闭黑色窗口**。可以最小化（右上角的 `_`），但不要关掉。

## 日常使用

| 我想… | 这样做 |
|---|---|
| 启动仪表板 | 双击桌面上的 **Live Chat Dashboard** |
| 关闭仪表板 | 关闭黑色窗口（右上角的 ✕） |
| 不小心关了浏览器标签页 | 再双击一次桌面快捷方式，或打开 <http://localhost:8501> |

## 第 3 步 — 读取弹幕

1. 点 **📡 直播监控** 标签页。
2. 在 **YouTube**、**Bilibili** 或 **猫耳FM** 下面的 **房间号或链接** 里粘贴你的频道链接或房间号。
3. 点 **▶ 开始监听**，弹幕会显示在 **💬 弹幕** 标签页。

读取弹幕不需要登录。

## 第 4 步 — 登录以便发送弹幕（可选）

1. 在你平时用的浏览器（Chrome、Edge 或 Firefox）里登录 YouTube / B站 / 猫耳FM。
2. 在仪表板中打开 **🍪 Cookies** 标签页。
3. 选择 **🧭 本机浏览器**，选好浏览器和网站，点 **读取 Cookie**，再点 **✅ 使用这些 Cookie**。
   - Chrome 或 Edge 读取失败？改用 **📋 粘贴 / 上传 Cookie**：用浏览器扩展 *Cookie-Editor* 导出 Cookie（**Export → JSON**），然后点 **📋 从剪贴板粘贴**，会自动识别网站，再点 **✅ 使用这些 Cookie**。
4. 要退出登录，在 **🔑 已保存的登录** 中点该网站的 **🗑️ 删除**（或 **🗑️ 删除所有登录**）。

向猫耳FM 发送弹幕或房间表情时，导入的账号必须有该直播间的发言资格；猫耳FM 网页端要求账号已绑定手机号。监听对应房间时，可在留言框旁的猫耳FM 选择器中浏览房间表情包（点击表情会立即发送），或点击预设颜文字将其添加到留言框，检查或编辑后再发送。发送失败的话，请重新导入最新的猫耳FM Cookie。

## 第 5 步 — 在 OBS 直播画面上显示弹幕

1. 在仪表板中打开 **🎬 OBS** 标签页，最上方是 **🖥️ OBS 独立弹幕层** 和一个链接。
2. 把鼠标移到链接上，点右侧的 **复制** 图标。
3. 在 OBS 的 **来源** 框中点 **＋** → **浏览器** → **确定**。
4. 把链接粘贴到 **URL**，**宽度** 填 `400`，**高度** 填 `600`，点 **确定**。
5. 在 OBS 预览中拖动、缩放弹幕框到合适的位置。

只要黑色窗口开着，即使关闭仪表板页面，弹幕层也会继续工作。

## 可选设置

大多数人不需要改。设置文件是 `multi-platform-chat-main` 文件夹中的 `.env`（第一次启动时自动创建）。
修改方法：右键 `.env` → **打开方式** → **记事本**，修改并保存，然后关闭黑色窗口再重新启动。

- **OBS 遥控**（开始/停止直播、切换场景）——在 OBS 中打开 **工具 → WebSocket 服务器设置**，勾选 **开启 WebSocket 服务器**，点 **显示连接信息** 并复制密码，填到 `.env` 中 `OBS_PASSWORD=` 后面。然后在 🎬 OBS 标签页打开 **连接 OBS**。
- **默认房间**——`YOUTUBE_CHANNEL=`、`BILIBILI_ROOM_ID=`、`MISSEVAN_ROOM_ID=`。
- **弹幕翻译**——程序优先使用 Index-Translate，失败时回退到 Google。内置直播术语表会统一“舰长”“醒目留言”“上舰”“弹幕”等词。若要直接使用 Google，在 `.env` 中设置 `INDEX_TRANSLATE_API_BASE=`。启用翻译时，弹幕文本会发送给翻译服务。

## 更新到新版本

1. 关闭黑色窗口。
2. 重新下载并解压 ZIP（第 1 步）。
3. 把新的 `multi-platform-chat-main` 文件夹里的所有内容 **复制到旧文件夹中**，选择 **替换目标中的文件**。
   这样会保留你的设置（`.env`）、登录（`.login_secret`）和屏蔽用户（`chat_filters.json`）。
4. 启动仪表板。如果需要新组件，会自动安装。

## 遇到问题？

| 看到的情况 | 解决方法 |
|---|---|
| “Windows 已保护你的电脑” | 点 **更多信息** → **仍要运行**。 |
| 黑色窗口一闪就关了 | 确认已经解压 ZIP（第 1 步第 3 点），不要在 ZIP 里面运行。 |
| “Python could not be installed automatically” | 会打开一个网页。点黄色的 **Download Python** 按钮并运行，第一个画面 **勾选 “Add python.exe to PATH”**，再点 **Install Now**。完成后再双击 `Start Dashboard`。 |
| “Installing the parts failed” | 检查网络，再双击 `Start Dashboard`，会从中断处继续。 |
| 浏览器没有自动打开 | 自己打开 <http://localhost:8501>。 |
| “The dashboard is already running” | 已经在运行了，窗口会帮你打开页面。要重启请先关闭黑色窗口。 |
| 页面显示 “Connection error” | 黑色窗口被关掉了，重新启动仪表板。 |
| OBS 弹幕层是空的 | 黑色窗口必须开着，链接中的房间必须正在直播且有弹幕。 |
| 其他问题 | 关闭黑色窗口，删除 `multi-platform-chat-main` 里的 `.venv` 文件夹，再重新启动。会重新安装全部组件（设置和登录会保留）。 |

进阶用户的详细说明请看 [README](README.zh-CN.md)。
