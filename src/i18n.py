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
    "Google returned: {err}": ("Google 返回：{err}", "Google からの応答：{err}"),
    "YouTube sign-in complete!": ("YouTube 登录完成！", "YouTube のサインインが完了しました！"),
    "Authenticated ✓": ("已认证 ✓", "認証済み ✓"),
    "Not authenticated": ("未认证", "未認証"),
    "Start YouTube OAuth": ("开始 YouTube OAuth 登录", "YouTube OAuth を開始"),
    "Set YOUTUBE_CLIENT_ID / CLIENT_SECRET in .env first.": (
        "请先在 .env 中设置 YOUTUBE_CLIENT_ID / CLIENT_SECRET。",
        "先に .env で YOUTUBE_CLIENT_ID / CLIENT_SECRET を設定してください。",
    ),
    "Open Google sign-in": ("打开 Google 登录", "Google サインインを開く"),
    "After you approve, Google redirects back here and sign-in completes automatically. "
    "If it doesn't, paste the full redirect URL below.": (
        "授权后 Google 会跳转回此页面并自动完成登录。如果没有，请在下方粘贴完整的跳转 URL。",
        "承認すると Google がこのページに戻り、自動的にサインインが完了します。"
        "完了しない場合は、リダイレクト URL 全体を下に貼り付けてください。",
    ),
    "Redirect URL or code": ("跳转 URL 或授权码", "リダイレクト URL またはコード"),
    "Submit": ("提交", "送信"),
    "Authenticated!": ("认证成功！", "認証しました！"),
    "Live stream URL, video ID, or live chat ID": (
        "直播 URL、视频 ID 或聊天 ID",
        "配信 URL、動画 ID、またはライブチャット ID",
    ),
    "{n} watching": ("{n} 人观看", "{n} 人が視聴中"),
    "Upcoming": ("即将开始", "配信予定"),
    "YouTube chat listener active ✓": ("YouTube 聊天监听中 ✓", "YouTube チャット受信中 ✓"),
    "Chat ID: `{chat_id}`": ("聊天 ID：`{chat_id}`", "チャット ID：`{chat_id}`"),
    "Reading chat without sign-in. Sign in to send messages or moderate.": (
        "无需登录即可读取聊天。登录后才能发送消息或管理。",
        "サインインなしでチャットを読み込み中。メッセージ送信やモデレーションにはサインインが必要です。",
    ),
    "Stop YouTube listener": ("停止 YouTube 监听", "YouTube 受信を停止"),
    "Start YouTube listener": ("开始 YouTube 监听", "YouTube 受信を開始"),
    "Room ID": ("房间号", "ルーム ID"),
    "popularity {n}": ("人气 {n}", "人気 {n}"),
    "Playback": ("轮播中", "再放送中"),
    "LIVE": ("直播中", "配信中"),
    "Offline": ("未开播", "オフライン"),
    "Danmaku listener connecting…": ("弹幕监听连接中…", "弾幕受信に接続中…"),
    "Danmaku listener active, but **anonymous** — Bilibili masks usernames (e.g. 波***). "
    "Import login cookies in the 🍪 Cookies tab.": (
        "弹幕监听中，但为**匿名**连接 — B站会隐藏用户名（如 波***）。请在 🍪 Cookies 标签页导入登录 Cookie。",
        "弾幕受信中ですが**匿名**接続です — Bilibili はユーザー名を伏せ字にします（例：波***）。"
        "🍪 Cookies タブでログイン Cookie をインポートしてください。",
    ),
    "Danmaku listener active ✓ (logged in, UID {uid})": (
        "弹幕监听中 ✓（已登录，UID {uid}）",
        "弾幕受信中 ✓（ログイン済み、UID {uid}）",
    ),
    "Stop Bilibili listener": ("停止 B站监听", "Bilibili 受信を停止"),
    "No Bilibili login cookies set — chat usernames will be masked.": (
        "未设置 B站登录 Cookie — 弹幕用户名将被隐藏。",
        "Bilibili のログイン Cookie が未設定です — ユーザー名は伏せ字になります。",
    ),
    "Start Bilibili listener": ("开始 B站监听", "Bilibili 受信を開始"),
    "Room ID or URL": ("房间号或链接", "ルームIDまたはURL"),
    "Could not find a room ID in that text.": ("无法从输入中找到房间号。", "入力からルームIDが見つかりません。"),
    "{n} online": ("{n} 人在线", "{n} 人視聴中"),
    "MissEvan room not found.": ("找不到该猫耳FM直播间。", "MissEvan のルームが見つかりません。"),
    "MissEvan chat listener active ✓": ("猫耳FM 弹幕监听中 ✓", "MissEvan チャット受信中 ✓"),
    "MissEvan chat listener connecting…": ("猫耳FM 弹幕连接中…", "MissEvan チャットに接続中…"),
    "Stop MissEvan listener": ("停止猫耳FM 监听", "MissEvan 受信を停止"),
    "Start MissEvan listener": ("开始猫耳FM 监听", "MissEvan 受信を開始"),
    "Shows chat, gifts, paid questions and joins without login. To send chat, log in via the 🍪 Cookies tab.": (
        "无需登录即可显示弹幕、礼物、付费提问和进场。如需发送弹幕，请在 🍪 Cookie 标签页登录。",
        "ログインなしでチャット、ギフト、有料質問、入室を表示します。チャット送信には 🍪 Cookie タブでログインしてください。",
    ),
    "MissEvan": ("猫耳FM", "MissEvan"),
    "Followers: {n}": ("关注：{n}", "フォロワー：{n}"),
    "MissEvan messages": ("猫耳FM 消息", "MissEvan メッセージ"),
    "Listener started!": ("监听已启动！", "受信を開始しました！"),
    "bilibili-api-python not installed or connection failed.": (
        "未安装 bilibili-api-python 或连接失败。",
        "bilibili-api-python が未インストールか、接続に失敗しました。",
    ),
    "OBS connected ✓": ("OBS 已连接 ✓", "OBS 接続済み ✓"),
    "Scene": ("场景", "シーン"),
    "OBS not connected — check OBS_HOST/PORT/PASSWORD in .env": (
        "OBS 未连接 — 请检查 .env 中的 OBS_HOST/PORT/PASSWORD",
        "OBS 未接続 — .env の OBS_HOST/PORT/PASSWORD を確認してください",
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
    "Ban/block user": ("封禁/屏蔽用户", "ユーザーをBAN/ブロック"),
    "Read this message aloud": ("朗读这条消息", "このメッセージを読み上げる"),
    "translating…": ("翻译中…", "翻訳中…"),
    # ── Tabs ─────────────────────────────────────────────────────────────────
    "💬 Chat": ("💬 聊天", "💬 チャット"),
    "📡 Stream Status": ("📡 直播状态", "📡 配信状況"),
    "🎬 OBS Control": ("🎬 OBS 控制", "🎬 OBS 操作"),
    "📊 Analytics": ("📊 数据分析", "📊 分析"),
    "🛡️ Filters": ("🛡️ 过滤", "🛡️ フィルター"),
    "🖥️ Overlay": ("🖥️ 叠加层", "🖥️ オーバーレイ"),
    "🍪 Cookies": ("🍪 Cookies", "🍪 Cookie"),
    # ── Chat tab ─────────────────────────────────────────────────────────────
    "⚠️ Action on {author}": ("⚠️ 处理 {author}", "⚠️ {author} への操作"),
    "Timeout (minutes, 0=permanent)": ("禁言时长（分钟，0=永久）", "タイムアウト（分、0=永久）"),
    "🚫 Ban / Timeout": ("🚫 封禁 / 禁言", "🚫 BAN / タイムアウト"),
    "Blocked {author}": ("已屏蔽 {author}", "{author} をブロックしました"),
    "🗑️ Delete message": ("🗑️ 删除消息", "🗑️ メッセージを削除"),
    "Send to": ("发送到", "送信先"),
    "Both": ("两者", "両方"),
    "Start the YouTube listener first.": ("请先启动 YouTube 监听。", "先に YouTube 受信を開始してください。"),
    "Enter a Bilibili room ID first.": ("请先输入 B站房间号。", "先に Bilibili のルームIDを入力してください。"),
    "Tick at least one site to send to.": ("请至少勾选一个发送平台。", "送信先を1つ以上選択してください。"),
    "Sent to {site} ✓": ("已发送到 {site} ✓", "{site} に送信しました ✓"),
    "Failed to send to {site} (check sign-in / login cookies).": (
        "发送到 {site} 失败（请检查登录 / Cookie）。",
        "{site} への送信に失敗しました（サインイン / Cookie を確認）。",
    ),
    "Message": ("消息", "メッセージ"),
    "Type a message…": ("输入消息…", "メッセージを入力…"),
    "Send": ("发送", "送信"),
    "Chat": ("聊天", "チャット"),
    "Gifts & Super Chats": ("礼物和醒目留言", "ギフトとスーパーチャット"),
    "{n} to thank": ("{n} 条待感谢", "未お礼 {n} 件"),
    "{n} total": ("共 {n} 条", "合計 {n} 件"),
    "🙏 Mark all thanked": ("🙏 全部标为已感谢", "🙏 すべてお礼済みにする"),
    "No gifts or Super Chats yet.": ("还没有礼物或醒目留言。", "まだギフトやスーパーチャットはありません。"),
    "Thanked": ("已感谢", "お礼済み"),
    "Mark as thanked": ("标为已感谢", "お礼済みにする"),
    "Undo: mark as not thanked yet": ("撤销：标为未感谢", "取り消し：未お礼に戻す"),
    "Auto-refreshes every {s}s · {n} messages shown": (
        "每 {s} 秒自动刷新 · 显示 {n} 条消息",
        "{s} 秒ごとに自動更新 · {n} 件表示",
    ),
    # ── Stream status tab ────────────────────────────────────────────────────
    "Enter a stream URL in the sidebar.": ("请在侧边栏输入直播 URL。", "サイドバーに配信 URL を入力してください。"),
    "Status needs a stream URL or video ID (a raw chat ID has no video info).": (
        "需要直播 URL 或视频 ID 才能显示状态（聊天 ID 不包含视频信息）。",
        "状況の表示には配信 URL または動画 ID が必要です（チャット ID には動画情報がありません）。",
    ),
    "Could not fetch stream info (sign in or set YOUTUBE_API_KEY).": (
        "无法获取直播信息（请登录或设置 YOUTUBE_API_KEY）。",
        "配信情報を取得できません（サインインするか YOUTUBE_API_KEY を設定してください）。",
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
    "Enter a room ID in the sidebar.": ("请在侧边栏输入房间号。", "サイドバーにルーム ID を入力してください。"),
    "Could not fetch room info.": ("无法获取房间信息。", "ルーム情報を取得できません。"),
    "Streamer: {name}": ("主播：{name}", "配信者：{name}"),
    "Category: {area} › {sub}": ("分区：{area} › {sub}", "カテゴリ：{area} › {sub}"),
    # ── OBS tab ──────────────────────────────────────────────────────────────
    "⚠️ OBS is not connected. Configure OBS WebSocket settings in your .env file.": (
        "⚠️ OBS 未连接。请在 .env 文件中配置 OBS WebSocket 设置。",
        "⚠️ OBS が接続されていません。.env ファイルで OBS WebSocket を設定してください。",
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
    "**How to use**: Add a Browser Source in OBS pointing to `http://localhost:8501/overlay` "
    "— or copy the overlay HTML below into a local file and load it as a file URL.": (
        "**使用方法**：在 OBS 中添加指向 `http://localhost:8501/overlay` 的浏览器来源，"
        "或将下方的叠加层 HTML 保存为本地文件并以文件 URL 加载。",
        "**使い方**：OBS で `http://localhost:8501/overlay` を指すブラウザソースを追加するか、"
        "下のオーバーレイ HTML をローカルファイルに保存してファイル URL として読み込みます。",
    ),
    "Custom overlay message (shown permanently on stream)": (
        "自定义叠加消息（常驻显示在直播画面）",
        "カスタムオーバーレイメッセージ（配信画面に常時表示）",
    ),
    "Show custom overlay message": ("显示自定义叠加消息", "カスタムメッセージを表示"),
    "Recent Chat Preview (last 5 messages)": ("最近聊天预览（最后 5 条）", "最近のチャットプレビュー（最新 5 件）"),
    "Standalone Overlay HTML": ("独立叠加层 HTML", "スタンドアロン オーバーレイ HTML"),
    "Save as `overlay.html` and open in OBS Browser Source.": (
        "保存为 `overlay.html` 并在 OBS 浏览器来源中打开。",
        "`overlay.html` として保存し、OBS のブラウザソースで開きます。",
    ),
    # ── Cookies tab ──────────────────────────────────────────────────────────
    "🍪 Import login cookies from browser": ("🍪 从浏览器导入登录 Cookie", "🍪 ブラウザからログイン Cookie をインポート"),
    "Reads cookies from a browser installed on this computer. Values never leave this "
    "machine except when verifying the login with the site itself.": (
        "从本机已安装的浏览器读取 Cookie。除向对应网站验证登录外，Cookie 值不会离开本机。",
        "このコンピューターのブラウザから Cookie を読み取ります。各サイトでのログイン確認以外で"
        "値がこのマシンの外に送られることはありません。",
    ),
    "Saved MISSEVAN_COOKIE to .env — you can now send chat to MissEvan.": (
        "已将 MISSEVAN_COOKIE 保存到 .env——现在可以向猫耳FM 发送弹幕了。",
        "MISSEVAN_COOKIE を .env に保存しました — MissEvan にチャットを送信できます。",
    ),
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
    "Env var": ("环境变量", "環境変数"),
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
    "💾 Save to .env and apply": ("💾 保存到 .env 并应用", "💾 .env に保存して適用"),
    "Saved {keys} to .env.": ("已将 {keys} 保存到 .env。", "{keys} を .env に保存しました。"),
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
    "Saved YOUTUBE_COOKIE to .env — you can now send YouTube chat without OAuth.": (
        "已将 YOUTUBE_COOKIE 保存到 .env——现在无需 OAuth 即可发送 YouTube 聊天。",
        "YOUTUBE_COOKIE を .env に保存しました — OAuth なしで YouTube チャットを送信できます。",
    ),
    "Cookie login is unofficial (it works like youtube.com itself) and may break if YouTube "
    "changes it. OAuth sign-in, if set up, is used first.": (
        "Cookie 登录为非官方方式（与 youtube.com 网页相同），YouTube 更改后可能失效。若已设置 OAuth 登录，将优先使用 OAuth。",
        "Cookie ログインは非公式（youtube.com と同じ仕組み）で、YouTube の変更により使えなくなる可能性があります。"
        "OAuth サインインが設定されている場合はそちらが優先されます。",
    ),
    "Signed in with browser cookies ✓ (sending chat)": ("已通过浏览器 Cookie 登录 ✓（发送聊天）", "ブラウザ Cookie でログイン済み ✓（チャット送信）"),
    "OAuth is optional — needed only for ban / delete and your own broadcast stats.": (
        "OAuth 为可选——仅在封禁 / 删除消息和查看自己的直播统计时需要。",
        "OAuth は任意です — BAN / 削除と自分の配信統計にのみ必要です。",
    ),
    "All cookie names (values masked)": ("所有 Cookie 名称（值已隐藏）", "すべての Cookie 名（値は伏せ字）"),
}

_INDEX = {"zh": 0, "ja": 1}


def translate(text: str, lang: str, **kwargs) -> str:
    """Return `text` in `lang` (falls back to English) with `{placeholders}` filled in."""
    idx = _INDEX.get(lang)
    out = text
    if idx is not None and text in _STRINGS:
        out = _STRINGS[text][idx]
    return out.format(**kwargs) if kwargs else out
