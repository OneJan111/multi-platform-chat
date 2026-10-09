"""UI localisation for the dashboard (English / Chinese / Japanese).

Strings are keyed by their English text, so untranslated strings fall back to English.
Use `{name}` placeholders for values and pass them as keyword arguments to `translate`.
"""
from __future__ import annotations

UI_LANGUAGES: dict[str, str] = {
    "en": "English",
    "zh": "中文",
    "ja": "日本語",
}

# English -> (Chinese, Japanese)
_STRINGS: dict[str, tuple[str, str]] = {
    # ── Sidebar ──────────────────────────────────────────────────────────────
    "🎙️ Streaming Dashboard": ("🎙️ 直播仪表板", "🎙️ 配信ダッシュボード"),
    "YouTube chat listener active ✓": ("YouTube 聊天监听中 ✓", "YouTube チャット受信中 ✓"),
    "Room ID": ("房间号", "ルーム ID"),
    "Room ID or URL": ("房间号或链接", "ルームIDまたはURL"),
    "Could not find a room ID in that text.": ("无法从输入中找到房间号。", "入力からルームIDが見つかりません。"),
    "MissEvan": ("猫耳FM", "MissEvan"),
    "Followers: {n}": ("关注：{n}", "フォロワー：{n}"),
    "MissEvan messages": ("猫耳FM 消息", "MissEvan メッセージ"),
    "bilibili-api-python not installed or connection failed.": (
        "未安装 bilibili-api-python 或连接失败。",
        "bilibili-api-python が未インストールか、接続に失敗しました。",
    ),
    "OBS connected ✓": ("OBS 已连接 ✓", "OBS 接続済み ✓"),
    "Connect to OBS": ("连接 OBS", "OBS に接続"),
    "Off: the dashboard never contacts OBS. On: stream, recording, scene and Text source controls appear here once OBS is connected.": (
        "关闭：仪表板不会连接 OBS。开启：连接成功后，这里会显示直播、录制、场景和文本源控制项。",
        "オフ：ダッシュボードは OBS に接続しません。オン：接続されると、ここに配信・録画・シーン・テキストソースの操作が表示されます。",
    ),
    "OBS functions are off.": ("OBS 功能已关闭。", "OBS 機能はオフです。"),
    "📝 OBS Text source": ("📝 OBS 文本源", "📝 OBS テキストソース"),
    "Send chat to OBS Text source": ("将聊天发送到 OBS 文本源", "チャットを OBS テキストソースに送信"),
    "OBS Text source": ("OBS 文本源", "OBS テキストソース"),
    "Add a Text source in OBS to display chat.": (
        "请在 OBS 中添加文本源以显示聊天。",
        "チャットを表示するには OBS にテキストソースを追加してください。",
    ),
    "Couldn't list OBS Text sources: {err}": (
        "无法列出 OBS 文本源：{err}",
        "OBS テキストソースを取得できません：{err}",
    ),
    "Couldn't update OBS chat text: {err}": (
        "无法更新 OBS 聊天文本：{err}",
        "OBS のチャットテキストを更新できません：{err}",
    ),
    "🌐 Translation": ("🌐 翻译", "🌐 翻訳"),
    "Translate chat": ("翻译聊天", "チャットを翻訳"),
    "Shows a translation under each chat message.": (
        "在每条聊天消息下方显示翻译。",
        "各チャットメッセージの下に翻訳を表示します。",
    ),
    "Translate to": ("翻译为", "翻訳先"),
    "Super Chat reading aid": ("醒目留言注音", "スーパーチャットの読み仮名"),
    "Shows pinyin / hiragana above Chinese characters in Super Chats so you can read them aloud.": (
        "在醒目留言的汉字上方显示拼音 / 平假名，方便朗读。",
        "スーパーチャットの漢字の上にピンイン／ひらがなを表示し、読み上げやすくします。",
    ),
    "🔊 Text-to-Speech": ("🔊 语音朗读", "🔊 読み上げ"),
    "Enable TTS": ("启用语音朗读", "読み上げを有効化"),
    "Language": ("语言", "言語"),
    "Auto-detect reads every message in its own language. Picking a language only reads chat written in that language.": (
        "自动检测会用每条消息自身的语言朗读全部消息。选择某种语言后，只朗读用该语言写的弹幕。",
        "自動検出ではすべてのメッセージをその言語で読み上げます。言語を選ぶと、その言語で書かれたチャットだけを読み上げます。",
    ),
    "Ignore emoji": ("忽略表情", "絵文字を無視"),
    "Skip emoji-only messages and stickers, and don't read emoji inside messages.": (
        "跳过纯表情消息和表情包，并且不朗读消息中的表情。",
        "絵文字のみのメッセージやスタンプをスキップし、メッセージ内の絵文字も読み上げません。",
    ),
    "Read translated chat": ("朗读翻译后的聊天", "翻訳したチャットを読み上げ"),
    "Always announce gifts & Super Chats": ("总是播报礼物和醒目留言", "ギフトとスーパーチャットを常に読み上げ"),
    "Reads gifts, Super Chats and memberships in any language, ahead of normal chat "
    "(normal chat waits until they're done).": (
        "无论语言都会播报礼物、醒目留言和会员，并优先于普通聊天（普通聊天会等它们读完）。",
        "言語に関係なくギフト・スーパーチャット・メンバーシップを通常のチャットより優先して読み上げます（通常のチャットはその後に読み上げ）。",
    ),
    "When the TTS language matches \"Translate to\" (Translation section), every message is "
    "read translated into that language. Otherwise messages are read in their original language.": (
        "当 TTS 语言与「翻译为」语言（翻译设置）相同时，所有消息都会翻译成该语言后朗读；否则按原文语言朗读。",
        "TTS の言語が「翻訳先」（翻訳セクション）と同じ場合、すべてのメッセージをその言語に翻訳して読み上げます。異なる場合は元の言語で読み上げます。",
    ),
    "⚠️ Not active: set the TTS language to the same language as \"Translate to\" ({target}).": (
        "⚠️ 未生效：请把 TTS 语言设为与「翻译为」相同的语言（{target}）。",
        "⚠️ 無効：TTS の言語を「翻訳先」と同じ言語（{target}）にしてください。",
    ),
    "Don't read usernames for regular chat": ("普通聊天不朗读用户名", "通常のチャットではユーザー名を読み上げない"),
    "Reads only the message text. Gifts and Super Chats still say who sent them.": (
        "只朗读消息内容。礼物和醒目留言仍会说出发送者。",
        "メッセージ本文のみを読み上げます。ギフトとスーパーチャットは送り主の名前も読み上げます。",
    ),
    "▶ Test voice": ("▶ 试听", "▶ 音声テスト"),
    "Smaller text ({p}%)": ("缩小文字（{p}%）", "文字を小さく（{p}%）"),
    "Bigger text ({p}%)": ("放大文字（{p}%）", "文字を大きく（{p}%）"),
    "⏭ Skip": ("⏭ 跳过", "⏭ スキップ"),
    "⏹ Stop TTS": ("⏹ 停止朗读", "⏹ 読み上げ停止"),
    "Stop reading the current message and go on to the next one.": (
        "停止朗读当前这条，继续读下一条。",
        "今読んでいるメッセージを止めて、次へ進みます。",
    ),
    "Stop reading now and drop all queued messages. New chat is still read.": (
        "立即停止朗读并清空等待中的消息。之后的新弹幕仍会朗读。",
        "すぐに読み上げを止め、待機中のメッセージを全て破棄します。新しいチャットは引き続き読み上げます。",
    ),
    "⏹ TTS stopped · {n} queued message(s) dropped": (
        "⏹ 已停止朗读 · 丢弃了 {n} 条等待中的消息",
        "⏹ 読み上げを停止 · 待機中の {n} 件を破棄",
    ),
    "⏭ Skipped the current message": ("⏭ 已跳过当前消息", "⏭ 現在のメッセージをスキップしました"),
    "Speed (WPM)": ("语速（WPM）", "速度（WPM）"),
    "Volume": ("音量", "音量"),
    "Show join events": ("显示进场消息", "入室イベントを表示"),
    "Max messages displayed": ("最多显示消息数", "最大表示メッセージ数"),
    "🗑️ Clear chat history": ("🗑️ 清空聊天记录", "🗑️ チャット履歴を消去"),
    # Option labels from src modules
    "Auto-detect": ("自动检测", "自動検出"),
    "Chinese (中文)": ("中文", "中国語（中文）"),
    "Japanese (日本語)": ("日语（日本語）", "日本語"),
    "Chinese (简体中文)": ("简体中文", "中国語（简体中文）"),
    "Chinese (繁體中文)": ("繁體中文", "中国語（繁體中文）"),
    "Korean (한국어)": ("韩语（한국어）", "韓国語（한국어）"),
    "English": ("英语（English）", "英語（English）"),
    "Auto (pinyin for Chinese, hiragana for Japanese)": (
        "自动（中文用拼音，日语用平假名）",
        "自動（中国語はピンイン、日本語はひらがな）",
    ),
    "Pinyin": ("拼音", "ピンイン"),
    "Hiragana": ("平假名", "ひらがな"),
    "Pinyin + Hiragana": ("拼音 + 平假名", "ピンイン + ひらがな"),
    "Off": ("关闭", "オフ"),
    # ── Chat rendering ───────────────────────────────────────────────────────
    "Block this user (hides their messages; saved permanently)": (
        "屏蔽该用户（隐藏其消息，永久保存）", "このユーザーをブロック（メッセージを非表示にし、永続的に保存）"),
    "Read this message aloud": ("朗读这条消息", "このメッセージを読み上げる"),
    "translating…": ("翻译中…", "翻訳中…"),
    # ── Tabs ─────────────────────────────────────────────────────────────────
    "💬 Chat": ("💬 聊天", "💬 チャット"),
    "📡 Stream Monitoring": ("📡 直播监控", "📡 配信モニタリング"),
    "🎬 OBS": ("🎬 OBS", "🎬 OBS"),
    "📊 Analytics": ("📊 数据分析", "📊 分析"),
    "🛡️ Filters": ("🛡️ 过滤", "🛡️ フィルター"),
    "🍪 Cookies": ("🍪 Cookies", "🍪 Cookie"),
    # ── Chat tab ─────────────────────────────────────────────────────────────
    "Blocked {author} — see the 🛡️ Filters tab to unblock": (
        "已屏蔽 {author}——可在 🛡️ 过滤 标签页取消屏蔽", "{author} をブロックしました（🛡️ フィルター タブで解除できます）"),
    "Saved to chat_filters.json and kept after restarting the app.": (
        "保存在 chat_filters.json，重启应用后仍然有效。", "chat_filters.json に保存され、アプリを再起動しても保持されます。"),
    "Any platform": ("任意平台", "全プラットフォーム"),
    "by name": ("按名称", "名前で"),
    "Unblock": ("取消屏蔽", "ブロック解除"),
    "Waits for the channel to go live, then reads its chat automatically.": (
        "等待频道开播，然后自动读取聊天。", "チャンネルの配信開始を待ち、自動でチャットを読み込みます。"),
    "👀 Watching {name} — not live yet": ("👀 正在监视 {name}——尚未开播", "👀 {name} を監視中 — まだ配信していません"),
    "👀 Watching {name} — stream scheduled: {title}": (
        "👀 正在监视 {name}——已预定直播：{title}", "👀 {name} を監視中 — 配信予定: {title}"),
    "Checks every {s}s · last checked {time}": ("每 {s} 秒检查一次 · 上次检查 {time}", "{s} 秒ごとに確認 · 最終確認 {time}"),
    "Live now: {title}": ("正在直播：{title}", "配信中: {title}"),
    "{channel} is live — reading chat": ("{channel} 开播了——正在读取聊天", "{channel} が配信開始 — チャットを読み込み中"),
    "The YouTube stream ended — watching the channel for the next one.": (
        "YouTube 直播已结束——继续监视频道等待下一场。", "YouTube の配信が終了しました — 次の配信に備えてチャンネルを監視します。"),
    "Watching the channel — it isn't live yet.": ("正在监视频道——尚未开播。", "チャンネルを監視中 — まだ配信していません。"),
    "Channel not found.": ("找不到该频道。", "チャンネルが見つかりません。"),
    "Send to": ("发送到", "送信先"),
    "Both": ("两者", "両方"),
    "Start the YouTube listener first.": ("请先启动 YouTube 监听。", "先に YouTube 受信を開始してください。"),
    "Enter a Bilibili room ID first.": ("请先输入 B站房间号。", "先に Bilibili のルームIDを入力してください。"),
    "Tick at least one site to send to.": ("请至少勾选一个发送平台。", "送信先を1つ以上選択してください。"),
    "Sent to {site} ✓": ("已发送到 {site} ✓", "{site} に送信しました ✓"),
    "Message": ("消息", "メッセージ"),
    "Type a message…": ("输入消息…", "メッセージを入力…"),
    "Send": ("发送", "送信"),
    "Chat": ("聊天", "チャット"),
    "Gifts & Super Chats": ("礼物和醒目留言", "ギフトとスーパーチャット"),
    "{n} to thank": ("{n} 条待感谢", "未お礼 {n} 件"),
    "{n} total": ("共 {n} 条", "合計 {n} 件"),
    "🙏 Mark all thanked": ("🙏 全部标为已感谢", "🙏 すべてお礼済みにする"),
    "No gifts or Super Chats yet.": ("还没有礼物或醒目留言。", "まだギフトやスーパーチャットはありません。"),
    "Joins": ("进场", "入室"),
    "No one has joined yet.": ("还没有人进场。", "まだ誰も入室していません。"),
    "Show viewers entering the room in a separate feed under Gifts & Super Chats.": (
        "在“礼物与醒目留言”下方的单独列表中显示进场的观众。",
        "入室した視聴者を「ギフトとスーパーチャット」の下の別欄に表示します。"),
    "Thanked": ("已感谢", "お礼済み"),
    "Mark as thanked": ("标为已感谢", "お礼済みにする"),
    "Undo: mark as not thanked yet": ("撤销：标为未感谢", "取り消し：未お礼に戻す"),
    "Auto-refreshes every {s}s · {n} messages shown": (
        "每 {s} 秒自动刷新 · 显示 {n} 条消息",
        "{s} 秒ごとに自動更新 · {n} 件表示",
    ),
    # ── Stream status tab ────────────────────────────────────────────────────
    "Enter a stream URL above to see its status.": ("在上方输入直播 URL 以查看状态。", "上に配信 URL を入力するとステータスが表示されます。"),
    "Status needs a stream URL or video ID (a raw chat ID has no video info).": (
        "需要直播 URL 或视频 ID 才能显示状态（聊天 ID 不包含视频信息）。",
        "状況の表示には配信 URL または動画 ID が必要です（チャット ID には動画情報がありません）。",
    ),
    "That video is not a live stream.": ("该视频不是直播。", "この動画はライブ配信ではありません。"),
    "🟢 Live": ("🟢 直播中", "🟢 配信中"),
    "🕒 Upcoming": ("🕒 即将开始", "🕒 配信予定"),
    "⚫ Ended": ("⚫ 已结束", "⚫ 終了"),
    "⚫ Offline": ("⚫ 未开播", "⚫ オフライン"),
    "📼 Playback": ("📼 轮播中", "📼 再放送中"),
    "Unknown": ("未知", "不明"),
    "Channel: {channel}": ("频道：{channel}", "チャンネル：{channel}"),
    "Viewers": ("观众", "視聴者"),
    "Live since: {t}": ("开播时间：{t}", "配信開始：{t}"),
    "Scheduled: {t}": ("预定时间：{t}", "予定：{t}"),
    "Enter a room ID above to see its status.": ("在上方输入房间号以查看状态。", "上にルーム ID を入力するとステータスが表示されます。"),
    "Could not fetch room info.": ("无法获取房间信息。", "ルーム情報を取得できません。"),
    "Streamer: {name}": ("主播：{name}", "配信者：{name}"),
    "Category: {area} › {sub}": ("分区：{area} › {sub}", "カテゴリ：{area} › {sub}"),
    # ── OBS tab ──────────────────────────────────────────────────────────────
    "⚠️ OBS is not connected: obsws-python is not installed. Run `pip install obsws-python`.": (
        "⚠️ OBS 未连接：未安装 obsws-python。请运行 `pip install obsws-python`。",
        "⚠️ OBS に接続されていません：obsws-python がインストールされていません。`pip install obsws-python` を実行してください。",
    ),
    "⚠️ OBS is not connected: OBS_PASSWORD is not set in .env.": (
        "⚠️ OBS 未连接：.env 中未设置 OBS_PASSWORD。",
        "⚠️ OBS に接続されていません：.env に OBS_PASSWORD が設定されていません。",
    ),
    "⚠️ OBS at {addr} refused the login — check OBS_PASSWORD. ({detail})": (
        "⚠️ {addr} 上的 OBS 拒绝登录——请检查 OBS_PASSWORD。（{detail}）",
        "⚠️ {addr} の OBS がログインを拒否しました — OBS_PASSWORD を確認してください。（{detail}）",
    ),
    "⚠️ OBS is not connected: nothing answered at {addr}.": (
        "⚠️ OBS 未连接：{addr} 没有响应。",
        "⚠️ OBS に接続されていません：{addr} から応答がありません。",
    ),
    "Is OBS running with its WebSocket server enabled? OBS_HOST is resolved on the computer "
    "running this dashboard — if that's a server, `localhost` means the server itself. Set "
    "OBS_HOST to the address of the PC running OBS, reachable from the server (same network, "
    "VPN such as Tailscale, or a port forward), and allow port {port} in that PC's firewall.": (
        "OBS 是否正在运行并已启用 WebSocket 服务器？OBS_HOST 是在运行本仪表板的电脑上解析的——如果它运行在服务器上，"
        "`localhost` 指的是服务器本身。请把 OBS_HOST 设为运行 OBS 的电脑地址，并确保服务器能访问它（同一网络、"
        "Tailscale 等 VPN 或端口转发），同时在该电脑的防火墙中放行端口 {port}。",
        "OBS は起動していて WebSocket サーバーが有効になっていますか？OBS_HOST はこのダッシュボードを動かしているコンピューターで"
        "解決されます — サーバーで動かしている場合、`localhost` はサーバー自身を指します。OBS_HOST を OBS を動かしている PC の"
        "アドレスにし、サーバーから届くようにしてください（同じネットワーク、Tailscale などの VPN、またはポート転送）。"
        "その PC のファイアウォールでポート {port} を許可してください。",
    ),
    "Setup instructions": ("设置说明", "設定手順"),
    "obs_setup_md": (
        """
1. 打开 OBS → **工具 → WebSocket 服务器设置**
2. 启用 WebSocket 服务器
3. 设置密码并记下端口（默认 4455）
4. 添加到 `.env`：
   ```
   OBS_HOST=localhost
   OBS_PORT=4455
   OBS_PASSWORD=your_password
   ```
""",
        """
1. OBS を開き **ツール → WebSocket サーバー設定**
2. WebSocket サーバーを有効にする
3. パスワードを設定し、ポートを控える（既定 4455）
4. `.env` に追加：
   ```
   OBS_HOST=localhost
   OBS_PORT=4455
   OBS_PASSWORD=your_password
   ```
""",
    ),
    "Dropped Frames": ("丢帧", "ドロップフレーム"),
    "🔴 Stream": ("🔴 推流", "🔴 配信"),
    "Streaming is LIVE": ("正在直播", "配信中です"),
    "⏹ Stop Stream": ("⏹ 停止推流", "⏹ 配信を停止"),
    "Not streaming": ("未在推流", "配信していません"),
    "▶️ Start Stream": ("▶️ 开始推流", "▶️ 配信を開始"),
    "⏺ Recording": ("⏺ 录制", "⏺ 録画"),
    "Recording in progress": ("正在录制", "録画中"),
    "⏹ Stop Recording": ("⏹ 停止录制", "⏹ 録画を停止"),
    "Not recording": ("未在录制", "録画していません"),
    "▶️ Start Recording": ("▶️ 开始录制", "▶️ 録画を開始"),
    "🎭 Scenes & Sources": ("🎭 场景与来源", "🎭 シーンとソース"),
    "Active scene": ("当前场景", "アクティブシーン"),
    "Sources in selected scene:": ("所选场景中的来源：", "選択中シーンのソース："),
    # ── Analytics tab ────────────────────────────────────────────────────────
    "📊 Stream Analytics": ("📊 直播数据分析", "📊 配信分析"),
    "Viewer Count Over Time": ("观众数变化", "視聴者数の推移"),
    "Time": ("时间", "時刻"),
    "Viewer history will appear here once streaming starts.": (
        "开播后将在此显示观众数历史。",
        "配信が始まると視聴者数の履歴がここに表示されます。",
    ),
    "Total messages": ("消息总数", "メッセージ総数"),
    "YouTube messages": ("YouTube 消息", "YouTube メッセージ"),
    "Bilibili danmaku": ("B站弹幕", "Bilibili 弾幕"),
    "Super Chats / SC": ("醒目留言 / SC", "スーパーチャット / SC"),
    "Message Rate (per minute)": ("消息速率（每分钟）", "メッセージ数（毎分）"),
    "Messages per Minute": ("每分钟消息数", "1分あたりのメッセージ数"),
    "Top Chatters": ("发言排行", "発言ランキング"),
    "Chat stats will appear once messages arrive.": ("收到消息后将显示聊天统计。", "メッセージが届くとチャット統計が表示されます。"),
    "🛡️ Filtered / blocked messages": ("🛡️ 已过滤 / 屏蔽的消息", "🛡️ フィルター / ブロックされたメッセージ"),
    "No blocked messages.": ("没有被屏蔽的消息。", "ブロックされたメッセージはありません。"),
    # ── Filters tab ──────────────────────────────────────────────────────────
    "🛡️ Chat Filters": ("🛡️ 聊天过滤", "🛡️ チャットフィルター"),
    "Keyword / Regex Block Patterns": ("关键词 / 正则屏蔽规则", "キーワード / 正規表現ブロック"),
    "Each pattern is a Python regex (case-insensitive by default).": (
        "每条规则都是 Python 正则表达式（默认不区分大小写）。",
        "各パターンは Python の正規表現です（既定で大文字小文字を区別しません）。",
    ),
    "No keyword filters.": ("没有关键词过滤。", "キーワードフィルターはありません。"),
    "New pattern (regex)": ("新规则（正则）", "新しいパターン（正規表現）"),
    "Add": ("添加", "追加"),
    "Allow Patterns (override block)": ("允许规则（优先于屏蔽）", "許可パターン（ブロックより優先）"),
    "New allow pattern": ("新允许规则", "新しい許可パターン"),
    "Add allow pattern": ("添加允许规则", "許可パターンを追加"),
    "Blocked Users": ("已屏蔽用户", "ブロック中のユーザー"),
    "No blocked users.": ("没有被屏蔽的用户。", "ブロック中のユーザーはいません。"),
    "Block by user ID / channel ID": ("按用户 ID / 频道 ID 屏蔽", "ユーザー ID / チャンネル ID でブロック"),
    "Block": ("屏蔽", "ブロック"),
    # ── Overlay tab ──────────────────────────────────────────────────────────
    "🖥️ Chat Overlay": ("🖥️ 聊天叠加层", "🖥️ チャットオーバーレイ"),
    "Use the overlay URL in OBS as a **Browser Source** to show a transparent chat on stream.": (
        "在 OBS 中将叠加层 URL 添加为**浏览器来源**，即可在直播画面显示透明聊天框。",
        "OBS でオーバーレイ URL を**ブラウザソース**として追加すると、配信画面に透過チャットを表示できます。",
    ),
    "**How to use**: Add a Browser Source in OBS pointing to `{url}`. "
    "Keep the dashboard open for live updates.": (
        "**使用方法**：在 OBS 中添加指向 `{url}` 的浏览器来源。"
        "保持仪表板打开以接收实时更新。",
        "**使い方**：OBS のブラウザソースに `{url}` を設定してください。"
        "ライブ更新にはダッシュボードを開いたままにしてください。",
    ),
    "Overlay channel": ("叠加层频道", "オーバーレイチャンネル"),
    "Sites on this overlay": ("此叠加层显示的网站", "このオーバーレイに表示するサイト"),
    "Show only some sites' chat — e.g. one Browser Source per site. Adds ?site=… to the overlay URL; leave all selected (or empty) for every site.": (
        "只显示部分网站的聊天——例如每个网站一个浏览器源。会在叠加层网址中加入 ?site=…；全部选中（或留空）则显示所有网站。",
        "一部のサイトのチャットだけを表示します（例：サイトごとにブラウザソースを 1 つ）。オーバーレイ URL に ?site=… を追加します。すべて選択（または空）ですべてのサイトを表示します。",
    ),
    "Each dashboard user can pick their own channel name so their overlays don't overwrite each other. Letters, digits, - and _ only.": (
        "每位仪表板用户可使用自己的频道名，避免叠加层互相覆盖。仅限字母、数字、- 和 _。",
        "ダッシュボードの利用者ごとに別のチャンネル名を使うと、オーバーレイが互いに上書きされません。英数字・-・_ のみ。",
    ),
    "The overlay only accepts connections from this computer. If OBS runs on another machine, set OVERLAY_HOST=0.0.0.0 in .env and restart.": (
        "叠加层仅接受本机连接。若 OBS 在其他电脑上运行，请在 .env 中设置 OVERLAY_HOST=0.0.0.0 并重启。",
        "オーバーレイはこのコンピューターからの接続のみ受け付けます。OBS が別のマシンで動いている場合は .env に OVERLAY_HOST=0.0.0.0 を設定して再起動してください。",
    ),
    "Couldn't start the chat overlay on port {port}: {err}": (
        "无法在端口 {port} 启动聊天叠加层：{err}",
        "ポート {port} でチャットオーバーレイを起動できません：{err}",
    ),
    "Custom overlay message (shown permanently on stream)": (
        "自定义叠加消息（常驻显示在直播画面）",
        "カスタムオーバーレイメッセージ（配信画面に常時表示）",
    ),
    "Show custom overlay message": ("显示自定义叠加消息", "カスタムメッセージを表示"),
    "Show usernames in OBS overlay": ("在 OBS 叠加层显示用户名", "OBS オーバーレイにユーザー名を表示"),
    "Messages shown in OBS overlay": ("OBS 叠加层显示的消息数", "OBS オーバーレイに表示するメッセージ数"),
    "Super Chats & gifts shown in OBS overlay": ("OBS 叠加层显示的醒目留言和礼物数", "OBS オーバーレイに表示するスーパーチャット・ギフト数"),
    "Super Chats, gifts and memberships are pinned to the top of the overlay, apart from regular chat, so busy chat never pushes them away. Set to 0 to hide them.": (
        "醒目留言、礼物和会员固定在叠加层顶部，与普通聊天分开，聊天再多也不会把它们挤走。设为 0 则隐藏。",
        "スーパーチャット・ギフト・メンバーシップはオーバーレイ上部に固定され、通常チャットとは別なので、チャットが多くても押し出されません。0 で非表示。",
    ),
    "Recent Chat Preview (last {n} messages)": ("最近聊天预览（最后 {n} 条）", "最近のチャットプレビュー（最新 {n} 件）"),
    # ── Cookies tab ──────────────────────────────────────────────────────────
    "🍪 Import login cookies": ("🍪 导入登录 Cookie", "🍪 ログイン Cookie をインポート"),
    "🧭 Browser on this computer": ("🧭 本机浏览器", "🧭 このパソコンのブラウザ"),
    "📋 Paste / upload cookies": ("📋 粘贴 / 上传 Cookie", "📋 Cookie を貼り付け / アップロード"),
    "Source": ("来源", "取得元"),
    "Use Paste / upload when the app runs on another computer or a server, "
    "where it can't see your browser.": (
        "当应用运行在其他电脑或服务器上、无法访问你的浏览器时，请使用粘贴 / 上传。",
        "アプリが別のパソコンやサーバーで動いていてブラウザにアクセスできない場合は、貼り付け / アップロードを使ってください。",
    ),
    "In your own browser, export the site's cookies with an extension such as "
    "\"Get cookies.txt LOCALLY\" or \"Cookie-Editor\" (Export → JSON or Netscape), or copy the "
    "Cookie request header from DevTools (F12 → Network → any request to the site). "
    "Paste it below or upload the exported file. Only cookies for the chosen site are used.": (
        "在你自己的浏览器中，用 \"Get cookies.txt LOCALLY\" 或 \"Cookie-Editor\" 等扩展导出该网站的 Cookie"
        "（导出为 JSON 或 Netscape 格式），或从开发者工具复制 Cookie 请求头（F12 → 网络 → 任意发往该网站的请求）。"
        "粘贴到下方或上传导出的文件。只会使用所选网站的 Cookie。",
        "自分のブラウザで \"Get cookies.txt LOCALLY\" や \"Cookie-Editor\" などの拡張機能を使ってサイトの Cookie を"
        "エクスポートするか（JSON または Netscape 形式）、開発者ツールから Cookie リクエストヘッダーをコピーしてください"
        "（F12 → ネットワーク → サイトへの任意のリクエスト）。下に貼り付けるか、エクスポートしたファイルをアップロードします。"
        "選択したサイトの Cookie だけが使われます。",
    ),
    "Cookies": ("Cookie", "Cookie"),
    "…or upload an exported file": ("…或上传导出的文件", "…またはエクスポートしたファイルをアップロード"),
    "No cookies for {site} found in that text.": ("在该文本中未找到 {site} 的 Cookie。", "そのテキストに {site} の Cookie が見つかりません。"),
    "the pasted cookies": ("粘贴的 Cookie", "貼り付けた Cookie"),
    "Reads cookies from a browser installed on this computer. Values never leave this "
    "machine except when verifying the login with the site itself.": (
        "从本机已安装的浏览器读取 Cookie。除向对应网站验证登录外，Cookie 值不会离开本机。",
        "このコンピューターのブラウザから Cookie を読み取ります。各サイトでのログイン確認以外で"
        "値がこのマシンの外に送られることはありません。",
    ),
    "You can now send chat to MissEvan.": ("现在可以向猫耳FM 发送弹幕了。", "MissEvan にチャットを送信できます。"),
    "MissEvan reports these cookies are not logged in — log in at fm.missevan.com first.": (
        "猫耳FM 报告这些 Cookie 未登录——请先在 fm.missevan.com 登录。",
        "MissEvan によるとこの Cookie は未ログインです — 先に fm.missevan.com にログインしてください。",
    ),
    "Log in to MissEvan in the 🍪 Cookies tab first.": (
        "请先在 🍪 Cookie 标签页登录猫耳FM。",
        "先に 🍪 Cookie タブで MissEvan にログインしてください。",
    ),
    "Enter a MissEvan room first.": ("请先输入猫耳FM 房间号。", "先に MissEvan のルームを入力してください。"),
    "Failed to send to {site}: {err}": ("发送到 {site} 失败：{err}", "{site} への送信に失敗しました：{err}"),
    "browser-cookie3 is not installed. Run `pip install browser-cookie3`.": (
        "未安装 browser-cookie3。请运行 `pip install browser-cookie3`。",
        "browser-cookie3 がインストールされていません。`pip install browser-cookie3` を実行してください。",
    ),
    "Browser": ("浏览器", "ブラウザ"),
    "Site": ("网站", "サイト"),
    "Chrome/Edge on Windows encrypt cookies with app-bound encryption and may require "
    "running the app as administrator. Firefox works without elevation. Close the "
    "browser if its cookie database is locked.": (
        "Windows 上的 Chrome/Edge 使用应用绑定加密，可能需要以管理员身份运行本程序。"
        "Firefox 无需提权。如果 Cookie 数据库被锁定，请关闭浏览器。",
        "Windows の Chrome/Edge はアプリバインド暗号化を使うため、管理者として実行する必要がある場合があります。"
        "Firefox は昇格不要です。Cookie データベースがロックされている場合はブラウザを閉じてください。",
    ),
    "Read cookies": ("读取 Cookie", "Cookie を読み取る"),
    "**{n} cookies** found for {site} in {browser}.": (
        "在 {browser} 中找到 {site} 的 **{n} 个 Cookie**。",
        "{browser} で {site} の **Cookie {n} 件**が見つかりました。",
    ),
    "Cookie": ("Cookie", "Cookie"),
    "Value": ("值", "値"),
    "❌ missing": ("❌ 缺失", "❌ なし"),
    "Logged in as **{uname}** (UID {mid}).": ("已登录为 **{uname}**（UID {mid}）。", "**{uname}** としてログイン中（UID {mid}）。"),
    "Bilibili reports these cookies are not logged in (expired or signed out).": (
        "B站报告这些 Cookie 未登录（已过期或已退出）。",
        "Bilibili によるとこの Cookie はログインしていません（期限切れまたはログアウト済み）。",
    ),
    "No SESSDATA cookie found — log in to bilibili.com in this browser first.": (
        "未找到 SESSDATA Cookie — 请先在此浏览器登录 bilibili.com。",
        "SESSDATA Cookie が見つかりません — 先にこのブラウザで bilibili.com にログインしてください。",
    ),
    "✅ Use these cookies": ("✅ 使用这些 Cookie", "✅ この Cookie を使用"),
    " Bilibili listener reconnected with the new login.": (
        " B站监听已使用新登录重新连接。",
        " 新しいログインで Bilibili 受信に再接続しました。",
    ),
    "Logged in to YouTube as **{name}**.": ("已登录 YouTube：**{name}**。", "YouTube に **{name}** としてログイン中。"),
    "No YouTube login cookies found — log in to youtube.com in this browser first.": (
        "未找到 YouTube 登录 Cookie — 请先在此浏览器登录 youtube.com。",
        "YouTube ログイン Cookie が見つかりません — 先にこのブラウザで youtube.com にログインしてください。",
    ),
    "YouTube reports these cookies are not logged in (expired or signed out).": (
        "YouTube 报告这些 Cookie 未登录（已过期或已退出）。",
        "YouTube によるとこの Cookie はログインしていません（期限切れまたはログアウト済み）。",
    ),
    "Not logged in — chat is read-only. Import cookies in the 🍪 Cookies tab to send.": (
        "未登录——只能查看聊天。要发送消息，请在 🍪 Cookie 标签页导入 Cookie。",
        "未ログイン — チャットは閲覧のみです。送信するには 🍪 Cookie タブで Cookie をインポートしてください。",
    ),
    "All cookie names (values masked)": ("所有 Cookie 名称（值已隐藏）", "すべての Cookie 名（値は伏せ字）"),
    "A live stream URL or video ID, or a channel link like https://www.youtube.com/@name — a channel's chat is picked up automatically when it goes live.": (
        '直播链接或视频 ID，或频道链接（如 https://www.youtube.com/@name）— 频道开播时会自动读取其聊天。',
        'ライブ配信の URL または動画 ID、またはチャンネルリンク（例: https://www.youtube.com/@name）— チャンネルが配信を始めると自動でチャットを読み取ります。',
    ),
    'Cookie login is unofficial (it works like youtube.com itself) and may break if YouTube changes it.': (
        'Cookie 登录是非官方方式（与 youtube.com 本身相同），YouTube 改版时可能失效。',
        'Cookie ログインは非公式（youtube.com と同じ方式）で、YouTube の変更で使えなくなる場合があります。',
    ),
    'Could not fetch stream info.': (
        '无法获取直播信息。',
        '配信情報を取得できませんでした。',
    ),
    'Failed to send to {site} (check the login cookies).': (
        '发送到 {site} 失败（请检查登录 Cookie）。',
        '{site} への送信に失敗しました（ログイン Cookie を確認してください）。',
    ),
    'UID {mid}': (
        'UID {mid}',
        'UID {mid}',
    ),
    'You can now send YouTube chat.': (
        '现在可以发送 YouTube 聊天了。',
        'YouTube チャットを送信できるようになりました。',
    ),
    '⏹ Stop listening': (
        '⏹ 停止监听',
        '⏹ 受信を停止',
    ),
    '▶ Start listening': (
        '▶ 开始监听',
        '▶ 受信を開始',
    ),
    '🎧 Connecting…': (
        '🎧 连接中…',
        '🎧 接続中…',
    ),
    '🎧 Listening anonymously — Bilibili masks usernames (e.g. 波***). Import login cookies in the 🍪 Cookies tab.': (
        '🎧 正在匿名监听 — B站会隐藏用户名（如 波***）。请在 🍪 Cookies 标签页导入登录 Cookie。',
        '🎧 匿名で受信中 — Bilibili はユーザー名を伏せます（例: 波***）。🍪 Cookies タブでログイン Cookie を取り込んでください。',
    ),
    '🎧 Listening ✓': (
        '🎧 监听中 ✓',
        '🎧 受信中 ✓',
    ),
    '🎧 Not listening.': (
        '🎧 未监听。',
        '🎧 受信していません。',
    ),
    "🔑 Couldn't check the login: {err}": (
        '🔑 无法检查登录状态：{err}',
        '🔑 ログイン状態を確認できませんでした: {err}',
    ),
    "Send as": ("发送身份", "送信するチャンネル"),
    "This Google login owns several YouTube channels — pick which one your chat messages come from.": (
        "此 Google 账号拥有多个 YouTube 频道——选择以哪个频道发送聊天消息。",
        "この Google アカウントには複数の YouTube チャンネルがあります。チャットを送信するチャンネルを選んでください。",
    ),
    "🚪 Clear login": ("🚪 清除登录", "🚪 ログインを解除"),
    "Forget your login cookies for this site (also removed from this browser). Chat keeps working read-only.": (
        "清除你在此网站的登录 Cookie（也会从此浏览器删除）。聊天仍可只读查看。",
        "このサイトのあなたのログイン Cookie を削除します（このブラウザからも削除）。チャットは閲覧のみで引き続き使えます。",
    ),
    "Login saved for you only — kept encrypted in this browser, not shared with other users.": (
        "登录仅对你保存——加密保存在此浏览器中，不会与其他用户共享。",
        "ログインはあなた専用に保存されました — このブラウザに暗号化して保持され、他のユーザーとは共有されません。",
    ),
    "Your logins are yours only: other people opening this dashboard don't see or use them. They are kept encrypted in this browser, so they survive a refresh; use 🚪 Clear login to forget them.": (
        "登录仅属于你：其他打开此仪表板的人看不到也无法使用。登录加密保存在此浏览器中，刷新后仍然有效；使用 🚪 清除登录 可将其删除。",
        "ログインはあなた専用です：このダッシュボードを開いた他の人には見えず、使われることもありません。このブラウザに暗号化して保持されるため再読み込み後も有効です。🚪 ログインを解除 で削除できます。",
    ),
    "Cleared the {site} login.": ("已清除 {site} 登录。", "{site} のログインを解除しました。"),
    '🔑 Logged in as **{name}**': (
        '🔑 已登录：**{name}**',
        '🔑 **{name}** としてログイン中',
    ),
    '🔑 Login expired — re-import cookies in the 🍪 Cookies tab.': (
        '🔑 登录已过期 — 请在 🍪 Cookies 标签页重新导入 Cookie。',
        '🔑 ログインの期限切れ — 🍪 Cookies タブで Cookie を取り込み直してください。',
    ),
    '🔑 Not logged in — chat is read-only. Import cookies in the 🍪 Cookies tab to send.': (
        '🔑 未登录 — 聊天为只读。在 🍪 Cookies 标签页导入 Cookie 后即可发送。',
        '🔑 未ログイン — チャットは閲覧のみ。送信するには 🍪 Cookies タブで Cookie を取り込んでください。',
    ),
}

_INDEX = {"zh": 0, "ja": 1}


def translate(text: str, lang: str, **kwargs) -> str:
    """Return `text` in `lang` (falls back to English) with `{placeholders}` filled in."""
    idx = _INDEX.get(lang)
    out = text
    if idx is not None and text in _STRINGS:
        out = _STRINGS[text][idx]
    return out.format(**kwargs) if kwargs else out
