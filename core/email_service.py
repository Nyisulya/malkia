import os
import re
import time
import base64
import requests
from requests.auth import HTTPBasicAuth
from django.conf import settings
from django.core.mail import EmailMultiAlternatives

RESEND_API_URL = "https://api.resend.com/emails"
DEFAULT_SMSGATE_SERVER = "https://api.sms-gate.app"
DEFAULT_NEXTSMS_URL = "https://messaging-service.co.tz/api/sms/v1/text/single"
COMPANY_OFFICIAL_NAME = "Malkia Cargo Wave Limited"


# =========================================================================
# 1. RESEND EMAIL ENGINE
# =========================================================================

def get_resend_api_key():
    from .models import SystemConfig
    db_val = SystemConfig.get_value('RESEND_API_KEY', '').strip()
    if db_val:
        return db_val
    return (getattr(settings, 'RESEND_API_KEY', '') or os.getenv('RESEND_API_KEY', '')).strip()


def get_resend_from_email():
    """
    Returns the formatted from address, e.g. 'Malkia Cargo Wave Limited <info@malkiacargowave.com>'
    """
    from .models import SystemConfig
    display_name = (
        SystemConfig.get_value('RESEND_SENDER_NAME', '').strip()
        or COMPANY_OFFICIAL_NAME
    )
    if 'Freight' in display_name:
        display_name = COMPANY_OFFICIAL_NAME
    from_address = (
        SystemConfig.get_value('RESEND_FROM_EMAIL', '').strip()
        or getattr(settings, 'RESEND_FROM_EMAIL', 'info@malkiacargowave.com')
    )
    if '<' in from_address and '>' in from_address:
        return from_address
    return f"{display_name} <{from_address}>"


def send_resend_email(to_email, subject, html_content, text_content=None, reply_to=None):
    """
    Sends email via Resend API (Primary).
    If Resend fails or is not configured, falls back to Django SMTP.
    Returns (success: bool, response_info: str)
    """
    api_key = get_resend_api_key()
    from_sender = get_resend_from_email()
    raw_list = [to_email] if isinstance(to_email, str) else (to_email or [])
    recipients = [r.strip() for r in raw_list if r and isinstance(r, str) and '@' in r.strip()]

    if not recipients:
        return False, "Hakuna barua pepe halali ya mpokeaji (Customer Email haipo)."

    if api_key:
        payload = {
            "from": from_sender,
            "to": recipients,
            "subject": subject,
            "html": html_content,
        }
        if text_content:
            payload["text"] = text_content
        if reply_to:
            payload["reply_to"] = reply_to

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(RESEND_API_URL, json=payload, headers=headers, timeout=12)
            if response.status_code in [200, 201]:
                data = response.json()
                msg_id = data.get('id', 'OK')
                return True, f"Email imetumwa kupitia Resend (ID: {msg_id}) kwenda {', '.join(recipients)}"
            else:
                resend_err = f"Resend Error [{response.status_code}]: {response.text}"
                print(f"[Email Service] Resend failed: {resend_err}. Trying SMTP fallback...")
        except Exception as e:
            resend_err = f"Resend connection failed: {str(e)}"
            print(f"[Email Service] {resend_err}. Trying SMTP fallback...")
    else:
        resend_err = "RESEND_API_KEY haijawekwa kwenye Settings."

    try:
        smtp_sender = getattr(settings, 'DEFAULT_FROM_EMAIL', from_sender)
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content or "Tafadhali tumia mfumo unaowezesha HTML kusoma barua pepe hii.",
            from_email=smtp_sender,
            to=recipients,
            reply_to=[reply_to] if reply_to else None,
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True, f"Email imetumwa kupitia SMTP Fallback ({smtp_sender})"
    except Exception as smtp_err:
        return False, f"Resend: {resend_err} | SMTP: {str(smtp_err)}"


# =========================================================================
# 2. SMS ENGINE (SMS GATE ANDROID GATEWAY + NEXTSMS SUPPORT)
# =========================================================================

def normalize_tz_phone(phone_raw, with_plus=False):
    """
    Normalizes a Tanzanian phone number to 255XXXXXXXXX (or +255XXXXXXXXX when with_plus=True).
    """
    if not phone_raw:
        return ""
    first_part = re.split(r'[,;/|]', str(phone_raw))[0]
    digits = re.sub(r'\D', '', first_part)
    if not digits:
        return ""
    if digits.startswith('0') and len(digits) == 10:
        digits = '255' + digits[1:]
    elif len(digits) == 9 and digits[0] in ['6', '7']:
        digits = '255' + digits
    if with_plus and not digits.startswith('+'):
        return '+' + digits
    return digits


def get_smsgate_config():
    from .models import SystemConfig
    server_url = (
        SystemConfig.get_value('SMS_GATE_SERVER_URL', '').strip()
        or os.getenv('SMS_GATE_SERVER_URL', '')
        or DEFAULT_SMSGATE_SERVER
    ).rstrip('/')
    username = (
        SystemConfig.get_value('SMS_GATE_USERNAME', '').strip()
        or os.getenv('SMS_GATE_USERNAME', '')
    ).strip()
    password = (
        SystemConfig.get_value('SMS_GATE_PASSWORD', '').strip()
        or os.getenv('SMS_GATE_PASSWORD', '')
    ).strip()
    device_id = (
        SystemConfig.get_value('SMS_GATE_DEVICE_ID', '').strip()
        or os.getenv('SMS_GATE_DEVICE_ID', '')
    ).strip()
    sim_raw = (
        SystemConfig.get_value('SMS_GATE_SIM_NUMBER', '').strip()
        or os.getenv('SMS_GATE_SIM_NUMBER', '1')
    ).strip()
    order_phone = (
        SystemConfig.get_value('SMS_GATE_ORDER_PHONE', '').strip()
        or os.getenv('SMS_GATE_ORDER_PHONE', '')
    ).strip()
    try:
        sim_number = int(sim_raw)
    except ValueError:
        sim_number = 1

    return {
        'server_url': server_url,
        'username': username,
        'password': password,
        'device_id': device_id,
        'sim_number': sim_number,
        'order_phone': order_phone,
        'is_configured': bool(username and password),
    }


def get_nextsms_config():
    from .models import SystemConfig
    api_key = (
        SystemConfig.get_value('NEXTSMS_API_KEY', '').strip()
        or getattr(settings, 'NEXTSMS_API_KEY', '')
        or os.getenv('NEXTSMS_API_KEY', '')
    ).strip()
    username = (
        SystemConfig.get_value('NEXTSMS_USERNAME', '').strip()
        or getattr(settings, 'NEXTSMS_USERNAME', '')
        or os.getenv('NEXTSMS_USERNAME', '')
    ).strip()
    password = (
        SystemConfig.get_value('NEXTSMS_PASSWORD', '').strip()
        or getattr(settings, 'NEXTSMS_PASSWORD', '')
        or os.getenv('NEXTSMS_PASSWORD', '')
    ).strip()
    sender_id = (
        SystemConfig.get_value('NEXTSMS_SENDER_ID', '').strip()
        or getattr(settings, 'NEXTSMS_SENDER_ID', '')
        or os.getenv('NEXTSMS_SENDER_ID', '')
        or 'N-SMS'
    ).strip()
    api_url = (
        SystemConfig.get_value('NEXTSMS_API_URL', '').strip()
        or getattr(settings, 'NEXTSMS_API_URL', '')
        or os.getenv('NEXTSMS_API_URL', '')
        or DEFAULT_NEXTSMS_URL
    ).strip()
    return {
        'api_key': api_key,
        'username': username,
        'password': password,
        'sender_id': sender_id,
        'api_url': api_url,
        'is_configured': bool(api_key or (username and password)),
    }


def send_smsgate_sms(to_phone, message_text):
    """
    Sends an SMS via SMS Gate Android Gateway (https://api.sms-gate.app/3rdparty/v1/message).
    """
    cfg = get_smsgate_config()
    clean_phone = normalize_tz_phone(to_phone, with_plus=True)
    if not clean_phone:
        return False, "Namba ya simu ya mteja haipo au si sahihi."

    if not cfg['is_configured']:
        return False, "SMS Gate credentials hazijawekwa."

    base_url = cfg['server_url']
    if '/3rdparty/' in base_url:
        endpoint = base_url
    else:
        endpoint = f"{base_url}/3rdparty/v1/message"

    payload = {
        "textMessage": {"text": message_text},
        "phoneNumbers": [clean_phone],
        "simNumber": cfg['sim_number'],
    }
    if cfg['device_id']:
        payload["deviceId"] = cfg['device_id']

    try:
        resp = requests.post(
            endpoint,
            json=payload,
            auth=HTTPBasicAuth(cfg['username'], cfg['password']),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=15,
        )
        if resp.status_code in [200, 201, 202]:
            data = resp.json() if resp.text else {}
            msg_id = data.get('id', 'OK')
            state = data.get('state', 'Pending')
            print(f"[SMS Gate] Sent to {clean_phone} (ID: {msg_id}, State: {state})")
            return True, f"SMS imetumwa kupitia SMS Gate kwenda {clean_phone} (ID: {msg_id})"
        else:
            err = f"SMS Gate HTTP {resp.status_code}: {resp.text}"
            print(f"[SMS Gate] Error: {err}")
            return False, err
    except Exception as e:
        err = f"SMS Gate Connection Error: {str(e)}"
        print(f"[SMS Gate] {err}")
        return False, err


def send_nextsms_sms(to_phone, message_text, reference=None):
    """
    Unified SMS dispatcher:
    1. Uses SMS Gate Android Gateway (api.sms-gate.app) if configured.
    2. Otherwise uses NextSMS Tanzania if configured.
    """
    smsgate_cfg = get_smsgate_config()
    if smsgate_cfg['is_configured']:
        ok, info = send_smsgate_sms(to_phone, message_text)
        if ok:
            return True, info
        # If NextSMS is also configured, try NextSMS as fallback
        next_cfg = get_nextsms_config()
        if not next_cfg['is_configured']:
            return False, info

    cfg = get_nextsms_config()
    clean_phone = normalize_tz_phone(to_phone, with_plus=False)
    if not clean_phone:
        return False, "Namba ya simu ya mteja haipo au si sahihi."

    if not cfg['is_configured']:
        return False, "Credentials za SMS (SMS Gate / NextSMS) bado hazijawekwa kwenye Settings."

    auth_candidates = []
    if cfg['api_key']:
        if cfg['api_key'].startswith('Basic ') or cfg['api_key'].startswith('Bearer '):
            auth_candidates.append(cfg['api_key'])
        else:
            auth_candidates.append(f"Bearer {cfg['api_key']}")
            auth_candidates.append(f"Basic {cfg['api_key']}")
    if cfg['username'] and cfg['password']:
        b64_token = base64.b64encode(f"{cfg['username']}:{cfg['password']}".encode('utf-8')).decode('utf-8')
        auth_candidates.append(f"Basic {b64_token}")

    payload = {
        "from": cfg['sender_id'],
        "to": clean_phone,
        "text": message_text,
        "reference": reference or f"malkia_{int(time.time())}"
    }

    last_err = ""
    for auth_val in auth_candidates:
        headers = {
            "Authorization": auth_val,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            resp = requests.post(cfg['api_url'], json=payload, headers=headers, timeout=12)
            if resp.status_code in [200, 201]:
                return True, f"SMS imetumwa kupitia NextSMS kwenda {clean_phone}"
            else:
                last_err = f"NextSMS HTTP {resp.status_code}: {resp.text}"
        except Exception as e:
            last_err = f"NextSMS Connection Error: {str(e)}"

    return False, last_err or "Imeshindikana kutuma SMS."


# =========================================================================
# 3. THE 3 SIMPLE, CLEAR CLIENT NOTIFICATIONS (NO FILE NO, NO TECHNICAL JARGON)
# =========================================================================

MILESTONE_TEMPLATES = {
    'DOCS_RECEIVED': {
        "status_badge": "Nyaraka Zako Zimepokelewa",
        "badge_color": "#0F766E",
        "subject": "Tumepokea Nyaraka za Mzigo Wako ({cargo_desc}) - Malkia Cargo Wave Limited",
        "summary": (
            "Tunapenda kukujulisha kuwa tumepokea salama nyaraka za mzigo wako ({cargo_desc}). "
            "Tayari tumeanza kushughulikia taratibu za kuutoa mzigo wako bandarini."
        ),
        "action_note": (
            "Kwa sasa huna haja ya kufanya chochote. Tutakutumia ujumbe mara tu kodi ya TRA itakapotoka."
        ),
        "sms_template": (
            "MALKIA CARGO WAVE LIMITED\n"
            "-------------------------\n"
            "Habari {contact_person},\n\n"
            "Tumepokea salama nyaraka za mzigo wako:\n"
            "• Mzigo: {cargo_desc}\n"
            "• B/L No: {bl_number}\n\n"
            "Tumeanza taratibu za kuutoa mzigo wako bandarini. Tutakujulisha mara tu kodi ya TRA itakapotoka.\n\n"
            "Asante kwa kutuchagua!"
        ),
    },
    'TRA_DUTY_ISSUED': {
        "status_badge": "Kodi ya TRA Imetoka",
        "badge_color": "#DC2626",
        "subject": "Taarifa ya Kodi ya TRA kwa Mzigo Wako ({cargo_desc}) - Malkia Cargo Wave Limited",
        "summary": (
            "Mahesabu ya kodi ya TRA kwa ajili ya mzigo wako ({cargo_desc}) yametoka. "
            "Kiasi cha kodi kinachotakiwa kulipwa ni TSh {assessed_duty} kupitia namba ya malipo (Control Number): {duty_control_number}."
        ),
        "action_note": (
            "Tafadhali lipia kodi hiyo kupitia Benki yoyote au kwa simu (M-Pesa, TigoPesa, Airtel Money) "
            "ukitumia namba hiyo ya malipo. Ukishalipa tafadhali tujulishe ili tuendelee kuutoa mzigo wako bandarini."
        ),
        "sms_template": (
            "MALKIA CARGO WAVE LIMITED\n"
            "-------------------------\n"
            "Habari {contact_person},\n\n"
            "Kodi ya TRA ya mzigo wako imetoka:\n"
            "• Mzigo: {cargo_desc}\n"
            "• Kiasi cha Kodi: TSh {assessed_duty}\n"
            "• Control Number: {duty_control_number}\n\n"
            "Tafadhali lipia kupitia Benki au kwa simu (M-Pesa, TigoPesa, Airtel Money) kisha utujulishe.\n\n"
            "Asante!"
        ),
    },
    'PORT_EXIT_YARD_ARRIVAL': {
        "status_badge": "Mzigo Umetoka Bandarini na Kufika Yard",
        "badge_color": "#059669",
        "subject": "Habari Njema: Mzigo Wako ({cargo_desc}) Umefika Yard Yetu - Malkia Cargo Wave Limited",
        "summary": (
            "Habari njema! Mzigo wako ({cargo_desc}) umeshatoka bandarini salama na sasa umefika kwenye "
            "Yard yetu ya Malkia Cargo Wave Limited."
        ),
        "action_note": (
            "Mzigo wako uko tayari. Karibu sana ofisini kwetu ili ukamilishe taratibu za mwisho na "
            "ukabidhiwe mzigo wako."
        ),
        "sms_template": (
            "MALKIA CARGO WAVE LIMITED\n"
            "-------------------------\n"
            "Habari {contact_person},\n\n"
            "Habari njema! Mzigo wako umeshatoka bandarini salama:\n"
            "• Mzigo: {cargo_desc}\n"
            "• B/L No: {bl_number}\n"
            "• Mahali Ulipo: Umefika Yard Yetu\n\n"
            "Karibu sana ofisini kwetu uchukue mzigo wako.\n\n"
            "Asante kwa kutuamini!"
        ),
    },
}


def notify_client_milestone(job, milestone_key, extra_note=''):
    """
    Sends BOTH Email (via Resend) AND SMS (via SMS Gate / NextSMS) using simple, clear Swahili
    without internal file numbers or technical port jargon.
    """
    tmpl = MILESTONE_TEMPLATES.get(milestone_key)
    if not tmpl:
        return {
            'email_ok': False,
            'email_info': f"Milestone '{milestone_key}' haijulikani.",
            'sms_ok': False,
            'sms_info': f"Milestone '{milestone_key}' haijulikani.",
        }

    customer = job.customer
    customer_name = customer.company_name if customer else "Mteja Wetu"
    raw_cp = (customer.contact_person or '').strip() if customer else ''
    contact_person = customer_name if (not raw_cp or raw_cp.lower() in ['managing director', 'director', 'manager', 'owner', 'ceo']) else raw_cp
    customer_email = (customer.email or '').strip() if customer else ''
    customer_phone = (customer.phone or '').strip() if customer else ''

    fmt_duty = f"{job.assessed_duty_amount:,.0f}" if job.assessed_duty_amount else "0"
    received_docs_list = [name for name, ok in job.received_docs_checklist if ok]
    received_docs_str = ", ".join(received_docs_list) if received_docs_list else "Bill of Lading & Invoice"

    cargo_label = (job.cargo_description or '').strip() or (job.chassis_number or '').strip() or "Mzigo Wako"

    context_vars = {
        "bl_number": job.bl_number or "-",
        "chassis_number": job.chassis_number or "-",
        "cargo_desc": cargo_label,
        "assessed_duty": fmt_duty,
        "duty_control_number": job.duty_control_number or "-",
        "customer_name": customer_name,
        "contact_person": contact_person,
        "received_docs": received_docs_str,
    }

    subject = tmpl["subject"].format(**context_vars)
    summary_text = tmpl["summary"].format(**context_vars)
    action_note = tmpl["action_note"].format(**context_vars)
    sms_text = tmpl["sms_template"].format(**context_vars)
    status_badge = tmpl["status_badge"]
    badge_color = tmpl["badge_color"]

    callout_box_html = ""
    if milestone_key == 'DOCS_RECEIVED':
        callout_box_html = f"""
        <div style="background: #F0FDFA; border: 1.5px solid #5EEAD4; border-radius: 10px; padding: 16px; margin: 18px 0;">
            <div style="font-size: 13px; font-weight: 800; color: #0F766E; margin-bottom: 4px;">
                Nyaraka Tulizopokea:
            </div>
            <div style="font-size: 14.5px; font-weight: 700; color: #134E4A;">
                {received_docs_str}
            </div>
        </div>
        """
    elif milestone_key == 'TRA_DUTY_ISSUED':
        callout_box_html = f"""
        <div style="background: #FEF2F2; border: 2px dashed #EF4444; border-radius: 10px; padding: 18px; margin: 20px 0; text-align: center;">
            <div style="font-size: 13px; font-weight: 700; color: #991B1B; text-transform: uppercase;">
                Namba ya Kulipia Kodi TRA (Control Number):
            </div>
            <div style="font-family: monospace; font-size: 26px; font-weight: 800; color: #7F1D1D; letter-spacing: 0.08em; margin: 8px 0;">
                {context_vars['duty_control_number']}
            </div>
            <div style="font-size: 16px; font-weight: 800; color: #166534; background: #DCFCE7; display: inline-block; padding: 6px 16px; border-radius: 6px;">
                Kiasi cha Kodi: TSh {fmt_duty}
            </div>
            <div style="font-size: 13px; color: #475569; margin-top: 10px;">
                Unaweza kulipia kupitia Benki au kwa simu (M-Pesa, TigoPesa, Airtel Money).
            </div>
        </div>
        """
    elif milestone_key == 'PORT_EXIT_YARD_ARRIVAL':
        callout_box_html = f"""
        <div style="background: #ECFDF5; border: 2px solid #10B981; border-radius: 10px; padding: 18px; margin: 20px 0; text-align: center;">
            <div style="font-size: 16px; font-weight: 800; color: #065F46; margin-bottom: 4px;">
                Mzigo Upo Tayari Kwenye Yard Yetu
            </div>
            <div style="font-size: 14px; color: #047857;">
                Karibu ofisini kwetu Malkia Cargo Wave Limited uchukue mzigo wako.
            </div>
        </div>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{subject}</title>
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #F1F5F9; margin: 0; padding: 24px 12px; line-height: 1.6; color: #1E293B;">
        <div style="max-width: 600px; margin: 0 auto; background: #FFFFFF; border-radius: 14px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.06); border: 1px solid #E2E8F0;">
            <div style="background: linear-gradient(135deg, #0F766E 0%, #0F172A 100%); color: #FFFFFF; padding: 26px 24px; text-align: center;">
                <div style="font-size: 12px; font-weight: 800; letter-spacing: 0.12em; text-transform: uppercase; color: #99F6E4; margin-bottom: 6px;">
                    {COMPANY_OFFICIAL_NAME}
                </div>
                <h1 style="font-size: 21px; font-weight: 800; margin: 0;">
                    Taarifa ya Mzigo Wako
                </h1>
            </div>

            <div style="padding: 28px 24px;">
                <p style="font-size: 15.5px; margin-top: 0; color: #1E293B;">
                    Habari <strong>{contact_person}</strong>,
                </p>

                <div style="margin: 18px 0; text-align: center;">
                    <span style="display: inline-block; background: {badge_color}; color: #FFFFFF; padding: 8px 18px; border-radius: 50px; font-weight: 700; font-size: 13.5px;">
                        {status_badge}
                    </span>
                </div>

                <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 10px; padding: 18px; margin: 18px 0;">
                    <p style="margin: 0; font-size: 15px; line-height: 1.65; color: #1E293B;">
                        {summary_text}
                    </p>
                </div>

                {callout_box_html}

                <div style="border: 1px solid #E2E8F0; border-radius: 10px; overflow: hidden; margin: 22px 0;">
                    <div style="background: #0F766E; padding: 10px 16px; font-size: 12.5px; font-weight: 800; text-transform: uppercase; color: #FFFFFF;">
                        Taarifa Fupi za Mzigo Wako
                    </div>
                    <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                        <tr style="border-bottom: 1px solid #F1F5F9;">
                            <td style="padding: 10px 16px; color: #64748B; width: 40%;">Mteja:</td>
                            <td style="padding: 10px 16px; font-weight: 700; color: #0F172A;">{customer_name}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #F1F5F9; background: #F8FAFC;">
                            <td style="padding: 10px 16px; color: #64748B;">Mzigo / Gari:</td>
                            <td style="padding: 10px 16px; font-weight: 700; color: #0F172A;">{context_vars['cargo_desc']}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #F1F5F9;">
                            <td style="padding: 10px 16px; color: #64748B;">Namba ya B/L:</td>
                            <td style="padding: 10px 16px; font-family: monospace; font-weight: 700; color: #1E3A8A;">{context_vars['bl_number']}</td>
                        </tr>
                        <tr style="background: #F8FAFC;">
                            <td style="padding: 10px 16px; color: #64748B;">Namba ya Chassis:</td>
                            <td style="padding: 10px 16px; font-family: monospace; font-weight: 700; color: #0F172A;">{context_vars['chassis_number']}</td>
                        </tr>
                    </table>
                </div>

                <div style="background: #F0FDF4; border: 1px solid #BBF7D0; border-radius: 8px; padding: 14px 16px; margin: 20px 0;">
                    <div style="font-size: 13.5px; font-weight: 700; color: #166534; margin-bottom: 4px;">
                        Cha Kufanya Sasa:
                    </div>
                    <div style="font-size: 14px; color: #14532D; line-height: 1.55;">
                        {action_note}
                    </div>
                </div>

                <div style="margin-top: 24px; padding-top: 18px; border-top: 1px solid #E2E8F0; font-size: 14px; color: #334155;">
                    Karibu sana,<br>
                    <strong>{COMPANY_OFFICIAL_NAME}</strong><br>
                    <span style="font-size: 12.5px; color: #64748B;">Dar es Salaam, Tanzania</span>
                </div>
            </div>

            <div style="background: #F8FAFC; border-top: 1px solid #E2E8F0; padding: 14px; text-align: center; font-size: 12px; color: #64748B;">
                &copy; 2026 {COMPANY_OFFICIAL_NAME}.
            </div>
        </div>
    </body>
    </html>
    """

    # 1. Send Email via Resend
    email_ok, email_info = send_resend_email(customer_email, subject, html_content, text_content=summary_text)

    # 2. Send SMS via SMS Gate / NextSMS
    sms_ok, sms_info = send_nextsms_sms(customer_phone, sms_text, reference=f"{milestone_key}_{job.id}_{int(time.time())}")

    print(f"[Client Milestone Notification: {milestone_key}] B/L {context_vars['bl_number']} -> Email: {email_ok} ({email_info}) | SMS: {sms_ok} ({sms_info})")
    return {
        'email_ok': email_ok,
        'email_info': email_info,
        'sms_ok': sms_ok,
        'sms_info': sms_info,
        'sms_text': sms_text,
    }


def send_stage_update_email(job, stage_number, extra_note=''):
    if stage_number == 1:
        milestone_key = 'DOCS_RECEIVED'
    elif stage_number in [3, 4] and not job.duty_paid:
        milestone_key = 'TRA_DUTY_ISSUED'
    elif stage_number == 8 or job.vehicle_arrived_at_office:
        milestone_key = 'PORT_EXIT_YARD_ARRIVAL'
    else:
        return True, "Hatua hii haitumi ujumbe kwa mteja (ujumbe hutumwa kwenye hatua 3 kuu pekee)."

    res = notify_client_milestone(job, milestone_key, extra_note=extra_note)
    any_ok = res['email_ok'] or res['sms_ok']
    summary = f"Email: {res['email_info']} | SMS: {res['sms_info']}"
    return any_ok, summary


def send_declarer_intake_notification(job, declarer):
    if not declarer:
        return False, "Hakuna Customs Declarer aliyepatikana."
    recipient = (declarer.email or '').strip()
    if not recipient:
        return False, f"Declarer {declarer.username} hana barua pepe."

    received = ", ".join(name for name, ok in job.received_docs_checklist if ok) or "Hakuna"
    subject = f"Faili Mpya kwa Declaration (B/L: {job.bl_number or job.job_number}) - {COMPANY_OFFICIAL_NAME}"
    summary = (
        f"Faili jipya limepokelewa kutoka Documentation. "
        f"B/L: {job.bl_number or 'N/A'} | Mteja: {job.customer.company_name}. "
        f"Nyaraka zilizopokelewa: {received}."
    )
    html_content = f"""
    <div style="font-family: Arial, sans-serif; background:#F1F5F9; padding:24px;">
        <div style="max-width:600px; margin:0 auto; background:#FFFFFF; border:1px solid #E2E8F0; border-radius:12px; overflow:hidden;">
            <div style="background:#0F766E; color:#FFFFFF; padding:20px 24px;">
                <div style="font-size:11px; letter-spacing:.12em; text-transform:uppercase; color:#99F6E4;">{COMPANY_OFFICIAL_NAME}</div>
                <h2 style="margin:6px 0 0; font-size:19px;">Faili Mpya kwa Customs Declaration</h2>
            </div>
            <div style="padding:24px; color:#1E293B; font-size:14px; line-height:1.6;">
                <p>Habari <strong>{declarer.get_full_name() or declarer.username}</strong>,</p>
                <p>Documentation Officer amekamilisha upokeaji wa nyaraka na kupeleka faili hili kwako kwa ajili ya kuwasilisha tamko la forodha.</p>
                <table style="width:100%; border-collapse:collapse; margin:16px 0; font-size:13.5px;">
                    <tr><td style="padding:8px 0; color:#64748B; width:38%;">B/L Number:</td><td style="padding:8px 0; font-weight:700;">{job.bl_number or 'N/A'}</td></tr>
                    <tr><td style="padding:8px 0; color:#64748B;">Mteja:</td><td style="padding:8px 0;">{job.customer.company_name}</td></tr>
                    <tr><td style="padding:8px 0; color:#64748B;">Nyaraka:</td><td style="padding:8px 0;">{received}</td></tr>
                </table>
            </div>
        </div>
    </div>
    """
    ok, result = send_resend_email(recipient, subject, html_content, text_content=summary)
    return ok, result
