"""
ZenHR Remote-Work Request Automation
=====================================
بيسجل دخول على ZenHR، يبعت طلب "Working remotely"، ويتأكد إنه اتبعت صح،
وبعدين يبعت رسالة WhatsApp (عن طريق CallMeBot) بنتيجة العملية.

طريقة التشغيل:
    python zenhr_automation.py sunday      -> يبعت طلب ليوم الاتنين الجاي
    python zenhr_automation.py tuesday     -> يبعت طلب من الاربع للخميس الجايين

محتاج ملف config.json (انسخه من config.json.example وعبي بياناتك فيه)
موجود في نفس الفولدر بتاع السكريبت ده.
"""

import argparse
import json
import logging
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "config.json"
LOG_PATH = SCRIPT_DIR / "zenhr_automation.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    # لو شغال على GitHub Actions، البيانات هتيجي من Secrets (environment variables)
    env_map = {
        "zenhr_email": "ZENHR_EMAIL",
        "zenhr_password": "ZENHR_PASSWORD",
        "callmebot_phone": "CALLMEBOT_PHONE",
        "callmebot_apikey": "CALLMEBOT_APIKEY",
    }
    if all(os.environ.get(env_var) for env_var in env_map.values()):
        log.info("Loading config from environment variables.")
        return {key: os.environ[env_var] for key, env_var in env_map.items()}

    # وإلا نستخدم config.json المحلي (للتشغيل على جهازك)
    if not CONFIG_PATH.exists():
        log.error(
            "مفيش config.json ولا environment variables. "
            "انسخ config.json.example وسميه config.json وعبي بياناتك فيه، "
            "أو ظبط الـ GitHub Secrets."
        )
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def next_weekday(target_weekday: int, from_date: date | None = None) -> date:
    """
    بيرجع تاريخ أقرب يوم جاي بيطابق target_weekday.
    target_weekday: Monday=0, Tuesday=1, Wednesday=2, Thursday=3, ...
    """
    base = from_date or date.today()
    days_ahead = (target_weekday - base.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7  # لو انهاردة نفس اليوم، خد الأسبوع الجاي مش النهاردة
    return base + timedelta(days=days_ahead)


def send_whatsapp(config: dict, message: str) -> None:
    try:
        phone = config["callmebot_phone"]
        apikey = config["callmebot_apikey"]
        text = urllib.parse.quote(message)
        url = f"https://api.callmebot.com/whatsapp.php?phone={phone}&text={text}&apikey={apikey}"
        urllib.request.urlopen(url, timeout=15)
        log.info("WhatsApp notification sent.")
    except Exception as e:
        log.error(f"Failed to send WhatsApp notification: {e}")


def select_calendar_date(page, picker_button_selector: str, target_date: date) -> None:
    """
    بيفتح الـ date picker (PrimeReact) ويختار اليوم المطلوب،
    مع التنقل بين الشهور لو محتاج.
    """
    page.locator(picker_button_selector).click()
    page.wait_for_timeout(400)

    today = date.today()
    months_diff = (target_date.year - today.year) * 12 + (target_date.month - today.month)
    for _ in range(months_diff):
        page.locator(".p-datepicker-next").click()
        page.wait_for_timeout(250)

    day_str = str(target_date.day)
    day_cells = page.locator(
        ".p-datepicker-calendar td:not(.p-datepicker-other-month) span",
        has_text=re.compile(rf"^{day_str}$"),
    )
    day_cells.first.click()
    page.wait_for_timeout(300)


# ---------------------------------------------------------------------------
# Main automation flow
# ---------------------------------------------------------------------------

def submit_remote_work_request(config: dict, from_date: date, to_date: date) -> tuple[bool, str]:
    """
    بيرجع (success: bool, message: str)
    """
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        try:
            # ---- Login ----
            page.goto("https://app.zenhr.com/ar/users/sign_in", timeout=30000)
            page.get_by_role("textbox", name="البريد الالكتروني").click()
            page.get_by_role("textbox", name="البريد الالكتروني").fill(config["zenhr_email"])
            page.get_by_role("textbox", name="البريد الالكتروني").press("Tab")
            page.get_by_role("textbox", name="كلمة السر").fill(config["zenhr_password"])
            page.get_by_role("button", name="تسجيل الدخول").click()
            page.wait_for_load_state("networkidle", timeout=30000)
            log.info("Logged in successfully.")

            # ---- Navigate to Approvals & Requests ----
            page.goto("https://app.zenhr.com/en/employee_onboarding", timeout=30000)
            page.wait_for_timeout(1000)

            try:
                page.get_by_role("link", name="Icon Approvals & Requests").click(timeout=8000)
            except PlaywrightTimeoutError:
                # لو مفيش onboarding overlay، نجرب ندخل الصفحة مباشرة
                page.goto("https://app.zenhr.com/en/approvals?tab=approvals", timeout=30000)

            try:
                page.get_by_role("button", name="Skip").click(timeout=5000)
            except PlaywrightTimeoutError:
                pass  # الـ tour overlay ممكن ميظهرش كل مرة

            # ---- Open request form ----
            page.get_by_role("button", name="Add Request").click(timeout=15000)
            page.get_by_role("button", name="Time Offs").click(timeout=15000)

            # Employee (fixed - نفس المستخدم)
            page.locator(
                "#employee > .select__control > .select__value-container > .select__input-container"
            ).click()
            page.get_by_text("- Anas Saleh Mousa AlSadiq").click()

            # Timeoff type (fixed - Working remotely)
            page.locator(
                "#timeoff_types > .select__control > .select__value-container > .select__input-container"
            ).click()
            page.get_by_text("Working remotely").click()

            # Dates
            select_calendar_date(page, "#date-picker-from-date-dateTimeRange > .p-button", from_date)
            select_calendar_date(page, "#date-picker-to-date-dateTimeRange > .p-button", to_date)

            # Notes
            page.locator("#notes").click()
            page.locator("#notes").fill(".")

            # ---- Submit ----
            page.locator("button").filter(has_text="Request").nth(1).click()
            page.wait_for_timeout(3000)

            # ---- Verify success ----
            success = False
            try:
                page.wait_for_selector(
                    "text=/success|تم بنجاح|submitted/i", timeout=8000
                )
                success = True
            except PlaywrightTimeoutError:
                # نتأكد بطريقة تانية: مفيش رسالة error ظاهرة
                error_visible = page.locator("text=/error|مشكلة|failed/i").count() > 0
                success = not error_visible

            screenshot_path = SCRIPT_DIR / f"last_run_{date.today().isoformat()}.png"
            page.screenshot(path=str(screenshot_path))

            if success:
                msg = f"تم إرسال طلب Working Remotely بنجاح من {from_date} لـ {to_date} ✅"
                log.info(msg)
                return True, msg
            else:
                msg = f"في مشكلة في إرسال الطلب من {from_date} لـ {to_date}. شوف الـ screenshot: {screenshot_path.name} ❌"
                log.warning(msg)
                return False, msg

        except Exception as e:
            screenshot_path = SCRIPT_DIR / f"error_{date.today().isoformat()}.png"
            try:
                page.screenshot(path=str(screenshot_path))
            except Exception:
                pass
            msg = f"حصل خطأ غير متوقع أثناء إرسال الطلب: {e}"
            log.error(msg)
            return False, msg

        finally:
            context.close()
            browser.close()


def main():
    parser = argparse.ArgumentParser(description="ZenHR Remote-Work Request Automation")
    parser.add_argument(
        "mode",
        choices=["sunday", "tuesday"],
        help="sunday: يبعت طلب ليوم الاتنين | tuesday: يبعت طلب من الاربع للخميس",
    )
    args = parser.parse_args()

    config = load_config()

    if args.mode == "sunday":
        monday = next_weekday(0)  # Monday
        from_date, to_date = monday, monday
    else:  # tuesday
        wednesday = next_weekday(2)  # Wednesday
        thursday = wednesday + timedelta(days=1)
        from_date, to_date = wednesday, thursday

    log.info(f"Starting automation | mode={args.mode} | from={from_date} to={to_date}")

    success, message = submit_remote_work_request(config, from_date, to_date)
    send_whatsapp(config, message)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
