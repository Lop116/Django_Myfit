def notifications(request):
    if not request.user.is_authenticated:
        return {
            'latest_notifications': (),
            'unread_notification_count': 0,
        }

    notification_manager = request.user.notifications
    return {
        'latest_notifications': notification_manager.order_by('-created_at')[:10],
        'unread_notification_count': notification_manager.filter(is_read=False).count(),
    }
