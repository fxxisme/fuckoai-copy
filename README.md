# fuckoai Linux

Linux 容器版注册控制面板。

## 功能

- Web 控制面板：`/ui`
- 临时邮箱队列生成和验证码读取
- 购买组可视化配置，支持 HeroSMS 和 SMSBower 双供应商，分别保存到 `data/purchase_config.json` 和 `data/purchase_config_bower.json`
- Linux 图形浏览器自动注册入口，通过 Xvfb、x11vnc、noVNC 查看

## 文件结构

```text
server.py                       # 本地 API 和 Web 控制面板服务
control_panel.html              # Linux Web 控制面板
uc_signup.py                    # Linux 浏览器自动注册脚本
config.example.json             # 应用配置模板
config.json                     # 本地应用配置，不进入 git
data/purchase_config.json       # HeroSMS 购买配置
data/purchase_config_bower.json # SMSBower 购买配置
data/catalog_cache.json         # HeroSMS 国家/运营商缓存
data/catalog_cache_bower.json   # SMSBower 国家/运营商缓存
Dockerfile                      # Linux 容器镜像
docker-compose.yml              # fuckoai 服务
scripts/start_linux_vnc.sh      # Xvfb/VNC/noVNC + server 启动脚本
```

运行数据放在 `data/`，`.env`、`config.json` 和 `data/` 不进入 git，也不进入 Docker build context。

## 配置

`.env` 只放管理员密码：

```env
ADMIN_PASSWORD=你的控制面板管理员密码
```

`ADMIN_PASSWORD` 可选；设置后访问 `/ui` 需要登录。

其他设置写在本地 `config.json`，也可以在控制面板“设置”页保存。首次部署可以从模板创建：

```bash
cp config.example.json config.json
```

模板已包含 HeroSMS / SMSBower 接口地址、注册资料默认值和浏览器参数；接口密钥、临时邮箱、CPA 等用户配置默认为空。

### OAuth 导入目标

注册完成后由 `OAUTH_TARGET` 选择 OAuth 凭证导入目标：

| 配置值 | 导入目标 | 必填配置 |
| --- | --- | --- |
| `cpa`（默认） | CPA / CLIProxyAPI | `CPA_BASE_URL`、`CPA_MANAGEMENT_KEY` |
| `sub2api` | sub2api OpenAI OAuth 账号（`platform=openai`、`type=oauth`） | `SUB2API_BASE_URL`、`SUB2API_ADMIN_API_KEY` |

使用 sub2api 时保留以下默认值即可，按实际调度需求调整并发和优先级：

```json
{
  "OAUTH_TARGET": "sub2api",
  "SUB2API_BASE_URL": "https://sub2api.example.com",
  "SUB2API_ADMIN_API_KEY": "",
  "SUB2API_REDIRECT_URI": "http://127.0.0.1:56121/callback",
  "SUB2API_TIMEOUT_SEC": "300",
  "SUB2API_CONCURRENCY": "10",
  "SUB2API_PRIORITY": "1"
}
```

`SUB2API_REDIRECT_URI` 是浏览器 OAuth 完成后的本机回调 URL；不需要额外启动 HTTP 服务，但三个位置必须保持一致：生成授权 URL、OpenAI 最终跳转地址、提交给 sub2api 的 OAuth 回调。容器使用 `network_mode: host`，默认 `127.0.0.1:56121` 指向运行容器的宿主机网络命名空间。


### 短信供应商

支持两套收码供应商，协议兼容（均为 `handler_api.php` 体系），各自独立配置接口地址和密钥：

| 供应商 | 接口地址 | 密钥字段 | 购买配置文件 |
| --- | --- | --- | --- |
| HeroSMS | `HERO_SMS_API_URL` | `HERO_SMS_API_KEY` | `data/purchase_config.json` |
| SMSBower | `SMSBOWER_API_URL` | `SMSBOWER_API_KEY` | `data/purchase_config_bower.json` |

`SMS_PROVIDER` 决定默认使用哪个供应商（`hero` 或 `bower`，默认 `hero`）。可在控制面板“设置”页修改，也可在购买配置页通过 tab 切换查看/编辑对应供应商的购买组。

## 购买配置

购买参数统一维护在控制面板“设置”页，保存后写入对应供应商的购买配置文件（HeroSMS 写入 `data/purchase_config.json`，SMSBower 写入 `data/purchase_config_bower.json`）。这些文件位于 `data/`，不会进入 git。

购买配置页提供 HeroSMS / SMSBower 两个 tab，切换后只显示并轮询当前选中供应商的购买组和国家/运营商缓存，互不干扰。

默认仓库不提供具体国家、运营商、价格等购买组。首次使用前需要在控制面板新增购买组。

服务端会按当前选中供应商已启用购买组顺序尝试买号，失败时自动试下一组；只在当前供应商内轮询，不会跨供应商混用。

## 启动

```bash
docker compose up -d --build fuckoai
```

访问：

```text
http://127.0.0.1:3030/ui
```

查看容器：

```bash
docker compose ps
docker logs --tail 80 fuckoai
```

## Linux 本地运行

```bash
python3 server.py
```

如果需要浏览器画面：

```bash
./scripts/start_linux_vnc.sh
```

## 邮箱队列

控制面板只保留随机前缀模式。填写邮箱后缀域名、数量和可选邮箱前缀后，会生成：

```text
随机字符@example.com
自定义前缀随机字符@example.com
```

生成后的队列仍可手动编辑，一行一个邮箱。

## API

基础地址：

```text
http://127.0.0.1:3030/api
```

常用接口：

- `GET /api/health`
- `POST /api/purchase`
- `GET /api/purchase-settings`
- `POST /api/purchase-settings`
- `GET /api/sms-providers`
- `POST /api/sms-providers/current`
- `GET /api/purchase-catalog/countries`
- `POST /api/purchase-catalog/countries/refresh`
- `GET /api/purchase-catalog/operators`
- `GET /api/email-queue`
- `POST /api/email-queue`
- `POST /api/email-queue/generate`
- `GET /api/uc-signup/status`
- `POST /api/uc-signup/start`
- `POST /api/uc-signup/stop`
- `GET /api/uc-signup/logs`

以上涉及号码/购买的接口均支持 `?provider=hero|bower` query 参数指定供应商，省略时使用当前默认（`SMS_PROVIDER`）。`POST /api/purchase-settings` 支持在 body 中传 `provider` 字段指定要保存的供应商配置。

## 致谢

感谢 linux.do 社区提供的交流、经验和启发。
