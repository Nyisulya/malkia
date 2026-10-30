import json
import logging
import datetime
import requests
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from django.db.models import Sum, Q

logger = logging.getLogger(__name__)

# ── DEFINISHO ZA ZANA (TOOLS / FUNCTION CALLING SCHEMAS) ──
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_financials",
            "description": "Hupata takwimu za fedha, mapato (invoiced na collected), na matumizi kwa kipindi (today, yesterday, juzi, this_month, last_month, all_time, au tarehe YYYY-MM-DD).",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": "today, yesterday, juzi, this_month, last_month, all_time, au tarehe kama 2026-09-25",
                        "default": "all_time"
                    }
                },
                "required": ["period"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_jobs",
            "description": "Searches and lists freight forwarding and clearance jobs by status (active, delayed, completed, all), client name, job number (e.g. CF/2026/0001), or cargo description.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["active", "delayed", "completed", "all"],
                        "description": "Shipment status: active, delayed, completed, or all",
                        "default": "active"
                    },
                    "search_query": {
                        "type": "string",
                        "description": "Client company name, job number, or B/L number (e.g. 'TCRA', '0001', 'MIELIA')",
                        "default": ""
                    },
                    "period": {
                        "type": "string",
                        "description": "today, yesterday, this_month, last_month, all_time",
                        "default": "all_time"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_containers_and_demurrage",
            "description": "Retrieves container status: at port (at_port), demurrage/overdue (overdue), in transit (in_transit), or empty returned.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filter_type": {
                        "type": "string",
                        "enum": ["all", "overdue", "at_port", "in_transit", "returned"],
                        "description": "Container group to inspect",
                        "default": "all"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_debtors",
            "description": "Lists all customers with outstanding accounts receivable balances, amount owed, contact details, and active shipment count.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_staff_and_fleet",
            "description": "Displays workforce attendance (present, late) and heavy fleet dispatch status (available, in transit, maintenance).",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": "today, yesterday, or YYYY-MM-DD",
                        "default": "today"
                    }
                }
            }
        }
    }
]


# ── UTENDAJI WA ZANA ZA DATABASE (TOOL EXECUTION ENGINE) ──
def execute_database_tool(name: str, args: dict):
    """
    Hutekeleza kazi maalum ya kusoma database kulingana na zana aliyoichagua DeepSeek.
    """
    from core.models import (
        JobShipment, JobContainer, Customer, ClientInvoice,
        ClientPayment, ExpenseVoucher, UserProfile, FleetVehicle, StaffAttendance
    )

    today = timezone.now().date()

    # 1. ZANA YA FEDHA (GET FINANCIALS)
    if name == "get_financials":
        period = (args.get("period") or "all_time").lower().strip()
        d_start, d_end = None, None

        if period in ["today", "leo"]:
            d_start, d_end = today, today
        elif period in ["yesterday", "jana"]:
            y = today - datetime.timedelta(days=1)
            d_start, d_end = y, y
        elif period in ["juzi", "day_before_yesterday"]:
            j = today - datetime.timedelta(days=2)
            d_start, d_end = j, j
        elif period in ["this_month", "mwezi_huu"]:
            d_start, d_end = today.replace(day=1), today
        elif period in ["last_month", "mwezi_uliopita"]:
            first_this = today.replace(day=1)
            d_end = first_this - datetime.timedelta(days=1)
            d_start = d_end.replace(day=1)
        else:
            # Jaribu kusoma tarehe maalum YYYY-MM-DD
            try:
                parsed_d = datetime.date.fromisoformat(period)
                d_start, d_end = parsed_d, parsed_d
            except Exception:
                d_start, d_end = None, None

        pay = ClientPayment.objects.all()
        inv = ClientInvoice.objects.all()
        exp = ExpenseVoucher.objects.all()

        if d_start and d_end:
            pay = pay.filter(payment_date__gte=d_start, payment_date__lte=d_end)
            inv = inv.filter(created_at__date__gte=d_start, created_at__date__lte=d_end)
            exp = exp.filter(paid_at__date__gte=d_start, paid_at__date__lte=d_end, is_paid=True)

        tot_inv = inv.aggregate(t=Sum("total_amount"))["t"] or Decimal("0")
        tot_pay = pay.aggregate(t=Sum("amount"))["t"] or Decimal("0")
        tot_exp = exp.aggregate(t=Sum("amount"))["t"] or Decimal("0")
        margin = tot_pay - tot_exp

        # Kama all_time, weka na madeni ya jumla
        outstanding = None
        if not d_start:
            all_customers = Customer.objects.all()
            total_debt = sum([c.outstanding_balance for c in all_customers])
            outstanding = f"TSh {total_debt:,.0f}"

        res = {
            "period": period,
            "tarehe": f"{d_start} hadi {d_end}" if d_start else "Muda wote (All Time)",
            "mapato_yaliyokusanywa": f"TSh {tot_pay:,.0f}",
            "ankara_zilizotolewa": f"TSh {tot_inv:,.0f}",
            "gharama_zilizolipwa": f"TSh {tot_exp:,.0f}",
            "ziada_faida_taslimu": f"TSh {margin:,.0f}"
        }
        if outstanding:
            res["madeni_ya_wateja_yaliyobaki"] = outstanding
        return res

    # 2. ZANA YA KAZI (GET JOBS)
    elif name == "get_jobs":
        status = (args.get("status") or "active").lower()
        query = (args.get("search_query") or "").strip()
        period = (args.get("period") or "").lower()

        qs = JobShipment.objects.select_related("customer").order_by("-created_at")

        if status == "active":
            qs = qs.filter(status__in=["ACTIVE", "DELAYED"])
        elif status == "delayed":
            qs = qs.filter(status="DELAYED")
        elif status == "completed":
            qs = qs.filter(status="COMPLETED")

        if query:
            qs = qs.filter(
                Q(customer__company_name__icontains=query) |
                Q(job_number__icontains=query) |
                Q(bl_number__icontains=query) |
                Q(cargo_description__icontains=query)
            )

        if period in ["today", "leo"]:
            qs = qs.filter(created_at__date=today)
        elif period in ["yesterday", "jana"]:
            y = today - datetime.timedelta(days=1)
            qs = qs.filter(created_at__date=y)
        elif period in ["this_month", "mwezi_huu"]:
            qs = qs.filter(created_at__date__gte=today.replace(day=1))
        elif period in ["last_month", "mwezi_uliopita"]:
            first_this = today.replace(day=1)
            last_end = first_this - datetime.timedelta(days=1)
            qs = qs.filter(created_at__date__gte=last_end.replace(day=1), created_at__date__lte=last_end)

        job_list = []
        for j in qs[:10]:
            curr_obj = j.current_stage_obj
            stage_name = curr_obj.stage_definition.name_en if curr_obj and curr_obj.stage_definition else f"Stage {j.current_stage_number}"
            job_list.append({
                "job_number": j.job_number,
                "client": j.customer.company_name,
                "bl_number": j.bl_number,
                "cargo": j.cargo_description[:40],
                "status": j.status,
                "stage": f"{stage_name} ({j.current_stage_number}/11)",
                "vessel": j.vessel_name or "N/A",
                "eta": str(j.eta_arrival_date) if j.eta_arrival_date else "N/A",
                "contracted_revenue": f"TSh {j.contracted_revenue:,.0f}"
            })

        return {
            "total_found": len(job_list),
            "jobs": job_list if job_list else "No jobs found matching these criteria."
        }

    # 3. ZANA YA MAKONTENA (GET CONTAINERS)
    elif name == "get_containers_and_demurrage":
        ftype = (args.get("filter_type") or "all").lower()
        conts = list(JobContainer.objects.select_related("job", "job__customer").all())

        at_port = [c for c in conts if c.status == "AT_PORT"]
        in_transit = [c for c in conts if c.status in ["LOADED", "IN_TRANSIT"]]
        delivered = [c for c in conts if c.status == "DELIVERED"]
        returned = [c for c in conts if c.status == "EMPTY_RETURNED"]
        overdue = [c for c in conts if c.is_detention_overdue]

        if ftype == "overdue":
            overdue_details = [
                f"Container #{c.container_number} ({c.job.job_number} - {c.job.customer.company_name}): exceeded by {c.detention_overdue_days} days!"
                for c in overdue
            ]
            return {
                "total_overdue_containers": len(overdue),
                "details": overdue_details if overdue_details else "No containers currently exceed free days (Zero Demurrage)."
            }

        return {
            "total_containers": len(conts),
            "at_port": len(at_port),
            "in_transit": len(in_transit),
            "delivered": len(delivered),
            "empty_returned": len(returned),
            "demurrage_overdue": len(overdue)
        }

    # 4. ZANA YA MADENI YA WATEJA (GET DEBTORS)
    elif name == "get_debtors":
        customers = Customer.objects.all()
        debtor_list = []
        for c in customers:
            bal = c.outstanding_balance
            if bal > 0:
                debtor_list.append({
                    "customer": c.company_name,
                    "outstanding_balance": f"TSh {bal:,.0f}",
                    "phone": c.phone or "N/A",
                    "total_shipments": c.total_shipments_count
                })

        return {
            "total_debtors": len(debtor_list),
            "customers": debtor_list if debtor_list else "No customers have outstanding balances at this time."
        }

    # 5. ZANA YA WAFANYAKAZI NA MAGARI (GET STAFF AND FLEET)
    elif name == "get_staff_and_fleet":
        period = (args.get("period") or "today").lower()
        target_date = today
        if period in ["yesterday", "jana"]:
            target_date = today - datetime.timedelta(days=1)

        total_staff = UserProfile.objects.count()
        present = StaffAttendance.objects.filter(date=target_date, status__in=["PRESENT", "LATE"]).count()
        late = StaffAttendance.objects.filter(date=target_date, status="LATE").count()

        vehicles = list(FleetVehicle.objects.all())
        v_avail = sum(1 for v in vehicles if v.current_status == "AVAILABLE")
        v_transit = sum(1 for v in vehicles if v.current_status == "IN_TRANSIT")
        v_maint = sum(1 for v in vehicles if v.current_status == "MAINTENANCE")

        return {
            "date": str(target_date),
            "total_staff": total_staff,
            "present_today": present,
            "late_arrivals": late,
            "total_fleet": len(vehicles),
            "vehicles_available": v_avail,
            "vehicles_in_transit": v_transit,
            "vehicles_in_maintenance": v_maint
        }

    return {"error": f"Tool '{name}' unrecognized."}


# ── INJINI KUU YA MAZUNGUMZO (AGENT CHAT ENGINE) ──
def query_executive_ai(user_message: str, user=None, chat_history=None):
    """
    Hutumia DeepSeek V4.1 Flash (Hive AI) na Tool Calling.
    AI ina akili kamili ya kuhoji database kwa tarehe yoyote au mada yoyote.
    """
    api_key = getattr(settings, "HIVE_API_KEY", "") or os.getenv("HIVE_API_KEY", "")
    base_url = getattr(settings, "HIVE_BASE_URL", "https://api-cdn.thehive.ai/api/v3")
    model = getattr(settings, "HIVE_MODEL", "deepseek-ai/deepseek-v4.1-flash")

    user_name = (user.get_full_name() or user.username) if user else "Executive"
    today_str = timezone.now().strftime("%Y-%m-%d")

    system_prompt = f"""You are Malkia Executive AI, an intelligent executive assistant to the CEO / Managing Director ({user_name}) of Malkia Cargo Wave Ltd (Clearing & Forwarding).
Today's date is: {today_str}.

GUIDELINES:
1. Conversational Queries: If the user sends a greeting or general pleasantry (e.g., 'hello', 'good morning', 'how are you'), reply naturally, concisely, and professionally in English without invoking tools.
2. Tools Execution: When queried about business financials (today, yesterday, this month, or all-time), active jobs/shipments, containers & demurrage risks, outstanding client debts, staff attendance, or fleet status, ALWAYS invoke the appropriate database tool to retrieve accurate real-time data.
3. Language & Tone: Always respond in clear, smart, executive-level professional English. Be direct, structured, and informative with relevant metrics, without unnecessary fluff.
"""

    messages = [{"role": "system", "content": system_prompt}]

    # Clean conversation history
    if chat_history and isinstance(chat_history, list):
        for msg in chat_history[-4:]:
            if isinstance(msg, dict) and "role" in msg and "content" in msg:
                content = str(msg["content"])
                if "network" not in content.lower() and "error" not in content.lower():
                    messages.append({"role": msg["role"], "content": content[:600]})

    messages.append({"role": "user", "content": user_message})

    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 1. Step 1: Send to AI with Tools Schema
    payload_1 = {
        "model": model,
        "messages": messages,
        "tools": TOOLS_SCHEMA,
        "tool_choice": "auto",
        "max_tokens": 2000,
        "temperature": 0.3
    }

    try:
        response_1 = requests.post(endpoint, headers=headers, json=payload_1, timeout=30)
        if response_1.status_code != 200:
            logger.error(f"Hive AI error HTTP {response_1.status_code}: {response_1.text}")
            return {"status": "error", "reply": "Sorry, a network connection error occurred while querying the intelligence engine. Please try again.", "suggestions": []}

        data_1 = response_1.json()
        choice_1 = data_1.get("choices", [{}])[0]
        assistant_msg = choice_1.get("message", {})
        tool_calls = assistant_msg.get("tool_calls")

        # If no tools required (e.g. greeting or conversational)
        if not tool_calls:
            content = assistant_msg.get("content", "").strip()
            if not content:
                content = f"I am here, {user_name}. How may I assist you with Malkia operations today?"
            return {"status": "success", "reply": content, "suggestions": []}

        # 2. Hatua ya Pili: Tekeleza zana zilizoombwa kwenye Database
        messages.append(assistant_msg)
        for tc in tool_calls:
            tool_id = tc.get("id")
            func_name = tc.get("function", {}).get("name")
            args_str = tc.get("function", {}).get("arguments", "{}")
            try:
                fn_args = json.loads(args_str) if isinstance(args_str, str) else args_str
            except Exception:
                fn_args = {}

            logger.info(f"AI calling tool: {func_name} with args: {fn_args}")
            tool_output = execute_database_tool(func_name, fn_args)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "content": json.dumps(tool_output, default=str)
            })

        # 3. Hatua ya Tatu: Rejesha data kwa DeepSeek ili atunge jibu kamili
        payload_2 = {
            "model": model,
            "messages": messages,
            "max_tokens": 2500,
            "temperature": 0.4
        }

        response_2 = requests.post(endpoint, headers=headers, json=payload_2, timeout=35)
        if response_2.status_code == 200:
            data_2 = response_2.json()
            final_content = data_2.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            if not final_content:
                final_content = "Data retrieved from the database. Please specify if you need further analysis."
            return {"status": "success", "reply": final_content, "suggestions": []}
        else:
            logger.error(f"Hive AI step 2 error: {response_2.text}")
            return {"status": "error", "reply": "Data was retrieved but an error occurred while processing the analysis. Please try again.", "suggestions": []}

    except Exception as e:
        logger.exception(f"Error in query_executive_ai: {e}")
        return {"status": "error", "reply": f"Sorry {user_name}, a connectivity error occurred. Please try your request again.", "suggestions": []}


# ── CLIENT AI TOOLS & CHAT ENGINE ──

def find_job_in_client_query(message_text, customer=None):
    """
    Intelligently extracts and finds a JobShipment matching the user's query.
    Supports CF/YYYY/NNNN formats, 4-digit numbers, BL numbers, or container numbers.
    """
    import re
    from core.models import JobShipment

    if not message_text:
        return None

    clean = message_text.strip()

    # 1. Regex for CF/YYYY/NNNN or CF-YYYY-NNNN
    cf_match = re.search(r'CF[/\-_ ]\d{4}[/\-_ ]\d{4}', clean, re.IGNORECASE)
    if cf_match:
        token = cf_match.group(0).replace(' ', '/').replace('-', '/').replace('_', '/')
        job = JobShipment.objects.filter(job_number__iexact=token).first()
        if not job:
            job = JobShipment.objects.filter(job_number__icontains=token).first()
        return job

    # 2. Direct substring search against all jobs (e.g. matching full job_number in text)
    for job in JobShipment.objects.select_related('customer').all():
        if job.job_number.lower() in clean.lower():
            return job
        if job.bl_number and job.bl_number.lower() in clean.lower():
            return job

    # 3. Check 4-digit sequence like 0005, 0001, etc. (excluding years 2020-2030)
    year_numbers = {'2020', '2021', '2022', '2023', '2024', '2025', '2026', '2027', '2028', '2029', '2030'}
    digits_matches = [d for d in re.findall(r'\b\d{4}\b', clean) if d not in year_numbers]
    for digits in digits_matches:
        qs = JobShipment.objects.filter(job_number__endswith=digits)
        if not qs.exists():
            qs = JobShipment.objects.filter(job_number__icontains=digits)
        if customer:
            c_job = qs.filter(customer=customer).first()
            if c_job:
                return c_job
        job = qs.first()
        if job:
            return job

    return None





def query_client_ai(user_message: str, customer=None, chat_history=None):
    """
    Intelligent Conversational Client AI for Malkia Logistics.
    1. Converses naturally with clients exclusively in English.
    2. Answers queries, gives guidance on customs clearance and cargo logistics.
    3. Handles receipt submission workflows: prompts for Job Number and '+' attachment button.
    4. When Job Number is provided, retrieves full status and explains milestones accurately.
    5. Highly resilient: fallbacks ensure 100% uptime with zero error popups.
    """
    import re
    api_key = getattr(settings, "HIVE_API_KEY", "") or os.getenv("HIVE_API_KEY", "")
    base_url = getattr(settings, "HIVE_BASE_URL", "https://api-cdn.thehive.ai/api/v3")
    model = getattr(settings, "HIVE_MODEL", "deepseek-ai/deepseek-v4.1-flash")

    customer_name = customer.company_name if customer else "Valued Client"
    clean_msg = user_message.strip()

    # Step 1: Detect if user provided a job number in this message
    found_job = find_job_in_client_query(clean_msg, customer)

    # Intent detection
    is_asking_receipt = any(k in clean_msg.lower() for k in [
        'receipt', 'risiti', 'pay', 'paid', 'malipo', 'slip', 'gepg', 'control number',
        'upload', 'attach', 'submit', 'bank slip', 'tra'
    ])

    is_asking_tracking = any(k in clean_msg.lower() for k in [
        'where', 'track', 'status', 'shipment', 'cargo', 'stage', 'progress', 
        'arrived', 'container', 'b/l', 'bl', 'eta', 'wapi', 'mzigo'
    ])

    is_job_attempt = bool(re.search(r'CF[/\-_ ]\d{4}|\b\d{4}\b', clean_msg, re.IGNORECASE))

    # Prepare default responses if found_job exists
    direct_job_reply = None
    receipt_prompt_reply = None

    if found_job:
        stage_num = found_job.current_stage_number
        stage_en = found_job.current_stage_obj.name_en if found_job.current_stage_obj else f"Stage {stage_num}"
        duty_status = "✅ Paid & Settled (TRA Confirmed)" if found_job.duty_paid else f"⏳ Pending Payment (Assessed Duty: TZS {found_job.assessed_duty_amount:,.2f})"
        eta_str = found_job.eta_arrival_date.strftime('%d %b %Y') if found_job.eta_arrival_date else 'Schedule Pending'
        vessel_str = f"{found_job.vessel_name or 'N/A'} (Origin: {found_job.port_of_origin or 'Overseas'})"
        containers_str = f"{found_job.total_containers_count} ({found_job.container_size_type})"
        cargo_str = found_job.cargo_description or 'General Merchandise'
        overall_status = found_job.get_status_display()
        stage_display = f"{stage_en} (Milestone {stage_num}/11)"

        direct_job_reply = (
            f"📦 **Shipment Status: {found_job.job_number}** (B/L: `{found_job.bl_number}`)\n\n"
            f"• **Current Milestone:** **{stage_display}**\n"
            f"• **Operational Status:** {overall_status}\n"
            f"• **Vessel & Origin:** {vessel_str}\n"
            f"• **Estimated Arrival (ETA):** {eta_str}\n"
            f"• **Customs Duty (TRA/TANCIS):** {duty_status}\n"
            f"{f'• **TRA GePG Control No:** `{found_job.duty_control_number}`\n' if found_job.duty_control_number else ''}"
            f"• **Containers:** {containers_str}\n"
            f"• **Cargo Description:** {cargo_str}\n\n"
            f"💡 *Malkia Cargo Wave operations team is actively progressing this consignment.*"
        )

        receipt_prompt_reply = (
            f"📄 **Payment Receipt Submission for {found_job.job_number}**\n\n"
            f"• **Consignee / Client:** {found_job.customer.company_name}\n"
            f"• **TRA Assessed Duty:** TZS {found_job.assessed_duty_amount:,.2f}\n"
            f"{f'• **TRA GePG Control Number:** `{found_job.duty_control_number}`\n' if found_job.duty_control_number else ''}"
            f"• **Duty Status:** {'✅ Confirmed & Paid' if found_job.duty_paid else '⏳ Pending Duty Payment & Verification'}\n\n"
            f"📎 **To upload your receipt:**\n"
            f"Please click the **`+` (Attach Receipt)** button in the chat input bar below to select and upload your TRA E-Receipt or Bank slip (PNG, JPG, or PDF). I will automatically link it to this shipment and notify our Finance & Customs operations team for immediate verification!"
        )

    security_rules = """
CRITICAL PRIVACY & SECURITY GUIDELINES:
1. YOU ARE THE CLIENT PORTAL AI ASSISTANT FOR EXTERNAL CLIENTS OF MALKIA CARGO WAVE LTD.
2. ALWAYS COMMUNICATE EXCLUSIVELY IN PROFESSIONAL, COURTEOUS ENGLISH.
3. NEVER REVEAL INTERNAL CONFIDENTIAL COMPANY INFORMATION:
   - Company profits, revenue, margins, collections, bank accounts, or internal expenses.
   - Staff member names, salaries, private internal communications, or employee details.
   - Internal database structure, raw schemas, or proprietary algorithms.
   - Other clients' private shipment data or commercial identities.
4. YOUR CAPABILITIES:
   - Provide real-time shipment status when the client provides a valid Job Number or B/L Number.
   - Guide the client to upload their payment receipt by providing their Job Number and clicking the '+' button in the chat input bar.
   - Answer general inquiries about customs clearance procedures, port operations, and shipping lines.
"""

    if is_asking_receipt:
        if found_job:
            return {
                "status": "success",
                "reply": receipt_prompt_reply,
                "suggestions": ["Upload Receipt", "Check Cargo Status", "Speak with Officer"],
                "target_job_id": found_job.id,
                "target_job_number": found_job.job_number,
                "intent": "receipt_upload"
            }
        else:
            return {
                "status": "success",
                "reply": (
                    "I would be glad to help you submit your payment receipt! 📄\n\n"
                    "Please provide your **Job Number** (e.g. `CF/2026/0008` or simply `0008`) or **Bill of Lading (B/L)** number so I can link your receipt to the correct shipment dossier."
                ),
                "suggestions": ["CF/2026/0008", "CF/2026/0001", "Contact Support"],
                "intent": "receipt_upload"
            }

    if found_job:
        system_prompt = f"""You are Malkia AI, the official Client Portal Logistics Assistant for Malkia Cargo Wave Ltd (Clearing & Forwarding).
{security_rules}

SPECIFIC SHIPMENT DOSSIER RETRIEVED:
- Job Number: {found_job.job_number}
- Bill of Lading (B/L): {found_job.bl_number}
- Current Milestone: {found_job.current_stage_number}/11 — {stage_en}
- Status: {overall_status}
- Vessel: {vessel_str}
- ETA: {eta_str}
- Customs Duty (TRA): {duty_status}
- Control Number: {found_job.duty_control_number or 'N/A'}
- Containers: {containers_str}
- Cargo: {cargo_str}

GUIDELINES:
1. Respond to the client in clear, professional English.
2. If they ask to submit a payment receipt, tell them to click the '+' button below to upload their receipt for this shipment."""

    elif is_asking_tracking:
        system_prompt = f"""You are Malkia AI, the official Client Portal Logistics Assistant for Malkia Cargo Wave Ltd.
{security_rules}

The client is inquiring about shipment tracking but HAS NOT provided a Job Number.
Politely ask them to provide their Job Number (e.g., CF/2026/0008) or Bill of Lading (B/L) number so you can retrieve their live status."""

    else:
        system_prompt = f"""You are Malkia AI, the official Client Portal Logistics Assistant for Malkia Cargo Wave Ltd (Clearing & Forwarding).
{security_rules}

Greet the client courteously in professional English. Assist them with customs clearance inquiries, port logistics, tracking their cargo (remind them to enter their Job Number), or submitting payment receipts using the '+' attachment button."""

    messages = [{"role": "system", "content": system_prompt}]

    if chat_history and isinstance(chat_history, list):
        for msg in chat_history[-3:]:
            if isinstance(msg, dict) and "role" in msg and "content" in msg:
                content = str(msg["content"])
                if "network" not in content.lower() and "error" not in content.lower():
                    messages.append({"role": msg["role"], "content": content[:500]})

    messages.append({"role": "user", "content": clean_msg})

    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 1500,
        "temperature": 0.4
    }

    try:
        response = requests.post(endpoint, headers=headers, json=payload, timeout=25)
        if response.status_code == 200:
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            if content:
                suggestions = ["Track Another Cargo", "TRA Duty & Receipt", "Customer Care"]
                return {
                    "status": "success", 
                    "reply": content, 
                    "suggestions": suggestions,
                    "target_job_id": found_job.id if found_job else None,
                    "target_job_number": found_job.job_number if found_job else None,
                }
    except Exception as e:
        logger.warning(f"Hive AI request exception: {e}")

    # Fallback Handling (Ensures ZERO error popups on client side, always in English)
    if direct_job_reply:
        return {
            "status": "success", 
            "reply": direct_job_reply, 
            "suggestions": ["Upload Receipt", "Container Radar", "Contact Support"],
            "target_job_id": found_job.id,
            "target_job_number": found_job.job_number,
        }
    
    if is_job_attempt and not found_job:
        return {
            "status": "success",
            "reply": f"Sorry, I could not find a shipment matching that identifier in our database. Please double-check your Job Number (e.g. `CF/2026/0008` or `CF/2026/0001`) or Bill of Lading (B/L) number.",
            "suggestions": ["CF/2026/0008", "CF/2026/0001", "Contact Support"]
        }

    if is_asking_tracking:
        return {
            "status": "success",
            "reply": "Welcome! To track your cargo clearance and delivery status, please provide your **Job Number** (e.g. `CF/2026/0008`) or **Bill of Lading (B/L)** number.",
            "suggestions": ["CF/2026/0008", "CF/2026/0001"]
        }

    return {
        "status": "success",
        "reply": f"Hello {customer_name}! I am Malkia AI, your intelligent logistics concierge for Malkia Cargo Wave Ltd. How may I assist you today? You can enter your **Job Number** to track your cargo, or ask me about submitting a **Payment Receipt**.",
        "suggestions": ["Track My Shipment", "Upload Payment Receipt", "Clearance Inquiries"]
    }
