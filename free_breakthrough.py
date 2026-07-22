
"""
free突破: ChatGPT 邮箱注册 → Session 提取 → Agent Identity → sub2api 导入

复用 uc_signup.py 的 SignupBot 浏览器逻辑，仅新增:
  1. 邮箱注册流程 (跳过手机号 SMS)
  2. Session 提取 (/api/auth/session)
  3. Agent Identity 转换 + sub2api 导入

用法:
  python free_breakthrough.py --email "user@domain.com" --sub2api-base-url "https://..." --sub2api-admin-key "admin-xxx"
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import struct
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    # ── 1. 先解析命令行参数（import uc_signup 之前，确保环境变量就绪）──
    parser = argparse.ArgumentParser(description="free突破: ChatGPT 邮箱注册 → Agent Identity 导入")
    parser.add_argument("--email", required=True, help="注册邮箱")
    parser.add_argument("--sub2api-base-url", default="", help="sub2api 地址")
    parser.add_argument("--sub2api-admin-key", default="", help="sub2api 管理秘钥")
    parser.add_argument("--proxy", default="", help="代理地址")
    parser.add_argument("--chrome-binary", default="", help="Chrome 路径")
    parser.add_argument("--chrome-version", default="", help="Chrome 主版本号")
    parser.add_argument("--password", default="", help="注册密码")
    parser.add_argument("--name", default="", help="注册姓名")
    parser.add_argument("--age", default="", help="注册年龄")
    args = parser.parse_args()

    # ── 2. 设置环境变量（server.py 子进程已设好，这里处理 CLI 覆盖）──
    for env_key, arg_val in (
        ("SIGNUP_PASSWORD", args.password),
        ("SIGNUP_NAME", args.name),
        ("SIGNUP_AGE", args.age),
    ):
        if arg_val:
            os.environ[env_key] = arg_val
    os.environ.setdefault("SIGNUP_PASSWORD", "FuckOAI123456!")

    if args.proxy:
        os.environ["UC_SIGNUP_PROXY"] = args.proxy
        os.environ["BROWSER_PROXY"] = args.proxy
    if args.chrome_binary:
        os.environ["UC_SIGNUP_CHROME_BINARY"] = args.chrome_binary
    if args.chrome_version:
        os.environ["UC_SIGNUP_CHROME_VERSION"] = args.chrome_version

    # ── 3. 现在导入 uc_signup（模块级变量从 os.environ 读取）──
    import uc_signup
    from uc_signup import SignupBot, log, StepError, FatalError, MAX_RETRIES, api

    # ── 4. 导入 Agent Identity 依赖 ──
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except ImportError:
        print("ERROR: pip install cryptography", file=sys.stderr)
        return 1

    try:
        from curl_cffi import requests as cffi_requests
    except ImportError:
        print("ERROR: pip install curl_cffi", file=sys.stderr)
        return 1

    # ── 5. 准备运行时全局变量 ──
    # 确保 uc_signup 模块全局变量与 os.environ 一致
    uc_signup.PW = os.environ.get("SIGNUP_PASSWORD", uc_signup.PW)
    uc_signup.NAME = os.environ.get("SIGNUP_NAME", uc_signup.NAME)
    uc_signup.AGE = os.environ.get("SIGNUP_AGE", uc_signup.AGE)
    if args.proxy:
        uc_signup.PROXY = args.proxy
    if args.chrome_binary:
        uc_signup.CHROME_BINARY = args.chrome_binary
    if args.chrome_version:
        try:
            uc_signup.CHROME_VERSION = int(args.chrome_version)
        except ValueError:
            pass

    # ── 6. Agent Identity 核心函数 ──
    AGENT_REGISTER_URL = "https://auth.openai.com/api/accounts/v1/agent/register"

    def b64url_decode(data: str) -> bytes:
        data = data.replace("-", "+").replace("_", "/")
        padding = 4 - len(data) % 4
        if padding != 4:
            data += "=" * padding
        return base64.b64decode(data)

    def parse_jwt(token: str) -> dict:
        parts = token.strip().split(".")
        if len(parts) < 2:
            raise ValueError("不是合法 JWT")
        return json.loads(b64url_decode(parts[1]))

    def extract_account(claims: dict) -> dict:
        oa = claims.get("https://api.openai.com/auth", {})
        info = {
            "account_id": oa.get("chatgpt_account_id", ""),
            "chatgpt_user_id": oa.get("chatgpt_user_id", ""),
            "email": claims.get("email", ""),
            "plan_type": oa.get("chatgpt_plan_type", ""),
        }
        if not info["account_id"]:
            raise ValueError("JWT 缺少 chatgpt_account_id")
        if not info["chatgpt_user_id"]:
            raise ValueError("JWT 缺少 chatgpt_user_id")
        return info

    def generate_keypair() -> tuple:
        pk = ed25519.Ed25519PrivateKey.generate()
        pub = pk.public_key().public_bytes_raw()
        der = pk.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        return pk, pub, base64.b64encode(der).decode()

    def build_ssh_public_key(pubkey_bytes: bytes) -> str:
        key_type = b"ssh-ed25519"
        blob = struct.pack(">I", len(key_type)) + key_type + struct.pack(">I", len(pubkey_bytes)) + pubkey_bytes
        return "ssh-ed25519 " + base64.b64encode(blob).decode()

    def get_auth_session():
        s = cffi_requests.Session()
        s.impersonate = "chrome120"
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        s.get("https://auth.openai.com/", headers={"User-Agent": ua}, timeout=30)
        return s

    def register_runtime(access_token: str, pubkey_ssh: str) -> str:
        s = get_auth_session()
        abom = {
            "agent_version": "1.0.0",
            "agent_harness_id": str(uuid.uuid4()),
            "running_location": "local",
        }
        body = {"agent_public_key": pubkey_ssh, "abom": abom}
        resp = s.post(
            AGENT_REGISTER_URL,
            json=body,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=30,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        rid = data.get("agent_runtime_id") or data.get("agentRuntimeId") or data.get("id")
        if not rid:
            raise RuntimeError(f"响应无 agent_runtime_id: {json.dumps(data, indent=2)[:500]}")
        return rid

    def build_auth(account: dict, runtime_id: str, privkey_b64: str) -> dict:
        ai = {
            "agent_runtime_id": runtime_id,
            "agent_private_key": privkey_b64,
            "account_id": account["account_id"],
            "chatgpt_user_id": account["chatgpt_user_id"],
        }
        if account.get("email"):
            ai["email"] = account["email"]
        if account.get("plan_type"):
            ai["plan_type"] = account["plan_type"]
        return {"auth_mode": "agentIdentity", "agent_identity": ai}

    def import_sub2api(auth: dict, base_url: str, api_key: str) -> bool:
        content = json.dumps(auth, ensure_ascii=False)
        body = {
            "content": content,
            "concurrency": 2,
            "priority": 3,
            "auto_pause_on_expired": True,
        }
        url = base_url.rstrip("/") + "/api/v1/admin/accounts/import/codex-session"
        resp = cffi_requests.post(
            url,
            json=body,
            headers={"x-api-key": api_key, "Content-Type": "application/json", "Accept": "application/json"},
            timeout=30,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"sub2api HTTP {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        code = data.get("code", -1)
        if code != 0:
            raise RuntimeError(f"sub2api 返回错误: {data.get('message', resp.text[:300])}")
        result = data.get("data", {})
        created = result.get("created", 0)
        updated = result.get("updated", 0)
        log(f"sub2api 导入成功: created={created} updated={updated}")
        return True

    def do_agent_identity(access_token: str, base_url: str, api_key: str) -> dict:
        log("解析 JWT...")
        claims = parse_jwt(access_token)
        account = extract_account(claims)
        log(f"  account_id = {account['account_id']}")
        log(f"  plan_type  = {account.get('plan_type', 'N/A')}")

        log("生成 Ed25519 密钥对...")
        pk, pubkey_bytes, privkey_b64 = generate_keypair()
        pubkey_ssh = build_ssh_public_key(pubkey_bytes)

        log("注册 Agent Runtime...")
        runtime_id = register_runtime(access_token, pubkey_ssh)
        log(f"  agent_runtime_id = {runtime_id}")

        log("构建 auth.json...")
        auth = build_auth(account, runtime_id, privkey_b64)

        export_dir = ROOT / "export"
        export_dir.mkdir(parents=True, exist_ok=True)
        auth_path = export_dir / f"auth_{account['account_id']}.json"
        with open(auth_path, "w", encoding="utf-8") as f:
            json.dump(auth, f, indent=2, ensure_ascii=False)
        log(f"  auth.json: {auth_path}")

        log(f"导入 sub2api: {base_url}")
        import_sub2api(auth, base_url, api_key)
        return auth

    # ── 7. 邮箱注册 + Session 提取 ──
    def wait_for_email_login(driver, timeout: int = 600) -> bool:
        log("等待登录完成...")
        start = time.time()
        while time.time() - start < timeout:
            try:
                url = driver.current_url or ""
                if "chatgpt.com" in url and "/auth/" not in url and "login" not in url.lower():
                    log("登录完成，已进入主页")
                    time.sleep(3)
                    return True
                if "contact-verification" in url or "/auth/phone" in url:
                    log("检测到手机验证页，直接跳到主页...", "warn")
                    driver.get("https://chatgpt.com/")
                    time.sleep(8)
                    continue
            except Exception:
                pass
            time.sleep(2)
        return False

    def extract_session(driver) -> dict:
        log("提取 session...")
        for _ in range(15):
            try:
                result = driver.execute_script("""
                    const xhr = new XMLHttpRequest();
                    xhr.open('GET', '/api/auth/session', false);
                    xhr.send();
                    if (xhr.status === 200) return xhr.responseText;
                    return '';
                """)
                if result and len(result) > 20:
                    data = json.loads(result)
                    if data.get("accessToken") or data.get("user"):
                        log("session 提取成功")
                        return data
            except Exception:
                pass
            time.sleep(1)
        raise Exception("提取 session 失败")

    class FreeBreakthroughBot(SignupBot):
        """继承 SignupBot，复用所有浏览器操作；仅新增邮箱注册 + session 提取"""

        def register_with_email(self) -> dict:
            log(f"邮箱注册: {self.d.title}")

            self._step("Cookie", lambda: self.click_optional("Accept all", wait_seconds=3))

            # 切到邮箱登录（避免 Google OAuth 分流）
            self.click_optional("Continue with email", wait_seconds=3)
            self.click_optional("Use email", wait_seconds=3)

            log(f"填写邮箱: {self.email}")
            self._step("邮箱", lambda: (
                self.fill_any(["input[type=email]", "input[name=email]", "input[name=username]"], self.email),
                self.click("Continue"),
            ))

            code = self.poll_email(self.email)
            if not code:
                raise FatalError("邮箱验证码超时")
            log(f"邮箱码: {code}")

            self._step("邮箱码", lambda: (
                self.fill("input[name=code]", code),
                self.click("Continue"),
            ))

            log("填密码")
            try:
                self._step("填密码", lambda: (
                    self.fill("input[name=new-password]", uc_signup.PW),
                    self.click("Continue"),
                ))
            except Exception:
                log("密码步骤跳过或已完成")

            log("姓名年龄")
            try:
                self._step("姓名年龄", lambda: (
                    self.fill("input[name=name]", uc_signup.NAME),
                    self.fill_birth_year(uc_signup.AGE),
                    self.click("Finish creating account"),
                ))
            except Exception:
                try:
                    self.click("Continue")
                except Exception:
                    pass

            time.sleep(8)

            if not wait_for_email_login(self.d):
                raise FatalError("登录超时（可能跳到手机验证或异常页面）")

            log("注册完成，提取 session")
            return extract_session(self.d)

        def run(self) -> dict:
            log("=" * 55)
            log("free突破: ChatGPT 邮箱注册 → Agent Identity")
            log("=" * 55)

            self.launch()
            self.d.get("https://chatgpt.com/auth/login?intent=signup")
            time.sleep(10)
            log(f"打开注册页: {self.d.title}")

            self.email = self.prepare_email()
            return self.register_with_email()

    # ── 8. 执行 ──
    sub2api_url = args.sub2api_base_url.strip()
    sub2api_key = args.sub2api_admin_key.strip()

    bot = None
    try:
        bot = FreeBreakthroughBot(email=args.email)
        session = bot.run()
        access_token = session.get("accessToken") or ""
        if not access_token:
            raise Exception("session 无 accessToken")

        if sub2api_url and sub2api_key:
            do_agent_identity(access_token, sub2api_url, sub2api_key)
        else:
            log("WARN: 未配置 sub2api，跳过导入", "warn")
            claims = parse_jwt(access_token)
            account = extract_account(claims)
            pk, pub, privkey_b64 = generate_keypair()
            pubkey_ssh = build_ssh_public_key(pub)
            rid = register_runtime(access_token, pubkey_ssh)
            auth = build_auth(account, rid, privkey_b64)
            export_dir = ROOT / "export"
            export_dir.mkdir(parents=True, exist_ok=True)
            auth_path = export_dir / f"auth_{account['account_id']}.json"
            with open(auth_path, "w", encoding="utf-8") as f:
                json.dump(auth, f, indent=2, ensure_ascii=False)
            log(f"auth.json: {auth_path}")

        log("全部完成!")
        return 0
    except Exception as e:
        log(f"失败: {e}", "error")
        return 1
    finally:
        if bot:
            try:
                bot.close_browser()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
