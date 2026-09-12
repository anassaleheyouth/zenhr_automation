"""
ZenHR Remote-Work Request Automation — نسخة خفيفة (بدون متصفح)
================================================================
بتعمل بالظبط نفس اللي نسخة Playwright بتعمله، بس عن طريق HTTP requests
مباشرة (أسرع بكتير، من غير ما تحتاج تحميل متصفح Chromium).

الـ flow:
1. GET صفحة الـ login → نستخرج الـ authenticity_token (CSRF) من الـ HTML
2. POST بيانات الدخول لنفس الصفحة → السيشن بتاعتنا بتاخد session cookie
3. GET صفحة الـ approvals بنفس السيشن → نستخرج الـ v3-token المتضمن في الصفحة
4. POST الطلب الفعلي لـ ZenHR API باستخدام الـ v3-token كـ Bearer token

طريقة التشغيل: زي النسخة التانية بالظبط
    python zenhr_automation_api.py sunday
    python zenhr_automation_api.py tuesday
"""

import argparse
import json
import logging
import os
import re
import sys
import time
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "config.json"
LOG_PATH = SCRIPT_DIR / "zenhr_automation_api.log"

# ثوابت خاصة بالحساب - ممكن تتغير لو ZenHR غيّروا حاجة في السيستم بتاعهم
BRANCH_ID = "10338"
TIMEOFF_TYPE_ID = "133654"  # "Working remotely" - نفس الرقم اللي شفناه في أول طلب فعلي

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def load_config() -> dict:
    env_map = {
        "zenhr_email": "ZENHR_EMAIL",
        "zenhr_password": "ZENHR_PASSWORD",
        "callmebot_phone": "CALLMEBOT_PHONE",
        "callmebot_apikey": "CALLMEBOT_APIKEY",
    }
    if all(os.environ.get(env_var) for env_var in env_map.values()):
        log.info("Loading config from environment variables.")
        return {key: os.environ[env_var] for key, env_var in env_map.items()}
    if not CONFIG_PATH.exists():
        log.error("مفيش config.json ولا environment variables.")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def next_weekday(target_weekday: int, from_date: date | None = None) -> date:
    base = from_date or date.today()
    days_ahead = (target_weekday - base.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return base + timedelta(days=days_ahead)


def send_whatsapp(config: dict, message: str) -> None:
    phone = config["callmebot_phone"]
    apikey = config["callmebot_apikey"]
    text = urllib.parse.quote(message)
    url = f"https://api.callmebot.com/whatsapp.php?phone={phone}&text={text}&apikey={apikey}"

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            requests.get(url, timeout=30)
            log.info("WhatsApp notification sent.")
            return
        except Exception as e:
            log.warning(f"WhatsApp attempt {attempt}/{max_attempts} failed: {e}")
            if attempt < max_attempts:
                time.sleep(10)
    log.error("Failed to send WhatsApp notification after all retry attempts.")


def login_and_get_session(config: dict) -> tuple[requests.Session, str, str]:
    """
    بترجع (session, v3_token, employee_id) بعد تسجيل دخول ناجح.
    """
    session = requests.Session()
    session.headers.update(
        {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    )

    # 1) نجيب صفحة اللوجين ونستخرج الـ CSRF token
    login_page = session.get("https://app.zenhr.com/ar/users/sign_in", timeout=30)
    login_page.raise_for_status()
    csrf_match = re.search(
        r'name=["\']authenticity_token["\']\s+value=["\']([^"\']+)["\']', login_page.text
    )
    if not csrf_match:
        raise RuntimeError("مقدرناش نلاقي authenticity_token في صفحة اللوجين.")
    csrf_token = csrf_match.group(1)

    # 2) نبعت بيانات الدخول
    login_response = session.post(
        "https://app.zenhr.com/ar/users/sign_in",
        data={
            "authenticity_token": csrf_token,
            "user[login]": config["zenhr_email"],
            "user[password]": config["zenhr_password"],
            "user[remember_me]": "0",
        },
        timeout=30,
        allow_redirects=True,
    )
    login_response.raise_for_status()
    if "sign_in" in login_response.url:
        raise RuntimeError("فشل تسجيل الدخول - تأكد من الإيميل والباسورد.")

    # 3) نجيب صفحة approvals ونستخرج الـ v3 token المتضمن فيها
    approvals_page = session.get(
        "https://app.zenhr.com/en/approvals?tab=approvals", timeout=30
    )
    approvals_page.raise_for_status()
    # نستخرج الـ v3 token الخاص تحديدًا بموديول الـ approvals (أوسع صلاحيات من التوكن العام)
    token_match = re.search(
        r'id=["\']approvals-root["\'][^>]*?data-v3-token=["\']([^"\']+)["\']',
        approvals_page.text,
    )
    if not token_match:
        raise RuntimeError("مقدرناش نلاقي v3-token في approvals-root.")
    v3_token = token_match.group(1)

    employee_id_match = re.search(
        r'id=["\']approvals-root["\'][^>]*?data-current-employee-id=["\']([^"\']+)["\']',
        approvals_page.text,
    )
    if not employee_id_match:
        # نجرب نلاقيه في صفحة تانية لو مش موجود هنا
        employee_id_match = re.search(
            r"data-current-employee-id=['\"]([^'\"]+)['\"]", login_page.text
        )
    employee_id = employee_id_match.group(1) if employee_id_match else None

    return session, v3_token, employee_id


def submit_remote_work_request(config: dict, from_date: date, to_date: date) -> tuple[bool, str]:
    try:
        session, v3_token, employee_id = login_and_get_session(config)
        log.info(f"Logged in successfully. employee_id={employee_id}")

        amount = (to_date - from_date).days + 1

        response = session.post(
            f"https://app.zenhr.com/api/v3/branches/{BRANCH_ID}/timeoff_transaction_requests",
            params={"locale": "en"},
            headers={"Authorization": f"Bearer {v3_token}"},
            files={  # multipart/form-data زي ما الموقع بيبعتها فعليًا
                "timeoff_id": (None, TIMEOFF_TYPE_ID),
                "employee_id": (None, employee_id),
                "from_date": (None, from_date.strftime("%a, %b %d, %Y 12:00 AM")),
                "to_date": (None, to_date.strftime("%a, %b %d, %Y 12:00 AM")),
                "amount": (None, str(amount)),
                "notes": (None, "."),
            },
            timeout=30,
        )

        if response.status_code in (200, 201):
            msg = f"تم إرسال طلب Working Remotely بنجاح من {from_date} لـ {to_date} ✅"
            log.info(msg)
            return True, msg
        else:
            msg = (
                f"فشل إرسال الطلب - Status {response.status_code}: {response.text[:300]} ❌"
            )
            log.warning(msg)
            return False, msg

    except Exception as e:
        msg = f"حصل خطأ غير متوقع أثناء إرسال الطلب: {e}"
        log.error(msg)
        return False, msg


def main():
    parser = argparse.ArgumentParser(description="ZenHR Remote-Work Request Automation (API version)")
    parser.add_argument(
        "mode",
        choices=["sunday", "tuesday", "auto"],
        nargs="?",
        default="auto",
        help=(
            "sunday/tuesday: يجبر الوضع ده بغض النظر عن اليوم الحالي (للتجربة اليدوية). "
            "auto (افتراضي): يشتغل كل يوم بس بيبعت الطلب بس لو النهاردة فعلًا الأحد أو الثلاثاء، "
            "وإلا بيقفل من غير ما يعمل حاجة - مفيد لو الـ scheduler بتاعك بيدعم يومي بس."
        ),
    )
    args = parser.parse_args()

    config = load_config()

    if args.mode == "auto":
        today_weekday = date.today().weekday()  # Monday=0 ... Sunday=6
        if today_weekday == 6:  # الأحد
            mode = "sunday"
        elif today_weekday == 1:  # الثلاثاء
            mode = "tuesday"
        else:
            log.info(f"النهاردة مش أحد ولا ثلاثاء (weekday={today_weekday}) - مفيش حاجة نعملها.")
            sys.exit(0)
    else:
        mode = args.mode

    if mode == "sunday":
        monday = next_weekday(0)
        from_date, to_date = monday, monday
    else:
        wednesday = next_weekday(2)
        thursday = wednesday + timedelta(days=1)
        from_date, to_date = wednesday, thursday

    log.info(f"Starting automation | mode={mode} | from={from_date} to={to_date}")

    success, message = submit_remote_work_request(config, from_date, to_date)
    send_whatsapp(config, message)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
