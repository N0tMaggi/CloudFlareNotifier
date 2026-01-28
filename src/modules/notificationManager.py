# Manager for creating and handling + showing toast windows notifications
from modules.importHandler import windows_toasts
from modules.loggingHandler import logger

class NotificationManager:
    def __init__(self):
        # Initialize the toaster with an Application User Model ID (AUMID) or name
        self.toaster = windows_toasts.WindowsToaster('Cloudflare Notifier')

    def send_notification(self, title, message):
        """
        Sends a Windows Toast notification with a title and a message body.
        """
        try:
            # Create a new toast notification
            new_toast = windows_toasts.Toast()
            
            # Set the text fields: first element is arguably the title/header, second is body
            new_toast.text_fields = [title, message]
            
            # Show the toast
            self.toaster.show_toast(new_toast)
            logger.info(f"Notification sent: {title} - {message}")
            
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
