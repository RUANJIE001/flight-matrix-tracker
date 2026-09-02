"""
notifier.py - 邮件与移动端即时推送通知模块
特性：
1. 采用专业美观的现代化响应式 HTML 邮件模板
2. 包含 3x3 价格矩阵热力表、跨平台比价清单与直达预订按钮
3. 支持 SSL/TLS SMTP 邮件推送 (QQ/163/Gmail/Outlook 等)
4. 支持 Bark / 飞书机器人 / ServerChan 微信即时通知 (可选)
"""
import smtplib
import httpx
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from typing import Dict, Any, Optional
from matrix import MatrixAnalysis

class Notifier:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.email_cfg = config.get("email", {})
        self.webhook_cfg = config.get("webhook", {})

    def send_notification(
        self,
        route_info: Dict[str, Any],
        analysis: MatrixAnalysis,
        force_send: bool = False
    ) -> bool:
        """
        触发通知：
        - 若 notify_on == 'always' 或 force_send 为 True，每次均发送
        - 若 notify_on == 'hit'，仅当存在票价 <= target_price 时发送
        """
        has_hit = analysis.global_min_offer and analysis.global_min_offer.price <= analysis.target_price
        should_send = force_send or (self.email_cfg.get("notify_on") == "always") or has_hit

        if not should_send:
            print("[Notifier] 当前价格未达到目标价，跳过邮件发送")
            return False

        subject = self._build_subject(route_info, analysis, has_hit)
        html_content = self._render_html_template(route_info, analysis, has_hit)

        success = True
        # 1. 发送邮件
        if self.email_cfg.get("enabled"):
            sender = self._clean_val(self.email_cfg.get("sender_email", ""))
            auth_code = self._clean_val(self.email_cfg.get("sender_auth_code", ""))
            recipient = self._clean_val(self.email_cfg.get("recipient_email", ""))

            # 校验是否依然为占位符
            if not sender or not auth_code or "your_email" in sender or "abcd efgh" in auth_code or sender == "false":
                print("=================================================================")
                print("❌ [Notifier] 严重提醒：检测到未配置真实的发信 Gmail 或应用密码！")
                print(f"   当前读取的发件账号: '{sender}'")
                print(f"   当前读取的收件账号: '{recipient}'")
                print("   👉 请前往 GitHub 仓库: Settings -> Secrets and variables -> Actions")
                print("   点击 'New repository secret' 补充配置：")
                print("   1. EMAIL_SENDER: 你的真实 Gmail 账号 (如 xxx@gmail.com)")
                print("   2. EMAIL_AUTH_CODE: 你的 16 位 Google 应用专用密码")
                print("   3. EMAIL_RECIPIENT: 接收提醒的目标邮箱")
                print("=================================================================")
                raise ValueError("未配置 GitHub Secrets (EMAIL_SENDER / EMAIL_AUTH_CODE)！")

            try:
                self._send_smtp_email(subject, html_content)
                print(f"[Notifier] 邮件已成功发送至 {recipient}")
            except Exception as e:
                print(f"[Notifier] ❌ 邮件发送失败: {e}")
                raise e

        # 2. 发送移动端 Webhook (若配置)
        self._send_webhooks(subject, analysis)

        return success

    def _build_subject(self, route_info: Dict[str, Any], analysis: MatrixAnalysis, has_hit: bool) -> str:
        origin = route_info.get("origin")
        dest = route_info.get("dest")
        if has_hit and analysis.global_min_offer:
            return f"🎉 降价提醒！{origin}⇄{dest} 机票最低 ¥{int(analysis.global_min_offer.price)} (达标!)"
        elif analysis.global_min_offer:
            return f"✈️ 机票价格监测报告：{origin}⇄{dest} 当前最低 ¥{int(analysis.global_min_offer.price)}"
        return f"✈️ 机票监控报告：{origin}⇄{dest}"

    def _render_html_template(self, route_info: Dict[str, Any], analysis: MatrixAnalysis, has_hit: bool) -> str:
        origin = route_info.get("origin")
        dest = route_info.get("dest")
        trip_type = "往返" if route_info.get("return_date") else "单程"
        nonstop = "仅直飞" if route_info.get("nonstop") else "含转机"
        target_price = int(route_info.get("target_price", 0))

        # 构建矩阵行 HTML
        matrix_rows_html = ""
        for (dep, ret), offers in analysis.results_map.items():
            ret_text = ret if ret else "单程"
            if offers:
                best = min(offers, key=lambda x: x.price)
                is_global = analysis.global_min_offer and best.price == analysis.global_min_offer.price
                is_hit_price = best.price <= target_price
                
                # 样式与徽章
                row_bg = "#f0f7ff" if is_global else "#ffffff"
                badge_html = ""
                if is_global:
                    badge_html += '<span style="background:#e6f4ea;color:#137333;padding:2px 6px;border-radius:4px;font-size:11px;font-weight:bold;margin-left:4px;">最低</span>'
                if is_hit_price:
                    badge_html += '<span style="background:#fce8e6;color:#c5221f;padding:2px 6px;border-radius:4px;font-size:11px;font-weight:bold;margin-left:4px;">达标</span>'

                links_list = []
                # 1. 抓取到的平台直达链接
                for o in offers:
                    if o.booking_url:
                        links_list.append(f'<a href="{o.booking_url}" target="_blank" style="margin-right:6px;font-size:11px;color:#1a73e8;text-decoration:none;font-weight:500;">🔗 {o.platform}</a>')
                
                # 2. 补充携程与天巡官方实时直达链接 (方便用户一键在浏览器/App中核验对比)
                ctrip_url = f"https://www.trip.com/flights/{origin.lower()}-to-{dest.lower()}/tickets-{origin.lower()}-{dest.lower()}?dcity={origin.lower()}&acity={dest.lower()}&ddate={dep}" + (f"&rdate={ret}&flighttype=rt" if ret else "&flighttype=ow")
                sky_dep = dep.replace("-", "")[2:]
                sky_ret = f"/{ret.replace('-', '')[2:]}" if ret else ""
                sky_url = f"https://www.skyscanner.net/transport/flights/{origin.lower()}/{dest.lower()}/{sky_dep}{sky_ret}/?currency=CNY"
                
                links_list.append(f'<a href="{ctrip_url}" target="_blank" style="margin-right:6px;font-size:11px;color:#ff6913;text-decoration:none;">📱 携程</a>')
                links_list.append(f'<a href="{sky_url}" target="_blank" style="font-size:11px;color:#00a698;text-decoration:none;">🌐 天巡</a>')
                links_html = "".join(links_list)

                matrix_rows_html += f"""
                <tr style="background:{row_bg};border-bottom:1px solid #e8eaed;">
                    <td style="padding:10px 8px;font-size:13px;color:#202124;">{dep}</td>
                    <td style="padding:10px 8px;font-size:13px;color:#5f6368;">{ret_text}</td>
                    <td style="padding:10px 8px;font-size:14px;font-weight:bold;color:#1a73e8;">¥{int(best.price)} {badge_html}</td>
                    <td style="padding:10px 8px;font-size:12px;color:#3c4043;">{best.platform}</td>
                    <td style="padding:10px 8px;">{links_html}</td>
                </tr>
                """
            else:
                matrix_rows_html += f"""
                <tr style="border-bottom:1px solid #e8eaed;">
                    <td style="padding:10px 8px;font-size:13px;color:#202124;">{dep}</td>
                    <td style="padding:10px 8px;font-size:13px;color:#5f6368;">{ret_text}</td>
                    <td style="padding:10px 8px;font-size:13px;color:#9aa0a6;">暂无报价</td>
                    <td style="padding:10px 8px;font-size:12px;color:#9aa0a6;">--</td>
                    <td style="padding:10px 8px;font-size:12px;color:#9aa0a6;">--</td>
                </tr>
                """

        # 智能省钱建议卡片
        savings_card_html = ""
        if analysis.best_recommendation:
            savings_card_html = f"""
            <div style="background:#e8f0fe;border-left:4px solid #1a73e8;padding:12px 16px;border-radius:4px;margin-bottom:20px;">
                <p style="margin:0;font-size:14px;color:#1a73e8;font-weight:500;">💡 <strong>弹性日期出行建议：</strong></p>
                <p style="margin:4px 0 0 0;font-size:13px;color:#202124;">{analysis.best_recommendation}</p>
            </div>
            """

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin:0;padding:20px;background:#f8f9fa;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
            <div style="max-width:640px;margin:0 auto;background:#ffffff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.1);overflow:hidden;padding:24px;">
                <div style="text-align:center;padding-bottom:16px;border-bottom:1px solid #e8eaed;">
                    <h1 style="margin:0;font-size:20px;color:#1a73e8;">✈️ 机票价格监测与弹性矩阵报告</h1>
                    <p style="margin:6px 0 0 0;font-size:13px;color:#5f6368;">{origin} ⇄ {dest} · {trip_type} · {nonstop}</p>
                </div>

                <div style="display:flex;justify-content:space-between;margin:16px 0;padding:12px 16px;background:#f1f3f4;border-radius:6px;font-size:13px;">
                    <div><strong>基准出发:</strong> {route_info.get('depart_date')}</div>
                    <div><strong>基准返程:</strong> {route_info.get('return_date', '无')}</div>
                    <div><strong>期望目标价:</strong> <span style="color:#d93025;font-weight:bold;">¥{target_price}</span></div>
                </div>

                {savings_card_html}

                <h3 style="font-size:15px;color:#202124;margin-bottom:8px;">📊 ±1天 弹性日期价格对比矩阵</h3>
                <div style="overflow-x:auto;">
                    <table style="width:100%;border-collapse:collapse;text-align:left;">
                        <thead>
                            <tr style="background:#f8f9fa;border-bottom:2px solid #dadce0;font-size:12px;color:#5f6368;">
                                <th style="padding:8px;">出发日期</th>
                                <th style="padding:8px;">返程日期</th>
                                <th style="padding:8px;">最低价</th>
                                <th style="padding:8px;">来源平台</th>
                                <th style="padding:8px;">一键比价</th>
                            </tr>
                        </thead>
                        <tbody>
                            {matrix_rows_html}
                        </tbody>
                    </table>
                </div>

                <div style="margin-top:24px;padding-top:16px;border-top:1px solid #e8eaed;font-size:12px;color:#70757a;text-align:center;line-height:1.6;">
                    <p style="margin:0;">本邮件由 GitHub Actions 自动化监控脚本发送 · 最低价由 Google Flights 全网航司实时直连抓取</p>
                    <p style="margin:4px 0 0 0;color:#9aa0a6;">点击表格右侧【携程】与【天巡】可一键跳转至对应日期官方实时页面进行横向核验比价</p>
                </div>
            </div>
        </body>
        </html>
        """
        return html

    def _clean_val(self, v: Optional[str]) -> str:
        """去除首尾空白、常见外层引号、换行符"""
        if not v:
            return ""
        return str(v).strip().strip("'").strip('"').replace("\n", "").replace("\r", "")

    def _send_smtp_email(self, subject: str, html_content: str):
        # 1. 读取并严格清洗配置
        raw_host = self._clean_val(self.email_cfg.get("smtp_server", "smtp.gmail.com"))
        host = raw_host.replace("http://", "").replace("https://", "").split(":")[0]
        sender = self._clean_val(self.email_cfg.get("sender_email"))
        recipient = self._clean_val(self.email_cfg.get("recipient_email"))

        # ⚠️ 踩坑重点：必须完全剔除密码中的所有内部空格（针对 Google 16位应用专用密码形如 abcd efgh ijkl mnop）
        token = self._clean_val(self.email_cfg.get("sender_auth_code", "")).replace(" ", "")

        if not host or not sender or not token or not recipient:
            raise ValueError("邮件配置不完整 (缺少 host / sender / auth_code / recipient)，请检查 config.yaml 或 GitHub Secrets")

        # 2. 构建复合邮件对象
        msg = MIMEMultipart("alternative")
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"] = Header(f"机票监控机器人 <{sender}>", "utf-8")
        msg["To"] = Header(recipient, "utf-8")

        part = MIMEText(html_content, "html", "utf-8")
        msg.attach(part)

        # 3. SSL 上下文握手与双通道自动回退 (优先 587 STARTTLS，失败自动切换 465 SSL)
        import ssl
        context = ssl.create_default_context()
        channels = [
            ("STARTTLS", 587),
            ("SSL", 465)
        ]

        # 如果用户显式指定了端口且不是默认，优先尝试用户指定端口
        user_port = int(self.email_cfg.get("smtp_port", 0))
        if user_port in [587, 465]:
            if user_port == 465:
                channels = [("SSL", 465), ("STARTTLS", 587)]
            else:
                channels = [("STARTTLS", 587), ("SSL", 465)]

        last_error = None
        for mode, port in channels:
            server = None
            try:
                print(f"[Notifier] 🚀 尝试连接 SMTP {host}:{port} ({mode} 模式)...")
                if mode == "STARTTLS":
                    server = smtplib.SMTP(host, port, timeout=25)
                    server.set_debuglevel(0)
                    server.ehlo()
                    server.starttls(context=context)
                    server.ehlo()
                else:
                    server = smtplib.SMTP_SSL(host, port, context=context, timeout=25)
                    server.set_debuglevel(0)
                    server.ehlo()

                server.login(sender, token)
                server.sendmail(sender, [recipient], msg.as_string())
                print(f"[Notifier] 🎉 邮件发送成功至: {recipient} (使用 {host}:{port} {mode})")
                return
            except smtplib.SMTPAuthenticationError as auth_err:
                print(f"[Notifier] ❌ SMTP 认证失败 (账号/授权码错误，请核实 Gmail 16位应用密码): {auth_err}")
                raise auth_err
            except Exception as e:
                print(f"[Notifier] ⚠️ {mode} ({port}) 连接失败 ({e})，准备切换备用通道...")
                last_error = e
            finally:
                if server:
                    try:
                        server.quit()
                    except Exception:
                        pass

        raise RuntimeError(f"所有 SMTP 通道连接均失败，最后错误: {last_error}")

    def _send_webhooks(self, subject: str, analysis: MatrixAnalysis):
        """推送至移动端 Webhook"""
        bark_url = self.webhook_cfg.get("bark_url")
        if bark_url and analysis.global_min_offer:
            try:
                body = f"最低票价 ¥{int(analysis.global_min_offer.price)} ({analysis.global_min_offer.platform})"
                httpx.get(f"{bark_url.rstrip('/')}/{subject}/{body}", timeout=5.0)
            except Exception as e:
                print(f"[Notifier] Bark 推送失败: {e}")
