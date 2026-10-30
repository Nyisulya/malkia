import os
from datetime import datetime, timezone as dt_timezone, timedelta
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.db.models import Q, Max
from django.utils import timezone
from core.models import UserProfile, UserRole, StaffChatMessage


@login_required
def internal_chat_view(request):
    """
    Full Real-Time Chat & Direct Messaging Console.
    Allows CEO / Executives to message any employee, and staff to message peers & managers instantly.
    """
    current_user = request.user
    user_role = getattr(current_user, 'profile', None) and current_user.profile.role or UserRole.DOC_OFFICER
    can_broadcast = user_role in [UserRole.CEO, UserRole.ADMIN, UserRole.OPERATIONS_MGR]

    # Fetch all other active users
    users_qs = User.objects.filter(is_active=True).exclude(id=current_user.id).select_related('profile')

    # Optional search query
    q = request.GET.get('q', '').strip().lower()
    if q:
        users_qs = users_qs.filter(
            Q(username__icontains=q) |
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(profile__phone_number__icontains=q) |
            Q(profile__role__icontains=q) |
            Q(profile__department__icontains=q)
        )

    # Optional role filter
    role_filter = request.GET.get('role', 'ALL').upper()
    if role_filter != 'ALL':
        if role_filter == 'MANAGEMENT':
            users_qs = users_qs.filter(profile__role__in=[UserRole.CEO, UserRole.ADMIN, UserRole.OPERATIONS_MGR])
        elif role_filter == 'OPERATIONS':
            users_qs = users_qs.filter(profile__role__in=[UserRole.DOC_OFFICER, UserRole.PORT_OFFICER, UserRole.DISPATCH_OFFICER])
        elif role_filter == 'CUSTOMS':
            users_qs = users_qs.filter(profile__role=UserRole.CLEARING_OFFICER)
        elif role_filter == 'DRIVERS':
            users_qs = users_qs.filter(profile__role=UserRole.DRIVER)
        elif role_filter == 'FINANCE':
            users_qs = users_qs.filter(profile__role=UserRole.FINANCE)

    # Build contacts list with last message snippet, timestamp, and unread counts
    contacts = []
    total_unread = 0

    for u in users_qs:
        unread_count = StaffChatMessage.objects.filter(
            sender=u, recipient=current_user, is_read=False
        ).count()
        total_unread += unread_count

        last_msg = StaffChatMessage.objects.filter(
            (Q(sender=current_user, recipient=u) | Q(sender=u, recipient=current_user)) & Q(is_broadcast=False)
        ).order_by('-created_at').first()

        prof = getattr(u, 'profile', None)
        initials = (u.first_name[:1] + u.last_name[:1]).upper() if u.first_name and u.last_name else u.username[:2].upper()

        contacts.append({
            'user': u,
            'id': u.id,
            'name': u.get_full_name() or u.username,
            'role_code': prof.role if prof else 'STAFF',
            'role_display': prof.get_role_display() if prof else 'Staff Member',
            'department': prof.get_department_display() if prof else 'Operations',
            'phone': prof.phone_number if prof else '',
            'initials': initials,
            'avatar_url': prof.avatar.url if prof and prof.avatar else None,
            'unread_count': unread_count,
            'last_message': last_msg.message if last_msg else ('Shared an attachment' if last_msg and last_msg.attachment else ''),
            'last_message_time': last_msg.created_at if last_msg else None,
            'is_last_from_me': (last_msg.sender_id == current_user.id) if last_msg else False,
        })

    # Sort contacts: unread messages first, then most recent interaction, then by name
    min_aware_dt = datetime.min.replace(tzinfo=dt_timezone.utc)
    contacts.sort(key=lambda c: (
        1 if c['unread_count'] > 0 else 0,
        c['last_message_time'] or min_aware_dt,
        c['name']
    ), reverse=True)

    # Determine active contact
    active_user_id = None
    target_id_param = request.GET.get('user') or request.GET.get('user_id')
    if target_id_param:
        try:
            active_user_id = int(target_id_param)
        except ValueError:
            active_user_id = None

    if active_user_id is None and contacts:
        active_user_id = contacts[0]['id']

    active_contact = None
    if active_user_id:
        active_user = User.objects.filter(id=active_user_id).first()
        if active_user:
            aprof = getattr(active_user, 'profile', None)
            ainitials = (active_user.first_name[:1] + active_user.last_name[:1]).upper() if active_user.first_name and active_user.last_name else active_user.username[:2].upper()
            active_contact = {
                'id': active_user.id,
                'name': active_user.get_full_name() or active_user.username,
                'username': active_user.username,
                'role_code': aprof.role if aprof else 'STAFF',
                'role_display': aprof.get_role_display() if aprof else 'Staff Member',
                'department': aprof.get_department_display() if aprof else 'Operations',
                'phone': aprof.phone_number if aprof else '',
                'work_station': aprof.work_station if aprof else 'Dar es Salaam HQ',
                'initials': ainitials,
                'avatar_url': aprof.avatar.url if aprof and aprof.avatar else None,
            }

    context = {
        'contacts': contacts,
        'active_contact': active_contact,
        'active_user_id': active_user_id,
        'total_unread': total_unread,
        'can_broadcast': can_broadcast,
        'role_filter': role_filter,
        'search_q': q,
    }
    return render(request, 'core/internal_chat.html', context)


@login_required
def api_chat_messages(request, user_id):
    """
    Fetch message stream between current user and target user_id.
    Accepts ?last_id=<id> for zero-reload real-time polling updates.
    """
    current_user = request.user
    last_id = request.GET.get('last_id')

    if user_id == 0:
        # Broadcast channel
        qs = StaffChatMessage.objects.filter(is_broadcast=True)
    else:
        # 1-on-1 Direct Chat
        qs = StaffChatMessage.objects.filter(
            (Q(sender=current_user, recipient_id=user_id) | Q(sender_id=user_id, recipient=current_user)) &
            Q(is_broadcast=False)
        )

    if last_id:
        try:
            lid = int(last_id)
            qs = qs.filter(id__gt=lid)
        except ValueError:
            pass

    qs = qs.select_related('sender', 'sender__profile', 'reply_to', 'reply_to__sender').order_by('created_at')

    # Mark incoming unread messages as read
    unread_ids = [m.id for m in qs if m.recipient_id == current_user.id and not m.is_read]
    if unread_ids:
        StaffChatMessage.objects.filter(id__in=unread_ids).update(is_read=True, read_at=timezone.now())

    now_date = timezone.now().date()
    messages_data = []
    user_role = getattr(current_user, 'profile', None) and current_user.profile.role or UserRole.DOC_OFFICER
    is_boss = user_role in [UserRole.CEO, UserRole.ADMIN]

    for m in qs:
        local_created = timezone.localtime(m.created_at)
        date_str = 'Today' if local_created.date() == now_date else local_created.strftime('%d %b %Y')

        prof = getattr(m.sender, 'profile', None)
        initials = (m.sender.first_name[:1] + m.sender.last_name[:1]).upper() if m.sender.first_name and m.sender.last_name else m.sender.username[:2].upper()
        
        has_file = bool(m.attachment) and not m.is_deleted
        is_img = False
        filename = ''
        file_url = ''
        if has_file:
            file_url = m.attachment.url
            filename = os.path.basename(m.attachment.name)
            is_img = filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif'))

        reply_info = None
        if m.reply_to:
            r_sender_name = m.reply_to.sender.get_full_name() or m.reply_to.sender.username
            reply_info = {
                'id': m.reply_to.id,
                'sender_name': r_sender_name,
                'message': m.reply_to.message[:70] if not m.reply_to.is_deleted else 'Deleted message',
            }

        display_message = m.message
        if m.is_deleted:
            display_message = "🚫 This message was deleted"

        messages_data.append({
            'id': m.id,
            'sender_id': m.sender_id,
            'sender_name': m.sender.get_full_name() or m.sender.username,
            'sender_initials': initials,
            'sender_role': prof.get_role_display() if prof else 'Staff',
            'is_me': m.sender_id == current_user.id,
            'message': display_message,
            'is_deleted': m.is_deleted,
            'can_delete': (m.sender_id == current_user.id or is_boss) and not m.is_deleted,
            'reply_to': reply_info,
            'has_attachment': has_file,
            'attachment_url': file_url,
            'attachment_name': filename,
            'is_image': is_img,
            'is_broadcast': m.is_broadcast,
            'is_read': m.is_read,
            'time': local_created.strftime('%I:%M %p'),
            'date': date_str,
        })

    # Contact details
    contact_data = None
    if user_id > 0:
        target_user = User.objects.filter(id=user_id).select_related('profile').first()
        if target_user:
            tprof = getattr(target_user, 'profile', None)
            tinitials = (target_user.first_name[:1] + target_user.last_name[:1]).upper() if target_user.first_name and target_user.last_name else target_user.username[:2].upper()
            contact_data = {
                'id': target_user.id,
                'name': target_user.get_full_name() or target_user.username,
                'role': tprof.get_role_display() if tprof else 'Staff',
                'department': tprof.get_department_display() if tprof else 'Operations',
                'phone': tprof.phone_number if tprof else '',
                'initials': tinitials,
                'avatar_url': tprof.avatar.url if tprof and tprof.avatar else None,
            }

    return JsonResponse({
        'status': 'success',
        'contact': contact_data,
        'messages': messages_data,
        'server_time': timezone.now().isoformat(),
    })


@login_required
def api_chat_send(request):
    """
    POST API to send an instant message or attachment without reloading the page.
    Supports reply_to_id for quoted replies like WhatsApp.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST method is allowed'}, status=405)

    recipient_id = request.POST.get('recipient_id')
    message_text = request.POST.get('message', '').strip()
    attachment_file = request.FILES.get('attachment')
    is_broadcast = request.POST.get('is_broadcast') == 'true'
    reply_to_id = request.POST.get('reply_to_id')

    if not message_text and not attachment_file:
        return JsonResponse({'status': 'error', 'message': 'Message or attachment required'}, status=400)

    current_user = request.user
    user_role = getattr(current_user, 'profile', None) and current_user.profile.role or UserRole.DOC_OFFICER

    recipient = None
    if is_broadcast:
        if user_role not in [UserRole.CEO, UserRole.ADMIN, UserRole.OPERATIONS_MGR]:
            return JsonResponse({'status': 'error', 'message': 'Unauthorized to broadcast messages'}, status=403)
    else:
        if not recipient_id:
            return JsonResponse({'status': 'error', 'message': 'Recipient is required'}, status=400)
        try:
            recipient = User.objects.get(id=int(recipient_id))
        except (User.DoesNotExist, ValueError):
            return JsonResponse({'status': 'error', 'message': 'Recipient user not found'}, status=404)

    reply_to_obj = None
    if reply_to_id:
        try:
            reply_to_obj = StaffChatMessage.objects.filter(id=int(reply_to_id)).first()
        except ValueError:
            pass

    msg = StaffChatMessage.objects.create(
        sender=current_user,
        recipient=recipient,
        reply_to=reply_to_obj,
        message=message_text,
        attachment=attachment_file,
        is_broadcast=is_broadcast,
        is_read=False
    )

    local_created = timezone.localtime(msg.created_at)
    now_date = timezone.now().date()
    date_str = 'Today' if local_created.date() == now_date else local_created.strftime('%d %b %Y')

    prof = getattr(current_user, 'profile', None)
    initials = (current_user.first_name[:1] + current_user.last_name[:1]).upper() if current_user.first_name and current_user.last_name else current_user.username[:2].upper()

    has_file = bool(msg.attachment)
    is_img = False
    filename = ''
    file_url = ''
    if has_file:
        file_url = msg.attachment.url
        filename = os.path.basename(msg.attachment.name)
        is_img = filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif'))

    reply_info = None
    if msg.reply_to:
        r_sender_name = msg.reply_to.sender.get_full_name() or msg.reply_to.sender.username
        reply_info = {
            'id': msg.reply_to.id,
            'sender_name': r_sender_name,
            'message': msg.reply_to.message[:70] if not msg.reply_to.is_deleted else 'Deleted message',
        }

    formatted = {
        'id': msg.id,
        'sender_id': current_user.id,
        'sender_name': current_user.get_full_name() or current_user.username,
        'sender_initials': initials,
        'sender_role': prof.get_role_display() if prof else 'Staff',
        'is_me': True,
        'message': msg.message,
        'is_deleted': False,
        'can_delete': True,
        'reply_to': reply_info,
        'has_attachment': has_file,
        'attachment_url': file_url,
        'attachment_name': filename,
        'is_image': is_img,
        'is_broadcast': msg.is_broadcast,
        'is_read': False,
        'time': local_created.strftime('%I:%M %p'),
        'date': date_str,
    }

    return JsonResponse({
        'status': 'success',
        'message': formatted,
    })


@login_required
def api_chat_delete(request, message_id):
    """
    Delete a chat message (marks as deleted like WhatsApp).
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'POST required'}, status=405)

    current_user = request.user
    user_role = getattr(current_user, 'profile', None) and current_user.profile.role or UserRole.DOC_OFFICER
    is_boss = user_role in [UserRole.CEO, UserRole.ADMIN]

    msg = get_object_or_404(StaffChatMessage, id=message_id)
    if msg.sender_id != current_user.id and not is_boss:
        return JsonResponse({'status': 'error', 'message': 'Permission denied to delete this message'}, status=403)

    msg.is_deleted = True
    msg.message = "This message was deleted"
    msg.attachment = None
    msg.save(update_fields=['is_deleted', 'message', 'attachment'])

    return JsonResponse({
        'status': 'success',
        'message_id': msg.id,
    })


@login_required
def api_chat_unread_summary(request):
    """
    Lightweight background polling endpoint used by base.html to update
    the topbar badge and show real-time incoming message alerts across the app.
    """
    current_user = request.user
    
    # Unread direct messages
    unread_msgs = StaffChatMessage.objects.filter(
        recipient=current_user, is_read=False
    ).select_related('sender', 'sender__profile').order_by('-created_at')

    total_unread = unread_msgs.count()

    latest_data = None
    latest_msg = unread_msgs.first()
    if latest_msg:
        prof = getattr(latest_msg.sender, 'profile', None)
        latest_data = {
            'id': latest_msg.id,
            'sender_id': latest_msg.sender_id,
            'sender_name': latest_msg.sender.get_full_name() or latest_msg.sender.username,
            'sender_role': prof.get_role_display() if prof else 'Staff',
            'snippet': latest_msg.message[:65] if latest_msg.message else '[Attachment / Document]',
            'time': timezone.localtime(latest_msg.created_at).strftime('%I:%M %p'),
        }

    return JsonResponse({
        'status': 'success',
        'total_unread': total_unread,
        'latest_unread': latest_data,
    })
