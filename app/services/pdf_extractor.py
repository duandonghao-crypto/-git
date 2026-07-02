"""
PDF text extraction for electricity bills and invoices.
Uses pypdf (lightweight, pure Python, Render-safe).
"""
import re, os

try:
    import pdfplumber
    _has_plumber = True
except ImportError:
    _has_plumber = False

try:
    from pypdf import PdfReader
    _has_pypdf = True
except ImportError:
    _has_pypdf = False


class PDFExtractor:

    @staticmethod
    def _extract_text(pdf_path: str) -> str:
        try:
            # Try pdfplumber first (better for Chinese text)
            if _has_plumber:
                with pdfplumber.open(pdf_path) as pdf:
                    if pdf.pages:
                        return pdf.pages[0].extract_text() or ''
        except Exception:
            pass
        try:
            if _has_pypdf:
                reader = PdfReader(pdf_path)
                if reader.pages:
                    return reader.pages[0].extract_text() or ''
        except Exception:
            pass
        return ''

    @staticmethod
    def extract_bill_data(pdf_path: str) -> dict | None:
        try:
            size = os.path.getsize(pdf_path)
            if size < 100 or size > 50 * 1024 * 1024:
                return None
            with open(pdf_path, 'rb') as f:
                if not f.read(10).startswith(b'%PDF'):
                    return None

            text = PDFExtractor._extract_text(pdf_path)
            if not text:
                return None

            filename = os.path.basename(pdf_path)
            uid_match = re.search(r'用户\[(\d+)\]', filename)
            if not uid_match:
                uid_match = re.search(r'用户\[(\d+)\]', text)
            user_id = uid_match.group(1) if uid_match else ''

            ym = ''
            ym_match = re.search(r'\](\d{6})', filename)
            if ym_match:
                y = ym_match.group(1)
                ym = f"{y[:4]}年{int(y[4:]):d}月"

            fee = ''
            for line in text.split('\n'):
                if '本期电费' in line:
                    fm = re.search(r'本期电费[\s:：]*([\d,.]+)', line)
                    if fm: fee = fm.group(1).replace(',', '')
                    break

            kwh = ''
            for line in text.split('\n'):
                if '本期电量' in line:
                    km = re.search(r'本期电量\s*([\d,.]+)', line)
                    if km: kwh = km.group(1).replace(',', '')
                    break

            return {'user_id': user_id, 'year_month': ym, 'electricity_fee': fee, 'electricity_kwh': kwh, 'filename': filename}
        except Exception:
            return None

    @staticmethod
    def extract_invoice_info(pdf_path: str) -> dict | None:
        try:
            text = PDFExtractor._extract_text(pdf_path)
            if not text:
                return None

            buyer = re.search(r'名称[:：]\s*([\u4e00-\u9fa5a-zA-Z()（）\s]+?有限公司)', text)
            if not buyer:
                buyer = re.search(r'名称[:：]([\u4e00-\u9fa5a-zA-Z()（）]+有限公司)', text)
            month_m = re.search(r'电费年月[:：](\d{6})', text)
            if not month_m:
                month_m = re.search(r'年月[：:]\s*(\d{6})', text)

            if buyer and month_m:
                bname = re.sub(r'\s+', '', buyer.group(1).strip())
                return {'buyer_name': bname, 'year_month': month_m.group(1)}
            return None
        except Exception:
            return None

    @staticmethod
    def rename_invoice(pdf_path: str) -> tuple[bool, str]:
        info = PDFExtractor.extract_invoice_info(pdf_path)
        if not info:
            return False, "无法提取发票信息"
        bname = info['buyer_name']
        ym = info['year_month']
        month = str(int(ym[-2:]))
        new_fn = f"{bname}{month}月电费发票.pdf"
        parent = os.path.dirname(pdf_path)
        new_path = os.path.join(parent, new_fn)
        counter = 1
        while os.path.exists(new_path):
            new_fn = f"{bname}{month}月电费发票({counter}).pdf"
            new_path = os.path.join(parent, new_fn)
            counter += 1
        os.rename(pdf_path, new_path)
        return True, new_fn
