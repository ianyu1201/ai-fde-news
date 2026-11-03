> 2026-10-01：新增协同办公与访谈栏目，日更迁移到“资讯站每日更新与内容筛选”。栏目规则见 content-tracks.json；协同办公仅基线以后新信息，访谈按片段亮点和实际可读范围筛选。

> 当前版本：全宽适配；默认浏览 2026 年 7 月起资讯。网页不提供收藏、推荐阅读、详情与原文 MD 下载。下文涉及 extract 的命令仅是保留的本地工具，不是网站功能。持续选题偏好见 reader-profile.json、book-discovery.json 和 EDITORIAL.md。

# AI Native / FDE 观察

给自己看的每日资讯。Mac 本地采集，Codex 使用现有额度筛选和整理，导出独立静态页面。没有模型 API、服务器端接口或付费采集。

## 本轮边界

- 2026-10-01 经用户授权发布：[线上资讯](https://ianyu.art/ai-news/)。
- 资讯独立维护；个人网站构建时从本站 `dist/ai-news/` 同步最新发布快照。
- 参考 AIHOT 固定提交 `885b736dc0fd3ef3d4c9c70af2bc3a981a99ff38` 的独立复评、事件关系和热度规则；上游 MIT 许可与归属见 `reference/AIHOT/LICENSE`、`reference/AIHOT/NOTICE`。数据采集与后端独立实现；页面配色和日期时间线参考上游源码，许可见 THIRD_PARTY_NOTICES.md，没有使用原品牌。
- Codex 整理与采集是两个步骤。刷新网页或单独执行采集脚本不会生成模型摘要。

## 手动使用

采集和静态页面需要 macOS 自带 Python 3.9+。向量候选召回另外需要 Node.js 22 与本项目锁定的 npm 依赖；它们不影响采集、静态页面或词面降级。

```sh
cd '/Users/yusiyuan/Documents/资料/AI-FDE资讯站'
python3 news.py collect
# 在 Codex 中要求：读取 EDITORIAL.md，评审 .local/pending.json 并更新本地资讯页。
# Codex 生成 .local/reviews-YYYY-MM-DD.json 后执行：
python3 news.py review .local/reviews-YYYY-MM-DD.json
python3 news.py build
python3 news.py verify
python3 news.py serve
```

打开 `http://127.0.0.1:8765/ai-news/`。也可直接打开 `dist/ai-news/index.html`，建议使用本地预览核对页面。

双击 `打开资讯.command` 会构建并启动本机预览。启动器检查服务版本和 Markdown 下载能力，只自动替换同一项目目录的旧预览进程；遇到其他程序占用端口会说明原因。不会触发模型整理。需要立即更新时，向本 Codex 任务发送“更新 AI Native / FDE 资讯站，并生成本地页面”。

## 原文 Markdown 伴读

对单篇公开文章运行 `python3 news.py extract 文章ID`。成功提取后，先人工检查 `.local/reading/文章ID.md` 的首尾段落、结构和有无缺页，再运行 `python3 news.py approve-reading 文章ID` 与 `python3 news.py build`。本机预览页才会显示下载入口。仅摘要、提取失败或尚未核对时不提供“全文”下载。私人文件只在 `.local/reading/`，本机 `127.0.0.1` 的受控路由按文章 ID 返回，不写入 `dist/`。

## 评分、事件和热度

按评审角色生成尚未完成的候选批次，默认最多 30 条、每条摘要最多 900 字符，以控制每日用量：

```sh
python3 news.py score-batch --reviewer A > .local/score-A.json
python3 news.py score-batch --reviewer B > .local/score-B.json
```

把 A、B 两份输入分别交给互不读取对方结果的 Codex 评审上下文。每份输出保留对应 reviewer 和标准版本/哈希，另加不同 contextId、实际 model，并为每个条目给出 id、fingerprint、整数分数与理由；分别 `score-import`。已完成该 reviewer 的文章会跳过；两份真实、标准一致、材料指纹一致且上下文不同的回执才构成独立双评。编辑核查通过后，只有真实独立A/B双评均分≥75分才能公开发布；待评与低分材料留在本地。75分是用户确认的门槛，高分仍须通过主题与证据核查。

`python3 news.py group-candidates > .local/group-candidates.json` 只比较最近14天精选和未确认关系，默认每篇最多建议2篇候选；可用 `--limit` 调整。`group-import` 接受确认的 SAME_OCCURRENCE、SAME_STORY、UNRELATED、ROUNDUP 关系。旧 eventKey 继续生效。页面保留各来源链接。热榜按 AIHOT 的 48 小时窗口、24 小时半衰期与 publisherId 去重，至少两个来源才入榜；只代表已监测信源。日级变化只与上一日级快照比较。

本地多语向量使用 Node 22、`@huggingface/transformers@4.3.0` 和 [Xenova/multilingual-e5-small](https://huggingface.co/Xenova/multilingual-e5-small) 的 int8 ONNX。固定模型提交 `761b726dd34fb83930e26aab4e9ac3899aa1fa78`，文件 `onnx/model_int8.onnx` 为 118,054,593 字节，SHA-256 `4d24e2bc01a447951524466ef533e52944bf48509e6552810bcee1a2711cb02c`；源模型 [intfloat/multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small) 标注 MIT 许可。依赖已锁定在 `package-lock.json`，本机私有权重已下载并核验，保存在 `.local/model-cache/`。重装时运行 `npm ci` 和 `node --use-env-proxy embed.mjs --prepare`，日常更新只用本地缓存。若模型不可用，`group-candidates` 明确标记词面降级。向量仅排序候选，短句样本出现过无关内容的高相似度，不能据此自动合并。

## 数据与可靠性

### 公开平台补源（试验阶段）

`rsshub-sources.json` 是微博、B站 RSSHub 路由的独立配置。示例账号均**未启用，也不是推荐信源**；先从账号主页核对主体与 UID，再填写 `id`、`publisherId`、`name`、`route` 并设 `enabled: true`。采集前设置 `RSSHUB_BASE_URL` 为可用的 RSSHub 实例根地址，运行原有 `python3 news.py collect` 即会进入同一待评审池。没设置实例地址时采 sources.json 中的七个海外RSS、三个国内RSS与三个官方节目目录；RSSHub 故障会记录在 `.local/collection.json`，不会清空旧内容。公共实例可能限流或失效；B站路由也可能被上游反爬拦截。RSSHub 是传输层，文章的原始链接、日期和账号身份仍需逐条核实。

`watch-pages.json` 是 changedetection.io 页面监测的候选清单，当前均未启用，URL 也须核实为确切官方更新页面。可按[官方 pip 安装说明](https://github.com/dgtlmoon/changedetection.io#installation)在本机独立环境安装并启动服务，然后在其界面添加同样 URL，设置本机 API key。启用已核实页面后运行 `CHANGEDETECTION_API_KEY=... python3 page_watches.py`。脚本仅访问 `127.0.0.1:5000`（可用 `CHANGEDETECTION_BASE_URL` 改本机端口），写入私有 `.local/watch-leads.json`；首次运行只建立基线，之后变化仅是核查线索，不会自动入库或冒充新发布日期。确认页面具体新增事项与官方日期后，仍按 `EDITORIAL.md` 评审。勿把 API key 写入配置文件。

公众号单列实验：[we-mp-rss](https://github.com/rachelos/we-mp-rss) 的部分采集方式依赖微信读书登录态或 Cookie；当前没有启用，也不读取个人登录态。先核实来源和服务要求，再决定是否为少量指定账号试运行。[yt-dlp](https://github.com/yt-dlp/yt-dlp) 只作为公开视频元数据、已有字幕的辅助核对工具；当前没有自动长视频下载、转录或导入。

- `sources.json`：7 个已试抓的首批 RSS / Atom 信源。中国官方内容和 FDE 专题由 Codex 浏览公开来源补充，当前没有自动公众号采集。
- `.local/catalog.json`：采集资料；`.local/pending.json`：近 14 天的待评审材料。
- `.local/editorial.json`：明确的入选和拒绝记录。来源内容有变更时需重审。
- `dist/ai-news/`：可以发布的 HTML 与 JSON，不含本地原文、路径、密钥。
- URL 去重自动完成；事件关系由 Codex 明确核对。当前模型与权重已在本机准备；如果模型运行失败，候选命令会明确退回词面相似度。
- 发布时间缺失或在未来的文章不能直接进入精选；旧资料不改成今日新闻。
- 失败信源不会清除已保存内容。无新增时不编造文章，也不重复整理未变化内容。
- 采集与写入串行锁定，JSON 原子替换。任务中断后可重新运行。
- 《智能》《Token经济》和阿里手册是长期发现线索；书籍商品页不作为每日资讯重复发布。作者新文章、公开访谈等须核实原文及日级日期后，按普通资讯评审。

## 定时更新

用户已确认每天北京时间 09:00，使用 Codex 桌面端本任务的定时自动化。运行条件是 Mac 开机联网，Codex 可运行且有剩余额度。是否补跑休眠期间错过的任务取决于应用调度，本项目不承诺唤醒或补跑。

脚本本身不会唤起模型，没有隐藏的 API 调用，也没有另装系统定时任务。每日工作范围与预算见 EDITORIAL.md。

## CloudBase 发布

2026-10-02 已将更新后的资讯发布到 https://ianyu.art/ai-news/，并在个人网站首页右上角加入入口。更新时先执行本项目 build 和 verify；个人网站构建脚本会自动从本项目 `dist/ai-news/` 复制最新 HTML 与 JSON，不再依赖手动同步旧的 `public/ai-news/` 副本。

个人网站执行 `npm run build:cloudbase`，确认 `cloudbase-out/ai-news/` 与本项目导出逐字节一致。本次使用 CloudBase CLI 3.8.4，以 `hosting deploy cloudbase-out --env-id ianyu-d7g4yno3a369dd74d --safe --verify` 发布整站，远端校验通过。不要使用 prune 或把资讯目录当整站根目录上传。

每日 09:00 的更新任务在资讯站 `build`、`verify` 后，自动构建个人网站的 `cloudbase-out/`，核对资讯文件一致性，再以 `--safe --verify --concurrency 5 --retry-count 5` 发布整站并检查线上内容。构建或发布失败时保留线上旧版本并报告；具体顺序见 `EDITORIAL.md`。

## 验证

`python3 -m unittest discover -s tests -v` 覆盖 RSS/Atom、链接去重、注入边界、无日期/未来日期、变更重审、事件归组和导出隐私。`python3 news.py verify` 检查当前产物。浏览器验收记录见 QA.md。

2026-10-06：新增国内RSS（量子位、InfoQ中文、少数派）与新可能实验室、红杉中国the prompt、张小珺商业访谈录的官方公开目录。每日09:00核查并发布合格内容；目录不是全平台视频实时监控。访谈按AI、商业、金融、市场、书籍等主题筛选，明确移除的单集禁止重入选。

2026-10-06最终确认：所有候选先进入私有数据库，核查并完成独立双评后，均分≥75分才进入网页。待评与低分记录只保留在.local数据库，不产生另一版本地网页。个人网页cloudbase-out与线上发布同一构建产物；verify拦截未评分、单评及低于门槛的公开数据。当前20条补评回执已完成，原67条中43条达标、24条低于75分。

评分分三条路线：协同办公用`score-batch --track office`（产品与行业动态），访谈/播客/视频对谈用`--track interviews`（片段洞见），其余用`--track depth`（默认，深度与实践）。全部保持独立A/B与均分≥75门槛；office与interviews回执必须提供对应五项分数并校验总和。访谈评价具体观点、取舍及决策启发，不要求完整工程方法或ROI实测；观点可追溯与效果验证分别表述。旧回执完整保留，启用前已上线访谈按固定指纹/回执清单保留历史评分并明确标注。详见EDITORIAL.md和content-tracks.json。
