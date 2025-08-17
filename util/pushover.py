import http.client, urllib
from config import create_c

c = create_c()

def send_push_notification(message):
    conn = http.client.HTTPSConnection("api.pushover.net:443")
    conn.request("POST", "/1/messages.json",
    urllib.parse.urlencode({
        "token": c.pushover.api_token,
        "user": c.pushover.user_key,
        "message": message,
    }), { "Content-type": "application/x-www-form-urlencoded" })
    conn.getresponse()