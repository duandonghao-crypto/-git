"""
IMAP email client for downloading electricity bills and invoices.
Credentials come from environment variables (Config).
"""
import re
import os
import email
import imaplib
from datetime import datetime, timedelta
from config import Config
from app.utils.helpers import sanitize_filename, decode_filename


class EmailClient:
    """IMAP email client for electricity bill workflows."""

    MAX_MESSAGES = 200  # Safety limit to avoid timeout

    def __init__(self, address=None, password=None, server=None, port=None):
        self.address = address or Config.EMAIL_ADDRESS
        self.password = password or Config.EMAIL_PASSWORD
        self.server = server or Config.EMAIL_SERVER
        self.port = port or Config.EMAIL_PORT
        self._mail = None

    def _connect(self):
        """Connect and login to IMAP server."""
        self._mail = imaplib.IMAP4_SSL(self.server, self.port, timeout=15)
        self._mail.login(self.address, self.password)
        self._mail.select('INBOX')

    def _disconnect(self):
        if self._mail:
            try:
                self._mail.logout()
            except Exception:
                pass
            self._mail = None

    def _set_sock_timeout(self, seconds=15):
        """Set per-operation timeout on the IMAP socket."""
        if self._mail:
            try:
                sock = self._mail.socket()
                if sock:
                    sock.settimeout(seconds)
            except Exception:
                pass

    def _build_search_criteria(self, start_date=None, end_date=None):
        """Build IMAP search criteria from date range."""
        if start_date and end_date:
            try:
                sd = datetime.strptime(start_date, '%Y-%m-%d')
                ed = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
                return f'(SINCE {sd.strftime("%d-%b-%Y")} BEFORE {ed.strftime("%d-%b-%Y")})'
            except Exception:
                pass
        return 'ALL'

    def scan_emails(self, start_date=None, end_date=None):
        """Scan mailbox and count bills + invoices."""
        logs = []
        try:
            logs.append("正在连接邮箱...")
            self._connect()
            logs.append("邮箱登录成功")

            criteria = self._build_search_criteria(start_date, end_date)
            status, messages = self._mail.search(None, criteria)
            if status != 'OK':
                logs.append(f"搜索邮件失败: {status}")
                return False, logs, 0, 0, 0

            message_ids = messages[0].split()
            total = len(message_ids)
            if total > self.MAX_MESSAGES:
                logs.append(f"邮件较多({total}封)，仅检查最近{self.MAX_MESSAGES}封以避免超时")
                message_ids = message_ids[-self.MAX_MESSAGES:]
                total = len(message_ids)
            logs.append(f"找到 {total} 封邮件，开始分析...")

            bill_count = 0
            invoice_count = 0

            for i, mid in enumerate(message_ids, 1):
                if i % 5 == 1:
                    logs.append(f"分析邮件 {i}/{total}...")

                status, msg_data = self._mail.fetch(mid, '(RFC822)')
                if status != 'OK':
                    continue

                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)
                sender = msg.get('From', '')

                if '95598@sgcc.com.cn' in sender:
                    invoice_count += 1
                    continue

                body = self._extract_body(msg)
                if re.search(r'用户\[\d+\].*?电费账单', body):
                    bill_count += 1
                    continue

                for part in msg.walk():
                    if part.get_filename():
                        fn = decode_filename(part.get_filename())
                        if re.search(r'用户\[\d+\].*?电费账单', fn):
                            bill_count += 1
                            break

            logs.append(f"扫描完成: 电费账单={bill_count}, 发票={invoice_count}")
            return True, logs, total, bill_count, invoice_count
        except Exception as e:
            logs.append(f"扫描邮箱出错: {str(e)[:100]}")
            return False, logs, 0, 0, 0
        finally:
            self._disconnect()

    def download_bills(self, start_date=None, end_date=None, output_dir=None):
        """Download electricity bill PDFs from email."""
        output_dir = output_dir or Config.ATTACHMENTS_DIR
        os.makedirs(output_dir, exist_ok=True)
        logs = []

        try:
            logs.append("正在连接邮箱...")
            self._connect()
            logs.append("邮箱登录成功")

            criteria = self._build_search_criteria(start_date, end_date)
            if start_date and end_date:
                logs.append(f"搜索日期范围: {start_date} 到 {end_date}")

            status, messages = self._mail.search(None, criteria)
            if status != 'OK':
                logs.append(f"搜索失败: {status}")
                return False, logs, 0

            message_ids = messages[0].split()
            total = len(message_ids)
            if total > self.MAX_MESSAGES:
                logs.append(f"邮件较多({total}封)，仅检查最近{self.MAX_MESSAGES}封以避免超时")
                message_ids = message_ids[-self.MAX_MESSAGES:]
                total = len(message_ids)
            logs.append(f"找到 {total} 封邮件，开始下载...")
            count = 0

            for i, mid in enumerate(message_ids, 1):
                if i % 5 == 1:
                    logs.append(f"处理邮件 {i}/{total}...")
                self._set_sock_timeout(60)
                status, msg_data = self._mail.fetch(mid, '(RFC822)')
                if status != 'OK':
                    continue

                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)
                sender = msg.get('From', '')

                if '95598@sgcc.com.cn' in sender:
                    continue

                body = self._extract_body(msg)
                base_name = None
                match = re.search(r'用户\[\d+\].*?电费账单', body)
                if match:
                    base_name = sanitize_filename(match.group().strip())

                if not base_name:
                    for part in msg.walk():
                        if part.get_filename():
                            fn = decode_filename(part.get_filename())
                            m2 = re.search(r'用户\[\d+\].*?电费账单', fn)
                            if m2:
                                base_name = sanitize_filename(m2.group().strip())
                                break
                if not base_name:
                    continue

                for part in msg.walk():
                    if part.get_content_maintype() == 'multipart':
                        continue
                    if part.get('Content-Disposition') is None:
                        continue
                    filename = part.get_filename()
                    if not filename:
                        continue
                    if not decode_filename(filename).lower().endswith('.pdf'):
                        continue

                    new_fn = f"{base_name}.pdf"
                    existing = [f for f in os.listdir(output_dir)
                                if f.startswith(base_name) and f.lower().endswith('.pdf')]
                    if existing:
                        logs.append(f"跳过重复: {base_name}* (已有 {existing[0]})")
                        continue

                    filepath = os.path.join(output_dir, new_fn)
                    payload = part.get_payload(decode=True)
                    if payload:
                        with open(filepath, 'wb') as f:
                            f.write(payload)
                        count += 1
                        logs.append(f"✓ 下载: {new_fn}")

            logs.append(f"下载完成！共下载 {count} 个电费账单")
            return True, logs, count
        except Exception as e:
            logs.append(f"下载出错: {e}")
            return False, logs, 0
        finally:
            self._disconnect()

    def collect_invoice_links(self, start_date=None, end_date=None):
        """Search 95598 emails and collect invoice PDF download links."""
        logs = []
        try:
            logs.append("正在连接邮箱...")
            self._connect()
            logs.append("邮箱登录成功，搜索95598发票邮件...")

            criteria = self._build_search_criteria(start_date, end_date)
            status, messages = self._mail.search(None, criteria)
            if status != 'OK':
                logs.append(f"搜索失败: {status}")
                return False, logs, []

            message_ids = messages[0].split()
            total = len(message_ids)
            if total > self.MAX_MESSAGES:
                logs.append(f"邮件较多({total}封)，仅检查最近{self.MAX_MESSAGES}封以避免超时")
                message_ids = message_ids[-self.MAX_MESSAGES:]
                total = len(message_ids)
            logs.append(f"找到 {total} 封邮件，开始搜索发票...")
            links = []

            for i, mid in enumerate(message_ids, 1):
                if i % 5 == 1:
                    logs.append(f"处理邮件 {i}/{total}...")
                self._set_sock_timeout(60)
                status, msg_data = self._mail.fetch(mid, '(RFC822)')
                if status != 'OK':
                    continue
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)
                sender = msg.get('From', '')
                if '95598@sgcc.com.cn' not in sender:
                    continue

                body = self._extract_body(msg)
                found = re.findall(r'https?://[^\s")]+', body)
                pdf_links = [l for l in found if '/einvoice/download' in l and 'id=' in l]
                if pdf_links:
                    links.append(pdf_links[0])
                    logs.append(f"✓ 收集发票PDF链接 #{len(links)}")
                else:
                    logs.append("未找到PDF下载链接")

            logs.append(f"发票搜索完成！共收集到 {len(links)} 个发票PDF链接")
            return True, logs, links
        except Exception as e:
            logs.append(f"搜索发票出错: {e}")
            return False, logs, []
        finally:
            self._disconnect()

    def _extract_body(self, msg) -> str:
        """Extract text body from an email message."""
        body = ''
        for part in msg.walk():
            ct = part.get_content_type()
            if ct in ('text/plain', 'text/html'):
                payload = part.get_payload(decode=True)
                if payload:
                    try:
                        body += payload.decode('utf-8', errors='replace')
                    except Exception:
                        body += str(payload)
        return body
