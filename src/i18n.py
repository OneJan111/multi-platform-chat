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
    "YouTube chat listener active ✓": ("YouTube 弹幕监听中 ✓", "YouTube チャット受信中 ✓"),
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
    "🖥️ Standalone overlay for OBS": ("🖥️ OBS 独立弹幕层", "🖥️ OBS 用スタンドアロンオーバーレイ"),
    "Enter a YouTube channel, Bilibili room or MissEvan room in the 📡 Stream Monitoring tab "
    "to get your overlay link.": (
        "在 📡 直播监控 标签页输入 YouTube 频道、B站房间或猫耳FM 房间，即可获得弹幕层链接。",
        "📡 配信モニタリング タブで YouTube チャンネル、Bilibili ルーム、MissEvan ルームを入力すると、"
        "オーバーレイのリンクが表示されます。",
    ),
    "↗ Open": ("↗ 打开", "↗ 開く"),
    "Copy the link (point at it, then click the copy icon on its right). In OBS: Sources ＋ → Browser → paste it as the URL "
    "(Width 400, Height 600) → OK. It keeps working after you close this page, as long as the "
    "dashboard program is running. The overlay settings below change this link.": (
        "复制链接（把鼠标移到链接上，点右侧的复制图标）。在 OBS 中：来源 ＋ → 浏览器 → 粘贴到 URL（宽 400，高 600）→ 确定。"
        "只要仪表板程序在运行，关闭此页面后仍然有效。下方的弹幕层设置会改变此链接。",
        "リンクをコピーします（リンクにマウスを乗せ、右側のコピーアイコンをクリック）。OBS で：ソース ＋ → ブラウザ → URL に貼り付け（幅 400、高さ 600）→ OK。"
        "ダッシュボードのプログラムが動いていれば、このページを閉じても表示され続けます。"
        "下のオーバーレイ設定でこのリンクが変わります。",
    ),
    "What can I change in this link?": ("这个链接可以改什么？", "このリンクで変更できること"),
    "All (Super Chats & gifts on top, chat below)": (
        "全部（醒目留言和礼物在上，弹幕在下）",
        "すべて（上にスーパーチャットとギフト、下にチャット）",
    ),
    "Super Chats & gifts only": ("仅醒目留言和礼物", "スーパーチャットとギフトのみ"),
    "Chat only": ("仅弹幕", "チャットのみ"),
    "Want Super Chats and chat in different places or scenes? Add one Browser Source with the "
    "\"Super Chats & gifts only\" link and another with the \"Chat only\" link.": (
        "想把醒目留言和弹幕放在不同位置或不同场景？用「仅醒目留言和礼物」链接添加一个浏览器源，再用「仅弹幕」链接添加另一个。",
        "スーパーチャットとチャットを別の位置やシーンに置きたい場合は、「スーパーチャットとギフトのみ」のリンクと"
        "「チャットのみ」のリンクでブラウザソースを 1 つずつ追加してください。",
    ),
    "⬆️ The overlay settings are at the top of this tab, under the standalone overlay link.": (
        "⬆️ 弹幕层设置在本标签页顶部的独立弹幕层链接下方。",
        "⬆️ オーバーレイ設定は、このタブの一番上のスタンドアロンオーバーレイのリンクの下にあります。",
    ),
    "⚙️ Overlay settings": ("⚙️ 弹幕层设置", "⚙️ オーバーレイ設定"),
    "📝 OBS Text source": ("📝 OBS 文本源", "📝 OBS テキストソース"),
    "Send chat to OBS Text source": ("将弹幕发送到 OBS 文本源", "チャットを OBS テキストソースに送信"),
    "OBS Text source": ("OBS 文本源", "OBS テキストソース"),
    "Add a Text source in OBS to display chat.": (
        "请在 OBS 中添加文本源以显示弹幕。",
        "チャットを表示するには OBS にテキストソースを追加してください。",
    ),
    "Couldn't list OBS Text sources: {err}": (
        "无法列出 OBS 文本源：{err}",
        "OBS テキストソースを取得できません：{err}",
    ),
    "Couldn't update OBS chat text: {err}": (
        "无法更新 OBS 弹幕文本：{err}",
        "OBS のチャットテキストを更新できません：{err}",
    ),
    "🌐 Translation": ("🌐 翻译", "🌐 翻訳"),
    "Translate chat": ("翻译弹幕", "チャットを翻訳"),
    "Site emotes": ("特制表情包", "サイト専用スタンプ"),
    "Expand all": ("全部展开", "すべて展開"),
    "Collapse all": ("全部收起", "すべて折りたたむ"),
    "Each site's own emotes, sent only to that site.": ("各网站的特制表情包，只发到该网站。", "各サイト専用のスタンプは、そのサイトにだけ送信されます。"),
    "🔄 Refresh": ("🔄 刷新", "🔄 更新"),
    "Members only": ("仅限会员", "メンバー限定"),
    "Locked": ("未解锁", "ロック中"),
    "No channel stamps seen yet.": ("还没有看到频道表情包。", "チャンネルのスタンプはまだ見つかっていません。"),
    "Sent only to YouTube. Click stamps to add them (as many as you like), add text if you want, then send. "
    "Channel stamps show up here once someone uses them in chat; with a YouTube login (🍪 Cookies tab) the "
    "full set is listed and 🔒 marks member-only stamps you can't use.": (
        "只发到 YouTube。点击表情包加入（可以加多个），也可以再输入文字，然后一次发送。有人在弹幕中使用频道表情包后，"
        "它们会出现在这里；登录 YouTube（🍪 Cookies 标签页）后会列出全部表情包，🔒 表示你无法使用的会员专属表情包。",
        "YouTube にだけ送信されます。スタンプをクリックして追加し（いくつでも）、必要なら文字も入れてまとめて送信します。"
        "チャットで誰かが使ったチャンネルスタンプがここに表示されます。YouTube にログイン（🍪 Cookies タブ）すると"
        "全スタンプが表示され、🔒 は使えないメンバー限定スタンプです。",
    ),
    "Click stamps above…": ("点击上方表情包…", "上のスタンプをクリック…"),
    "Send to YouTube": ("发送到 YouTube", "YouTube に送信"),
    "Clear": ("清空", "クリア"),
    "Sent only to Bilibili, as a sticker danmaku. 🔒 emotes need e.g. this room's fan medal, a guard "
    "membership, or charging (充电) the streamer for the 充电表情 tab.": (
        "只发到 B站，作为表情包弹幕。🔒 表情包需要本房间的粉丝勋章、大航海等条件；「充电表情」需要为主播充电。",
        "Bilibili にだけスタンプ弾幕として送信されます。🔒 のスタンプにはこの部屋のファンメダルや大航海などが必要です。"
        "「充电表情」は配信者への充電（充电）が必要です。",
    ),
    "This room has no emotes you can send.": ("这个房间没有你可以发送的表情包。", "この部屋で送信できるスタンプはありません。"),
    "Bilibili's emote server returned an error. Try 🔄 Refresh in a moment.": (
        "B站表情包接口返回服务器错误，请稍后点击 🔄 刷新重试。",
        "Bilibili のスタンプ API がサーバーエラーを返しました。少し待ってから 🔄 更新してください。"),
    "Only YouTube stamps — not sent to {site}.": ("只有 YouTube 表情包——未发送到 {site}。", "YouTube スタンプのみのため、{site} には送信しませんでした。"),
    "Not logged in to Bilibili — import cookies in the 🍪 Cookies tab.": (
        "未登录 B站——请在 🍪 Cookies 标签页导入 Cookie。", "Bilibili に未ログインです。🍪 Cookies タブで Cookie を読み込んでください。"),
    "Not logged in to YouTube — import cookies in the 🍪 Cookies tab.": (
        "未登录 YouTube——请在 🍪 Cookies 标签页导入 Cookie。", "YouTube に未ログインです。🍪 Cookies タブで Cookie を読み込んでください。"),
    "Not logged in to YouTube — import YouTube cookies in the 🍪 Cookies tab.": (
        "未登录 YouTube——请在 🍪 Cookies 标签页导入 YouTube Cookie。",
        "YouTube に未ログインです。🍪 Cookies タブで YouTube の Cookie を読み込んでください。"),
    "🔥 Hotspots for clipping": ("🔥 热点切片", "🔥 切り抜き用ホットスポット"),
    "Moments when chat, gifts and Super Chats spike well above this stream's usual activity, timed from "
    "the stream start so you can cut them from the recording. Covers messages received while this "
    "dashboard page is open.": (
        "弹幕、礼物和醒目留言明显高于本场平时水平的时刻，按开播后的时间标注，方便从录像中切片。"
        "只统计此仪表板页面打开期间收到的消息。",
        "チャット・ギフト・スーパーチャットが普段より大きく盛り上がった場面を、配信開始からの時間で示します。"
        "録画からの切り抜きに使えます。このダッシュボードを開いている間に受信したメッセージが対象です。",
    ),
    "Hotspots will appear once messages arrive.": ("收到消息后将显示热点。", "メッセージが届くとホットスポットが表示されます。"),
    "Time 0 (start of the recording)": ("时间零点（录像开始）", "0 秒の位置（録画の開始）"),
    "{site} stream start": ("{site} 开播时间", "{site} 配信開始"),
    "First message received": ("收到第一条消息时", "最初のメッセージ受信時"),
    "Custom clock time": ("自定义时刻", "時刻を指定"),
    "Clip times count from here. Pick the site whose recording you are cutting.": (
        "切片时间从这里开始计算。请选择你要剪辑的那个网站的录像。",
        "切り抜きの時間はここから数えます。切り抜く録画のサイトを選んでください。",
    ),
    "Recording started at": ("录像开始时刻", "録画開始時刻"),
    "Window (seconds)": ("统计窗口（秒）", "集計間隔（秒）"),
    "Sensitivity": ("灵敏度", "感度"),
    "How far above the usual activity a moment must be. Higher = fewer, bigger hotspots.": (
        "需要比平时活跃多少倍才算热点。越高 = 热点越少、越大。",
        "普段よりどれだけ盛り上がればホットスポットとみなすか。高いほど少なく大きな場面だけになります。",
    ),
    "Max hotspots": ("最多热点数", "最大ホットスポット数"),
    "Lead-in (seconds)": ("提前（秒）", "前余白（秒）"),
    "Chat reacts after the moment happens, so clips start this much earlier.": (
        "弹幕总是在事情发生之后才刷屏，所以切片会提前这么多秒开始。",
        "チャットは出来事の後に反応するので、切り抜きはこの秒数だけ早く始まります。",
    ),
    "Tail (seconds)": ("延后（秒）", "後余白（秒）"),
    "EDL frame rate": ("EDL 帧率", "EDL フレームレート"),
    "EDL timeline start": ("EDL 时间线起点", "EDL タイムライン開始"),
    "DaVinci Resolve timelines start at 01:00:00:00 by default.": (
        "DaVinci Resolve 的时间线默认从 01:00:00:00 开始。",
        "DaVinci Resolve のタイムラインは既定で 01:00:00:00 から始まります。",
    ),
    "No hotspots yet — chat hasn't spiked above its usual level. Try a lower sensitivity.": (
        "暂无热点——弹幕还没有明显高于平时水平。可以试试降低灵敏度。",
        "まだホットスポットはありません。チャットが普段より盛り上がっていません。感度を下げてみてください。",
    ),
    "Start": ("开始", "開始"),
    "End": ("结束", "終了"),
    "Length (s)": ("时长（秒）", "長さ（秒）"),
    "Peak": ("峰值", "ピーク"),
    "Clock time": ("实际时刻", "時刻"),
    "Heat": ("热度", "熱度"),
    "Messages": ("弹幕数", "メッセージ数"),
    "Gifts / SC": ("礼物 / SC", "ギフト / SC"),
    "Sites": ("网站", "サイト"),
    "Hot phrases": ("热词", "頻出ワード"),
    "⬇️ CSV (Excel)": ("⬇️ CSV（Excel）", "⬇️ CSV（Excel）"),
    "⬇️ Timestamps (.txt)": ("⬇️ 时间戳（.txt）", "⬇️ タイムスタンプ（.txt）"),
    "⬇️ Markers (.edl)": ("⬇️ 剪辑标记（.edl）", "⬇️ マーカー（.edl）"),
    "EDL: in DaVinci Resolve, put the recording on a timeline, then right-click the timeline in the "
    "Media Pool > Timelines > Import > Timeline Markers from EDL. Each hotspot becomes a red marker "
    "spanning the clip.": (
        "EDL：在 DaVinci Resolve 中把录像放到时间线上，然后在媒体池中右键该时间线 > 时间线 > 导入 > "
        "从 EDL 导入时间线标记。每个热点会成为一个覆盖整个片段的红色标记。",
        "EDL：DaVinci Resolve で録画をタイムラインに置き、メディアプールでそのタイムラインを右クリック > "
        "タイムライン > 読み込み > EDL からタイムラインマーカーを読み込み。各ホットスポットが区間付きの赤いマーカーになります。",
    ),
    "This server only lets browsers reach the dashboard's own address, so these overlay links open the "
    "dashboard in overlay-only mode (?view=overlay). If its background isn't transparent in OBS, add "
    "this to the Browser Source's Custom CSS: {css}": (
        "此服务器只开放仪表板本身的网址，因此这些叠加层链接会以仅叠加层模式（?view=overlay）打开仪表板。"
        "如果在 OBS 中背景不透明，请在浏览器来源的自定义 CSS 中加入：{css}",
        "このサーバーではダッシュボード自体のアドレスにしかアクセスできないため、これらのオーバーレイリンクは"
        "ダッシュボードをオーバーレイ専用モード（?view=overlay）で開きます。OBS で背景が透明にならない場合は、"
        "ブラウザソースのカスタム CSS に次を追加してください：{css}",
    ),
    "🕒 Chat time zone": ("🕒 弹幕时区", "🕒 チャットのタイムゾーン"),
    "Server time ({tz})": ("服务器时间（{tz}）", "サーバー時刻（{tz}）"),
    "{tz} (this browser)": ("{tz}（此浏览器）", "{tz}（このブラウザ）"),
    "Time zone for the times shown on chat messages.": ("弹幕消息上显示的时间所用的时区。", "チャットメッセージに表示する時刻のタイムゾーン。"),
    "Shows a translation under each chat message.": (
        "在每条弹幕消息下方显示翻译。",
        "各チャットメッセージの下に翻訳を表示します。",
    ),
    "Translate to": ("翻译为", "翻訳先"),
    "Super Chat reading aid": ("醒目留言注音", "スーパーチャットの読み仮名"),
    "Shows pinyin / furigana above Chinese characters in Super Chats and all usernames so you can read them aloud. "
    "Translations get furigana when Japanese, and Super Chat translations get pinyin when Chinese.": (
        "在醒目留言和所有用户名的汉字上方显示拼音 / 振假名，方便朗读。日语译文加振假名，醒目留言的中文译文加拼音。",
        "スーパーチャットとすべてのユーザー名の漢字の上にピンイン／振り仮名を表示し、読み上げやすくします。日本語の翻訳には振り仮名、スーパーチャットの中国語の翻訳にはピンインを付けます。",
    ),
    "🔊 Text-to-Speech": ("🔊 语音朗读", "🔊 読み上げ"),
    "Enable TTS": ("启用语音朗读", "読み上げを有効化"),
    "Speak on": ("朗读设备", "読み上げ先"),
    "This computer (Windows voices)": ("本机（Windows 语音）", "このPC（Windowsの音声）"),
    "This browser (device voices)": ("本浏览器（设备语音）", "このブラウザ（端末の音声）"),
    "Browser mode uses your device's own voices and only speaks while this page is open.": (
        "浏览器模式使用你设备自带的语音，仅在此页面打开时朗读。",
        "ブラウザモードは端末の音声を使い、このページを開いている間だけ読み上げます。",
    ),
    "🔈 Speaks with this device's voices while this page is open. Click anywhere on the page once so the browser allows sound.": (
        "🔈 在此页面打开时用本设备的语音朗读。请先在页面上任意点击一次，浏览器才允许播放声音。",
        "🔈 このページを開いている間、端末の音声で読み上げます。ブラウザが音声を許可するよう、ページを一度クリックしてください。",
    ),
    "⏹ TTS stopped · queue cleared": ("⏹ 已停止朗读 · 已清空队列", "⏹ 読み上げを停止 · キューをクリアしました"),
    "Language": ("语言", "言語"),
    "Auto-detect reads every message in its own language. Picking a language only reads chat written in that language.": (
        "自动检测会用每条消息自身的语言朗读全部消息。选择某种语言后，只朗读用该语言写的弹幕。",
        "自動検出ではすべてのメッセージをその言語で読み上げます。言語を選ぶと、その言語で書かれたチャットだけを読み上げます。",
    ),
    "Ignore emoji": ("忽略表情包", "絵文字を無視"),
    "Skip emoji-only messages and stickers, and don't read emoji inside messages.": (
        "跳过纯表情消息和表情包，并且不朗读消息中的表情。",
        "絵文字のみのメッセージやスタンプをスキップし、メッセージ内の絵文字も読み上げません。",
    ),
    "Read translated chat": ("朗读翻译后的弹幕", "翻訳したチャットを読み上げ"),
    "Read translated Super Chats": ("朗读翻译后的醒目留言", "翻訳したスーパーチャットを読み上げ"),
    "When the TTS language is Auto-detect or matches \"Translate to\" (Translation section), Super Chat "
    "messages are read translated into that language. Gift names are always read as they are.": (
        "当 TTS 语言为自动检测，或与「翻译为」语言（翻译设置）相同时，醒目留言会翻译成该语言后朗读。礼物名称始终按原样朗读。",
        "TTS の言語が自動検出、または「翻訳先」（翻訳セクション）と同じ場合、スーパーチャットのメッセージをその言語に翻訳して読み上げます。ギフト名は常にそのまま読み上げます。",
    ),
    "Choose what is read with 🔊 / 🔇 at the top of each list (Gifts & Super Chats, Chat, Joins). "
    "Gifts & Super Chats are read first, in any language.": (
        "在每个列表（礼物和醒目留言、弹幕、进场）顶部用 🔊 / 🔇 选择要朗读的内容。礼物和醒目留言无论语言都会优先朗读。",
        "各リスト（ギフトとスーパーチャット、チャット、入室）の上の 🔊 / 🔇 で読み上げる内容を選べます。"
        "ギフトとスーパーチャットは言語に関係なく優先して読み上げます。",
    ),
    "🔊 Read aloud": ("🔊 朗读", "🔊 読み上げ"),
    "🔇 Muted": ("🔇 不朗读", "🔇 読み上げない"),
    "Text-to-speech reads this list. Click to mute it.": (
        "语音朗读会读这个列表。点击可静音。",
        "このリストを読み上げます。クリックするとミュートします。",
    ),
    "Text-to-speech doesn't read this list. Click to read it aloud.": (
        "语音朗读不会读这个列表。点击可开启朗读。",
        "このリストは読み上げません。クリックすると読み上げます。",
    ),
    "When the TTS language is Auto-detect or matches \"Translate to\" (Translation section), every chat "
    "message is read translated into that language. Otherwise messages are read in their original language.": (
        "当 TTS 语言为自动检测，或与「翻译为」语言（翻译设置）相同时，所有弹幕都会翻译成该语言后朗读；否则按原文语言朗读。",
        "TTS の言語が自動検出、または「翻訳先」（翻訳セクション）と同じ場合、すべてのチャットをその言語に翻訳して読み上げます。異なる場合は元の言語で読み上げます。",
    ),
    "⚠️ Not active: set the TTS language to Auto-detect or to the same language as \"Translate to\" ({target}).": (
        "⚠️ 未生效：请把 TTS 语言设为自动检测，或与「翻译为」相同的语言（{target}）。",
        "⚠️ 無効：TTS の言語を自動検出、または「翻訳先」と同じ言語（{target}）にしてください。",
    ),
    "Don't read usernames": ("不朗读用户名", "ユーザー名を読み上げない"),
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
    "🙈 Hide": ("🙈 隐藏", "🙈 非表示"),
    "👁️ Show": ("👁️ 显示", "👁️ 表示"),
    "Max messages displayed": ("最多显示消息数", "最大表示メッセージ数"),
    "🗑️ Clear chat history": ("🗑️ 清空弹幕记录", "🗑️ チャット履歴を消去"),
    # Option labels from src modules
    "Auto-detect": ("自动检测", "自動検出"),
    "Chinese (中文)": ("中文", "中国語（中文）"),
    "Japanese (日本語)": ("日语（日本語）", "日本語"),
    "Chinese (简体中文)": ("简体中文", "中国語（简体中文）"),
    "Chinese (繁體中文)": ("繁體中文", "中国語（繁體中文）"),
    "Korean (한국어)": ("韩语（한국어）", "韓国語（한국어）"),
    "English": ("英语（English）", "英語（English）"),
    "Auto (pinyin for Chinese, furigana for Japanese)": (
        "自动（中文用拼音，日语用振假名）",
        "自動（中国語はピンイン、日本語は振り仮名）",
    ),
    "Pinyin": ("拼音", "ピンイン"),
    "Furigana": ("振假名", "振り仮名"),
    "Pinyin + Furigana": ("拼音 + 振假名", "ピンイン + 振り仮名"),
    "Off": ("关闭", "オフ"),
    # ── Chat rendering ───────────────────────────────────────────────────────
    "Block this user (hides their messages; saved permanently)": (
        "屏蔽该用户（隐藏其消息，永久保存）", "このユーザーをブロック（メッセージを非表示にし、永続的に保存）"),
    "Read this message aloud": ("朗读这条消息", "このメッセージを読み上げる"),
    "translating…": ("翻译中…", "翻訳中…"),
    # ── Tabs ─────────────────────────────────────────────────────────────────
    "💬 Chat": ("💬 弹幕", "💬 チャット"),
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
        "等待频道开播，然后自动读取弹幕。", "チャンネルの配信開始を待ち、自動でチャットを読み込みます。"),
    "👀 Watching {name} — not live yet": ("👀 正在监视 {name}——尚未开播", "👀 {name} を監視中 — まだ配信していません"),
    "👀 Watching {name} — stream scheduled: {title}": (
        "👀 正在监视 {name}——已预定直播：{title}", "👀 {name} を監視中 — 配信予定: {title}"),
    "Checks every {s}s · last checked {time}": ("每 {s} 秒检查一次 · 上次检查 {time}", "{s} 秒ごとに確認 · 最終確認 {time}"),
    "Live now: {title}": ("正在直播：{title}", "配信中: {title}"),
    "{channel} is live — reading chat": ("{channel} 开播了——正在读取弹幕", "{channel} が配信開始 — チャットを読み込み中"),
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
    "Chat": ("弹幕", "チャット"),
    "Gifts & Super Chats": ("礼物和醒目留言", "ギフトとスーパーチャット"),
    "{n} to thank": ("{n} 条待感谢", "未お礼 {n} 件"),
    "{n} total": ("共 {n} 条", "合計 {n} 件"),
    "🙏 Mark all thanked": ("🙏 全部标为已感谢", "🙏 すべてお礼済みにする"),
    "No gifts or Super Chats yet.": ("还没有礼物或醒目留言。", "まだギフトやスーパーチャットはありません。"),
    "Joins": ("进场", "入室"),
    "No one has joined yet.": ("还没有人进场。", "まだ誰も入室していません。"),
    "Show or hide viewers entering the room.": ("显示或隐藏进场的观众。", "入室した視聴者を表示／非表示にします。"),
    "Layout": ("布局", "レイアウト"),
    "◫ 2 columns": ("◫ 2 栏", "◫ 2 列"),
    "☰ 1 column": ("☰ 1 栏", "☰ 1 列"),
    "Use ▲ ▼ on each list to change its position, and ◀ ▶ to move it to the other column.": (
        "用各列表上的 ▲ ▼ 调整位置，◀ ▶ 移到另一栏。",
        "各リストの ▲ ▼ で位置を変更し、◀ ▶ でもう一方の列へ移動します。"),
    "Move up": ("上移", "上へ移動"),
    "Move down": ("下移", "下へ移動"),
    "Move to the left column": ("移到左栏", "左の列へ移動"),
    "Move to the right column": ("移到右栏", "右の列へ移動"),
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
        "需要直播 URL 或视频 ID 才能显示状态（弹幕 ID 不包含视频信息）。",
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
    "Chat stats will appear once messages arrive.": ("收到消息后将显示弹幕统计。", "メッセージが届くとチャット統計が表示されます。"),
    "🛡️ Filtered / blocked messages": ("🛡️ 已过滤 / 屏蔽的消息", "🛡️ フィルター / ブロックされたメッセージ"),
    "No blocked messages.": ("没有被屏蔽的消息。", "ブロックされたメッセージはありません。"),
    # ── Filters tab ──────────────────────────────────────────────────────────
    "🛡️ Chat Filters": ("🛡️ 弹幕过滤", "🛡️ チャットフィルター"),
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
    "🖥️ Chat Overlay": ("🖥️ 弹幕叠加层", "🖥️ チャットオーバーレイ"),
    "Use the overlay URL in OBS as a **Browser Source** to show a transparent chat on stream.": (
        "在 OBS 中将叠加层 URL 添加为**浏览器来源**，即可在直播画面显示透明弹幕框。",
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
        "只显示部分网站的弹幕——例如每个网站一个浏览器源。会在叠加层网址中加入 ?site=…；全部选中（或留空）则显示所有网站。",
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
    "This overlay URL uses the address you opened the dashboard with ({host}), but the overlay only accepts connections from this computer. Set OVERLAY_HOST=0.0.0.0 in .env and restart so OBS can load it.": (
        "此叠加层网址使用你打开仪表板时的地址（{host}），但叠加层仅接受本机连接。请在 .env 中设置 OVERLAY_HOST=0.0.0.0 并重启，OBS 才能加载。",
        "このオーバーレイ URL はダッシュボードを開いたアドレス（{host}）を使いますが、オーバーレイはこのコンピューターからの接続のみ受け付けます。OBS で読み込めるよう .env に OVERLAY_HOST=0.0.0.0 を設定して再起動してください。",
    ),
    "Couldn't start the chat overlay on port {port}: {err}": (
        "无法在端口 {port} 启动弹幕叠加层：{err}",
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
        "醒目留言、礼物和会员固定在叠加层顶部，与普通弹幕分开，弹幕再多也不会把它们挤走。设为 0 则隐藏。",
        "スーパーチャット・ギフト・メンバーシップはオーバーレイ上部に固定され、通常チャットとは別なので、チャットが多くても押し出されません。0 で非表示。",
    ),
    "Recent Chat Preview (last {n} messages)": ("最近弹幕预览（最后 {n} 条）", "最近のチャットプレビュー（最新 {n} 件）"),
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
    "Then click 📋 Paste from clipboard — the site is detected and the cookies are checked right away.": (
        "在你自己的浏览器中，用 \"Get cookies.txt LOCALLY\" 或 \"Cookie-Editor\" 等扩展导出该网站的 Cookie"
        "（导出为 JSON 或 Netscape 格式），或从开发者工具复制 Cookie 请求头（F12 → 网络 → 任意发往该网站的请求）。"
        "然后点击 📋 从剪贴板粘贴——会自动识别网站并立即检查 Cookie。",
        "自分のブラウザで \"Get cookies.txt LOCALLY\" や \"Cookie-Editor\" などの拡張機能を使ってサイトの Cookie を"
        "エクスポートするか（JSON または Netscape 形式）、開発者ツールから Cookie リクエストヘッダーをコピーしてください"
        "（F12 → ネットワーク → サイトへの任意のリクエスト）。次に 📋 クリップボードから貼り付け をクリックすると、"
        "サイトが自動で判別され、Cookie がすぐに確認されます。",
    ),
    "📋 Paste from clipboard": ("📋 从剪贴板粘贴", "📋 クリップボードから貼り付け"),
    "🧹 Clear box": ("🧹 清空输入框", "🧹 入力欄をクリア"),
    "This browser didn't allow reading the clipboard. Click in the box below and press "
    "Ctrl+V instead.": (
        "此浏览器不允许读取剪贴板。请点击下方输入框，然后按 Ctrl+V。",
        "このブラウザではクリップボードを読み取れませんでした。下の入力欄をクリックして Ctrl+V を押してください。",
    ),
    "Picked automatically when the pasted cookies show which site they are for.": (
        "当粘贴的 Cookie 能看出属于哪个网站时，会自动选择。",
        "貼り付けた Cookie からサイトが分かる場合は自動で選ばれます。",
    ),
    "🔑 Your saved logins": ("🔑 已保存的登录", "🔑 保存済みのログイン"),
    "— not logged in": ("— 未登录", "— 未ログイン"),
    "logged in": ("已登录", "ログイン済み"),
    "❔ saved (couldn't check)": ("❔ 已保存（无法检查）", "❔ 保存済み（確認できません）"),
    "⚠️ expired": ("⚠️ 已过期", "⚠️ 期限切れ"),
    "🗑️ Delete": ("🗑️ 删除", "🗑️ 削除"),
    "Forget your login cookies for this site (also removed from this browser).": (
        "删除你在该网站的登录 Cookie（也会从此浏览器中移除）。",
        "このサイトのログイン Cookie を削除します（このブラウザからも削除されます）。",
    ),
    "🗑️ Delete all logins": ("🗑️ 删除所有登录", "🗑️ すべてのログインを削除"),
    "Deleted all your logins.": ("已删除你的所有登录。", "すべてのログインを削除しました。"),
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
        "未登录——只能查看弹幕。要发送消息，请在 🍪 Cookie 标签页导入 Cookie。",
        "未ログイン — チャットは閲覧のみです。送信するには 🍪 Cookie タブで Cookie をインポートしてください。",
    ),
    "All cookie names (values masked)": ("所有 Cookie 名称（值已隐藏）", "すべての Cookie 名（値は伏せ字）"),
    "A live stream URL or video ID, or a channel link like https://www.youtube.com/@name — a channel's chat is picked up automatically when it goes live.": (
        '直播链接或视频 ID，或频道链接（如 https://www.youtube.com/@name）— 频道开播时会自动读取其弹幕。',
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
        '现在可以发送 YouTube 弹幕了。',
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
        "此 Google 账号拥有多个 YouTube 频道——选择以哪个频道发送弹幕消息。",
        "この Google アカウントには複数の YouTube チャンネルがあります。チャットを送信するチャンネルを選んでください。",
    ),
    "🚪 Clear login": ("🚪 清除登录", "🚪 ログインを解除"),
    "Forget your login cookies for this site (also removed from this browser). Chat keeps working read-only.": (
        "清除你在此网站的登录 Cookie（也会从此浏览器删除）。弹幕仍可只读查看。",
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
        '🔑 未登录 — 弹幕为只读。在 🍪 Cookies 标签页导入 Cookie 后即可发送。',
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
