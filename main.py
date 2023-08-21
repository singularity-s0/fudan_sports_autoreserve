import apis
import logs
import concurrent.futures

SERVICE_CATEGORY = "2c9c486e4f821a19014f82381feb0001"  # This is the category ID for "Sports Reservation". It usually doesn't change.

# Fill in these data
USER_ID = ""
USER_PASSWORD = ""
CAMPUS_NAME = "校区"
SPORT_NAME = "羽毛球"
SPORT_LOCATION = "XXXX场"
from datetime import datetime, timedelta

today = datetime.today()
two_days_later = today + timedelta(days=2)
DATE = two_days_later.strftime("%Y-%m-%d") #自动延后两天
TIMES = ["08:00","09:00"] #可以一次预定多个时间段

# Optional data
EMAILS = []  # Receive error notifications by email
YOUR_EMAIL = None  # Account to send email from
EMAIL_PASSWORD = None  # Password for the email account



def main_request(TIME: str):
    try:
        print(DATE)
        logged_in_session = apis.login(USER_ID, USER_PASSWORD)
        campus_id, sport_id = apis.load_sports_and_campus_id(logged_in_session, SERVICE_CATEGORY, CAMPUS_NAME, SPORT_NAME)
        service_id = apis.get_service_id(logged_in_session, SERVICE_CATEGORY, campus_id, sport_id, SPORT_LOCATION)
        apis.reserve(logged_in_session, service_id, SERVICE_CATEGORY, DATE, TIME)
    except Exception as e:
        if EMAILS:
            import smtplib
            import datetime
            message = f"Subject: Failed to reserve sport field\n\n{logs.FULL_LOG}"
            connection = smtplib.SMTP("smtp-mail.outlook.com", 587)
            try:
                connection.ehlo()
                connection.starttls()
                connection.login(YOUR_EMAIL, EMAIL_PASSWORD)
                connection.sendmail(YOUR_EMAIL, EMAILS, message)
            finally:
                connection.quit()

if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(TIMES)) as executor:
        executor.map(main_request, TIMES)
