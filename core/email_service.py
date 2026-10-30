import os
import requests
from django.conf import settings
from django.core.mail import EmailMultiAlternatives

RESEND_API_URL = "https://api.resend.com/emails"

def get_resend_api_key():
    from .models import SystemConfig
    db_val = SystemConfig.get_value('RESEND_API_KEY', '')
    if db_val:
        return db_val
    return getattr(settings, 'RESEND_API_KEY', '') or os.getenv('RESEND_API_KEY', '')

def get_resend_from_email():
    """
    Returns the formatted from address.
    e.g. 'Malkia Freight & Logistics <info@nyisu.com>'
    """
    from .models import SystemConfig
    display_name = SystemConfig.get_value('RESEND_SENDER_NAME', '') or getattr(settings, 'RESEND_SENDER_NAME', 'Malkia Freight & Logistics')
    from_address = SystemConfig.get_value('RESEND_FROM_EMAIL', '') or getattr(settings, 'RESEND_FROM_EMAIL', 'info@nyisu.com')
    return f"{display_name} <{from_address}>"

def send_resend_email(to_email, subject, html_content, text_content=None, reply_to=None):
    """
    Sends email via Resend API (Primary).
    If Resend fails or is rate-limited, automatically falls back to Gmail SMTP.
    Returns (success: bool, response_info: str)
    """
    api_key = get_resend_api_key()
    from_sender = get_resend_from_email()
    recipients = [to_email] if isinstance(to_email, str) else to_email

    # 1. Attempt delivery via Resend API (Primary)
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
                return True, f"Imetumwa kwa mafanikio kupitia Resend (ID: {msg_id}) kwa jina la '{from_sender}'"
            else:
                resend_err = f"Resend Error [{response.status_code}]: {response.text}"
                print(f"[Email Service] Resend failed: {resend_err}. Trying SMTP fallback...")
        except Exception as e:
            resend_err = f"Resend connection failed: {str(e)}"
            print(f"[Email Service] {resend_err}. Trying SMTP fallback...")
    else:
        resend_err = "RESEND_API_KEY haijawekwa."

    # 2. Attempt delivery via SMTP Fallback (Gmail)
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
        return True, f"Imetumwa kwa mafanikio kupitia Gmail SMTP Fallback ({smtp_sender})"
    except Exception as smtp_err:
        return False, f"Resend imeshindwa ({resend_err}) na SMTP Fallback imeshindwa pia: {str(smtp_err)}"


# =========================================================================
# WORKFLOW STAGE EMAIL TEMPLATES (SWAHILI, CUSTOMER-FRIENDLY, NO STAGE NUMBERS)
# =========================================================================
STAGE_NOTIFICATION_TEMPLATES = {
    1: {
        "status_badge": "Nyaraka Zimepokelewa & Ukaguzi wa Awali Umeanza",
        "badge_color": "#2563EB",
        "subject": "Taarifa ya Mzigo: Tumepokea Nyaraka Zako za Mzigo - {job_number}",
        "summary": "Tumepokea kwa ufanisi nyaraka zote za mzigo wako. Timu yetu ya forodha imeanza ukaguzi wa awali (Documentary Verification) ili kuanza taratibu za kisheria za kuondoa mzigo wako mara moja.",
        "action_note": "Hakuna hatua inayohitajika kutoka kwako kwa sasa. Tutakujulisha mara tu faili litakapofunguliwa na kusajiliwa rasmi.",
    },
    2: {
        "status_badge": "Faili la Mzigo Limefunguliwa Rasmi",
        "badge_color": "#0284C7",
        "subject": "Faili la Mzigo Wako Limefunguliwa Rasmi - {job_number}",
        "summary": "Faili rasmi la kielektroniki la mzigo wako limefunguliwa na kusajiliwa chini ya namba ya kumbukumbu {job_number}. Nyaraka zako zote zimepangwa tayari kwa kuwasilisha tamko la forodha (Customs Declaration).",
        "action_note": "Taratibu za kuwasilisha tamko kwenye mfumo wa TRA TANCIS zinaendelea.",
    },
    3: {
        "status_badge": "Tamko la Forodha Limewasilishwa (TANCIS Declaration)",
        "badge_color": "#D97706",
        "subject": "Tamko la Forodha Limewasilishwa TRA TANCIS - {job_number}",
        "summary": "Tamko rasmi la forodha (Single Goods Declaration) limewasilishwa kwenye mfumo wa TRA TANCIS chini ya Entry No: {declaration_number}. Mfumo wa forodha wa TRA sasa unakamilisha tathmini ya kodi (Assessment).",
        "action_note": "Tathmini ya kodi (Assessment Notice) itatolewa hivi punde ikiwa na GePG Control Number.",
    },
    4: {
        "status_badge": "Inasubiri Malipo ya Kodi ya Forodha (TRA GePG)",
        "badge_color": "#DC2626",
        "subject": "Taarifa ya Malipo ya Kodi ya Forodha (TRA) - {job_number}",
        "summary": "Tathmini ya kodi ya forodha kutoka TRA imekamilika rasmi. Kiasi cha kodi kinachotakiwa kulipwa moja kwa moja TRA ni TSh {assessed_duty} chini ya GePG Control Number: {duty_control_number}.",
        "action_note": "Tafadhali fanya malipo ya kodi hiyo moja kwa moja TRA kupitia Benki au GePG Mobile Money (M-Pesa, TigoPesa, Airtel Money) kwa kutumia Control Number hapo juu. Baada ya kulipa, tafadhali tutumie risiti ya TRA ili tuanze ukaguzi wa mzigo bandarini mara moja.",
    },
    5: {
        "status_badge": "Uhakiki na Ukaguzi wa Mzigo Unaendelea Bandarini",
        "badge_color": "#7C3AED",
        "subject": "Uhakiki wa Mzigo Wako Unaendelea Bandarini / ICD - {job_number}",
        "summary": "Malipo ya kodi ya forodha ya TRA yamethibitishwa. Maafisa wetu wa uwanjani wapo bandarini / ICD wakishirikiana na maafisa wa forodha (TRA) kwa ajili ya ukaguzi wa pamoja wa mzigo wako (Physical Verification & Inspection).",
        "action_note": "Timu yetu inafuatilia ukaguzi huu ili kukamilisha taratibu kwa haraka bila ucheleweshaji wowote.",
    },
    6: {
        "status_badge": "Kibali cha Meli (Delivery Order) Kinafuatiliwa",
        "badge_color": "#2563EB",
        "subject": "Upatikanaji wa Kibali cha Meli (Delivery Order) - {job_number}",
        "summary": "Kibali cha kutoa mzigo (Delivery Order - DO) kinafuatiliwa na kukamilishwa kutoka kwa wakala wa meli ({shipping_line}) ili kuruhusu kontena lako kuwa tayari kutolewa.",
        "action_note": "Taratibu za kutoa DO zinaendelea na wakala husika wa meli.",
    },
    7: {
        "status_badge": "Kibali Rasmi cha Forodha Kimeidhinishwa (Customs Release)",
        "badge_color": "#059669",
        "subject": "Kibali Rasmi cha Forodha Kimepatikana (Release Order) - {job_number}",
        "summary": "Habari njema! Mzigo wako umekamilisha taratibu zote za kiukaguzi na forodha (TRA) imetoa Kibali Rasmi cha Kuruhusu Mzigo (Customs Release Order).",
        "action_note": "Mzigo sasa uko huru forodhani na unaelekea hatua za mwisho za bandari na upakiaji.",
    },
    8: {
        "status_badge": "Ankara ya Bandari Imepokelewa (TPA Port Invoice)",
        "badge_color": "#D97706",
        "subject": "Ankara ya Gharama za Bandari Imepokelewa - {job_number}",
        "summary": "Ankara rasmi ya bandari (TPA / TICTS Wharfage & Handling) imepokelewa na kuingizwa kwenye mfumo kwa ajili ya usindikaji wa malipo.",
        "action_note": "Malipo ya bandari yanafanyiwa maandalizi ya haraka ili kuruhusu mzigo kutoka.",
    },
    9: {
        "status_badge": "Gharama za Bandari Zimelipwa (Port Charges Settled)",
        "badge_color": "#059669",
        "subject": "Gharama za Bandari Zimelipwa - {job_number}",
        "summary": "Gharama zote za bandari za TPA na ICD zimelipwa kikamilifu. Uthibitisho wa malipo umekamilika na hatua za kutoa kontena getini zimeanza.",
        "action_note": "Maandalizi ya lori na Gate Pass yanaendelea ili kuanza safari.",
    },
    10: {
        "status_badge": "Gate Pass Imepatikana & Kontena Limepakiwa Kwenye Lori",
        "badge_color": "#0284C7",
        "subject": "Gate Pass Imepatikana & Kontena Linasafirishwa - {job_number}",
        "summary": "Gate Pass rasmi ya kutoka getini imetolewa. Kontena lako limepakiwa salama kwenye lori (Namba ya Lori: {truck_number}) na kuanza safari kuelekea eneo lako la kupokelea mzigo ({destination}).",
        "action_note": "Dereva yuko safarini kuelekea eneo lako. Mzigo unatarajiwa kuwasili hivi punde.",
    },
    11: {
        "status_badge": "Mzigo Umewasili Salama & Umekabidhiwa (Delivered)",
        "badge_color": "#059669",
        "subject": "Mzigo Wako Umefikishwa Salama (Delivered & Closed) - {job_number}",
        "summary": "Tunayo furaha kukutaarifu kwamba mzigo wako umewasili salama eneo lako na kukabidhiwa rasmi (Proof of Delivery - POD). Utoaji wa huduma umekamilika kwa mafanikio makubwa.",
        "action_note": "Asante sana kwa kuichagua Malkia Freight & Logistics. Tunatarajia kuendelea kukuhudumia tena kwa ufanisi wa hali ya juu!",
    },
}


def send_stage_update_email(job, stage_number, extra_note=''):
    """
    Sends an automated, elegant, professional Swahili email notification to the client
    whenever their shipment progresses to a new milestone.
    Does NOT expose stage numbers; focuses purely on clear real-world status.
    """
    tmpl = STAGE_NOTIFICATION_TEMPLATES.get(stage_number)
    if not tmpl:
        return False, f"Hakuna template ya hatua namba {stage_number}"

    customer = job.customer
    customer_name = customer.company_name if customer else "Mteja Mpendwa"
    contact_person = customer.contact_person if (customer and customer.contact_person) else customer_name

    # Determine recipient
    primary_email = customer.email.strip() if (customer and customer.email) else ''
    default_test_email = getattr(settings, 'DEFAULT_TEST_EMAIL', '') or os.getenv('DEFAULT_TEST_EMAIL', '')

    if not primary_email:
        recipients = [default_test_email]
    else:
        recipients = [primary_email]
        if default_test_email not in recipients:
            recipients.append(default_test_email)

    # Format values
    fmt_duty = f"{job.assessed_duty_amount:,.2f}" if job.assessed_duty_amount else "0.00"
    vessel_display = f"{job.vessel_name or 'N/A'}"
    if job.voyage_number:
        vessel_display += f" (Voyage: {job.voyage_number})"

    truck_disp = job.truck_number or "Inasajiliwa"
    dest_disp = job.final_destination or "Dar es Salaam"

    context_vars = {
        "job_number": job.job_number,
        "bl_number": job.bl_number,
        "declaration_number": job.declaration_number or "Inasubiri Entry",
        "assessed_duty": fmt_duty,
        "duty_control_number": job.duty_control_number or "Inasubiri GePG",
        "shipping_line": job.get_shipping_line_display() if hasattr(job, 'get_shipping_line_display') else job.shipping_line,
        "vessel_name": vessel_display,
        "truck_number": truck_disp,
        "destination": dest_disp,
        "customer_name": customer_name,
        "contact_person": contact_person,
    }

    subject = tmpl["subject"].format(**context_vars)
    summary_text = tmpl["summary"].format(**context_vars)
    action_note = tmpl["action_note"].format(**context_vars)
    status_badge = tmpl["status_badge"]
    badge_color = tmpl["badge_color"]

    # Special GePG callout box for Duty Payment
    gepg_box_html = ""
    if stage_number == 4 and job.duty_control_number:
        gepg_box_html = f"""
        <div style="background: #FEF2F2; border: 2px dashed #EF4444; border-radius: 10px; padding: 18px; margin: 20px 0; text-align: center;">
            <div style="font-size: 13px; font-weight: 700; color: #991B1B; text-transform: uppercase; letter-spacing: 0.05em;">
                TRA GePG Control Number (Namba ya Malipo):
            </div>
            <div style="font-family: monospace; font-size: 26px; font-weight: 800; color: #7F1D1D; letter-spacing: 0.1em; margin: 8px 0;">
                {job.duty_control_number}
            </div>
            <div style="font-size: 15px; font-weight: 700; color: #166534; background: #DCFCE7; display: inline-block; padding: 6px 14px; border-radius: 6px;">
                Kiasi cha Kodi: TSh {fmt_duty}
            </div>
            <div style="font-size: 12px; color: #64748B; margin-top: 10px;">
                Lipa kupitia Benki zote au Mobile Money (M-Pesa, TigoPesa, Airtel Money) chini ya Huduma za Serikali (GePG).
            </div>
        </div>
        """

    extra_note_html = ""
    if extra_note:
        extra_note_html = f"""
        <div style="background: #F8FAFC; border-left: 4px solid #64748B; padding: 10px 14px; margin: 15px 0; font-size: 13px; color: #334155;">
            <strong>Maelezo ya Ziada kutoka kwa Afisa Wetu:</strong> {extra_note}
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
        <div style="max-width: 620px; margin: 0 auto; background: #FFFFFF; border-radius: 14px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.06); border: 1px solid #E2E8F0;">
            
            <!-- HEADER -->
            <div style="background: linear-gradient(135deg, #0F172A 0%, #1E3A8A 100%); color: #FFFFFF; padding: 28px 24px; text-align: center;">
                <div style="font-size: 11px; font-weight: 800; letter-spacing: 0.15em; text-transform: uppercase; color: #93C5FD; margin-bottom: 6px;">
                    Malkia Freight &amp; Forwarding Logistics Ltd
                </div>
                <h1 style="font-size: 22px; font-weight: 800; margin: 0; letter-spacing: -0.02em;">
                    Taarifa ya Maendeleo ya Mzigo Wako
                </h1>
                <div style="font-size: 13px; color: #CBD5E1; margin-top: 6px;">
                    Job Ref: <strong style="color: #FFFFFF; font-family: monospace;">{job.job_number}</strong> &bull; B/L: <strong style="color: #FFFFFF; font-family: monospace;">{job.bl_number}</strong>
                </div>
            </div>

            <!-- BODY -->
            <div style="padding: 28px 24px;">
                <p style="font-size: 15px; margin-top: 0; color: #334155;">
                    Habari <strong>{contact_person}</strong>,
                </p>

                <!-- STATUS BADGE -->
                <div style="margin: 20px 0; text-align: center;">
                    <span style="display: inline-block; background: {badge_color}; color: #FFFFFF; padding: 8px 18px; border-radius: 50px; font-weight: 700; font-size: 13px; letter-spacing: 0.02em; box-shadow: 0 2px 6px rgba(0,0,0,0.15);">
                        {status_badge}
                    </span>
                </div>

                <!-- SUMMARY -->
                <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 10px; padding: 18px; margin: 20px 0;">
                    <p style="margin: 0; font-size: 14.5px; line-height: 1.6; color: #1E293B;">
                        {summary_text}
                    </p>
                </div>

                {gepg_box_html}
                {extra_note_html}

                <!-- SHIPMENT DETAILS CARD -->
                <div style="border: 1px solid #E2E8F0; border-radius: 10px; overflow: hidden; margin: 24px 0;">
                    <div style="background: #F1F5F9; padding: 10px 16px; font-size: 12px; font-weight: 800; text-transform: uppercase; color: #475569; letter-spacing: 0.05em;">
                        Muhtasari wa Mzigo (Consignment Summary)
                    </div>
                    <table style="width: 100%; border-collapse: collapse; font-size: 13.5px;">
                        <tr style="border-bottom: 1px solid #F1F5F9;">
                            <td style="padding: 10px 16px; color: #64748B; width: 40%;">Mteja / Mwagizaji:</td>
                            <td style="padding: 10px 16px; font-weight: 700; color: #0F172A;">{customer_name}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #F1F5F9;">
                            <td style="padding: 10px 16px; color: #64748B;">Bill of Lading (B/L):</td>
                            <td style="padding: 10px 16px; font-family: monospace; font-weight: 700; color: #1E3A8A;">{job.bl_number}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #F1F5F9;">
                            <td style="padding: 10px 16px; color: #64748B;">Meli &amp; Safari:</td>
                            <td style="padding: 10px 16px; color: #0F172A;">{vessel_display}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #F1F5F9;">
                            <td style="padding: 10px 16px; color: #64748B;">Maelezo ya Mzigo:</td>
                            <td style="padding: 10px 16px; color: #0F172A;">{job.cargo_description or 'General Merchandise'}</td>
                        </tr>
                        <tr>
                            <td style="padding: 10px 16px; color: #64748B;">Eneo la Mwisho:</td>
                            <td style="padding: 10px 16px; font-weight: 600; color: #0F172A;">{dest_disp}</td>
                        </tr>
                    </table>
                </div>

                <!-- ACTION NOTE -->
                <div style="background: #F0FDF4; border: 1px solid #BBF7D0; border-radius: 8px; padding: 14px 16px; margin: 20px 0;">
                    <div style="font-size: 13px; font-weight: 700; color: #166534; margin-bottom: 4px;">
                        Hatua Inayofuata:
                    </div>
                    <div style="font-size: 13.5px; color: #14532D; line-height: 1.5;">
                        {action_note}
                    </div>
                </div>

                <p style="font-size: 13.5px; color: #64748B; margin-top: 24px;">
                    Ukiwa na swali lolote kuhusu mzigo huu, timu yetu ya operesheni iko tayari kukuhudumia saa 24/7 kupitia namba zetu za simu au barua pepe hii.
                </p>

                <div style="margin-top: 24px; padding-top: 18px; border-top: 1px solid #E2E8F0; font-size: 13.5px; color: #334155;">
                    Wako katika Ujenzi wa Taifa,<br>
                    <strong>Timu ya Operesheni &bull; Malkia Freight &amp; Logistics</strong><br>
                    <span style="font-size: 12px; color: #64748B;">Dar es Salaam Port Commercial Hub, Tanzania</span>
                </div>
            </div>

            <!-- FOOTER -->
            <div style="background: #F8FAFC; border-top: 1px solid #E2E8F0; padding: 18px; text-align: center; font-size: 12px; color: #64748B;">
                &copy; 2026 Malkia Freight &amp; Forwarding Logistics Ltd. Haki zote zimehifadhiwa.<br>
                Barua pepe hii imetumwa moja kwa moja kutoka kwenye Mfumo Rasmi wa Malkia C&amp;F Management System.
            </div>
        </div>
    </body>
    </html>
    """

    ok, result = send_resend_email(recipients, subject, html_content, text_content=summary_text)
    print(f"[Stage Notification] Stage {stage_number} email sent to {recipients}: {ok} -> {result}")
    return ok, result


def send_declarer_intake_notification(job, declarer):
    """
    Notifies the Customs Declarer that Documentation has handed over a new file
    directly for TRA TANESW & TBS declaration (no Operations approval step).
    """
    if not declarer:
        return False, "Hakuna Customs Declarer aliyepatikana."
    recipient = (declarer.email or '').strip()
    if not recipient:
        return False, f"Declarer {declarer.username} hana barua pepe."

    received = ", ".join(name for name, ok in job.received_docs_checklist if ok) or "Hakuna"
    subject = f"Faili Mpya kwa TANESW/TBS Declaration - {job.job_number}"
    summary = (
        f"Faili jipya limepokelewa moja kwa moja kutoka Documentation. "
        f"Job Ref: {job.job_number} | B/L: {job.bl_number or 'N/A'} | Mteja: {job.customer.company_name}. "
        f"Nyaraka zilizopokelewa: {received}. Tafadhali lodge TANESW/TBS kwenye module ya TANCIS Declarations."
    )
    html_content = f"""
    <div style="font-family: Arial, sans-serif; background:#F1F5F9; padding:24px;">
        <div style="max-width:600px; margin:0 auto; background:#FFFFFF; border:1px solid #E2E8F0; border-radius:12px; overflow:hidden;">
            <div style="background:#0B152B; color:#FFFFFF; padding:20px 24px;">
                <div style="font-size:11px; letter-spacing:.12em; text-transform:uppercase; color:#93C5FD;">Malkia Freight &amp; Logistics</div>
                <h2 style="margin:6px 0 0; font-size:19px;">Faili Mpya kwa TANESW/TBS Declaration</h2>
            </div>
            <div style="padding:24px; color:#1E293B; font-size:14px; line-height:1.6;">
                <p>Habari <strong>{declarer.get_full_name() or declarer.username}</strong>,</p>
                <p>Documentation Officer amekamilisha upokeaji wa nyaraka na kupeleka faili hili moja kwa moja kwako kwa ajili ya tamko la forodha (TRA TANESW &amp; TBS).</p>
                <table style="width:100%; border-collapse:collapse; margin:16px 0; font-size:13.5px;">
                    <tr><td style="padding:8px 0; color:#64748B; width:38%;">Job Ref:</td><td style="padding:8px 0; font-weight:700;">{job.job_number}</td></tr>
                    <tr><td style="padding:8px 0; color:#64748B;">B/L Number:</td><td style="padding:8px 0; font-weight:700;">{job.bl_number or 'N/A'}</td></tr>
                    <tr><td style="padding:8px 0; color:#64748B;">Mteja:</td><td style="padding:8px 0;">{job.customer.company_name}</td></tr>
                    <tr><td style="padding:8px 0; color:#64748B;">Meli:</td><td style="padding:8px 0;">{job.vessel_name or 'N/A'}</td></tr>
                    <tr><td style="padding:8px 0; color:#64748B;">Clearance Mode:</td><td style="padding:8px 0;">{job.get_clearance_mode_display()}</td></tr>
                    <tr><td style="padding:8px 0; color:#64748B;">Nyaraka:</td><td style="padding:8px 0;">{received}</td></tr>
                </table>
                <div style="background:#EFF6FF; border:1px solid #BFDBFE; border-radius:8px; padding:14px; font-size:13.5px; color:#1E3A8A;">
                    Fungua <strong>Customs → TANCIS Declarations</strong> ili kulodge TANSAD/TANESW na TBS kwa faili hili.
                </div>
            </div>
            <div style="background:#F8FAFC; border-top:1px solid #E2E8F0; padding:14px 24px; font-size:12px; color:#64748B;">
                Taarifa hii imetumwa moja kwa moja kutoka Malkia C&amp;F Management System.
            </div>
        </div>
    </div>
    """
    ok, result = send_resend_email(recipient, subject, html_content, text_content=summary)
    print(f"[Declarer Notification] {job.job_number} -> {recipient}: {ok} -> {result}")
    return ok, result
