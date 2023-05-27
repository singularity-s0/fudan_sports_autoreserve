import json
import time

import easyocr
import requests
import logs
from bs4 import BeautifulSoup

import cv2
import base64
import numpy as np
from datetime import datetime

CUDA = None
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.3 Safari/605.1.15",
    "Referer": "https://elife.fudan.edu.cn/app/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}
get_reservables_url = "https://elife.fudan.edu.cn/app/api/toResourceFrame.action"
sso_url = "https://elife.fudan.edu.cn/sso/login?targetUrl=base64aHR0cHM6Ly9lbGlmZS5mdWRhbi5lZHUuY24vYXBw"
app_url = "https://elife.fudan.edu.cn/app/"
reserve_url = "https://elife.fudan.edu.cn/app/api/order/saveOrder.action?op=order"
captcha_url = "https://elife.fudan.edu.cn/public/front/getImgSwipe.htm?_="
order_form_url = "https://elife.fudan.edu.cn/app/api/order/loadOrderForm_ordinary.action"
search_url = "https://elife.fudan.edu.cn/app/api/search.action"
error_string = "您将登录的是："
max_retry = 3


def login(username, password):
    # Login UIS
    data = {
        "username": username,
        "password": password
    }
    retry = 0
    s = requests.Session()
    while retry < max_retry:
        retry += 1
        try:
            logs.log_console("Begin UIS Login", "INFO")
            s.headers.update(headers)
            response = requests.get(sso_url, allow_redirects=True,
                                    headers={
                                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.3 Safari/605.1.15"},
                                    cookies=None)
            login_url = response.url
            s.get(app_url, allow_redirects=True)
            response = s.get(login_url, allow_redirects=True)
            soup = BeautifulSoup(response.text, "lxml")
            inputs = soup.find_all("input")
            for i in inputs[2::]:
                data[i.get("name")] = i.get("value")
            s.headers.update({"Referer": "https://uis.fudan.edu.cn/"})
            response = s.post(login_url, data=data, allow_redirects=True)
            if error_string in response.text:
                logs.log_console("UIS Login Failed", "ERROR")
                raise Exception("UIS Login Failed")
            logs.log_console("UIS Login Successful", "INFO")

            logs.log_console("Begin Elife OAuth Login", "INFO")
            response = s.get(sso_url,
                             allow_redirects=False)  # Note that redirects must not be allowed here, otherwise userToken will be replaced with an invalid value
            logs.log_console("OAuth Login Response Code: " + str(response.status_code), "DEBUG")
            # Update headers with token
            s.headers.update({"token": s.cookies.get_dict()["userToken"][1:-1]})
            break
        except KeyError:
            logs.log_console("OAuth Login Failed", "ERROR")
        logs.log_console(f"OAuth Login Failed, {max_retry - retry} Retries Left", "WARNING")
        time.sleep(500)
        s = requests.Session()
    if retry >= max_retry:
        logs.log_console("Elife OAuth Login Failed", "ERROR")
        raise Exception("Elife OAuth Login Failed")
    logs.log_console("Elife OAuth Login Successful", "INFO")
    logs.log_console(f"Token: {s.cookies.get_dict().get('userToken')[1:-1]}", "DEBUG")
    return s


def load_sports_and_campus_id(s: requests.Session, service_category_id, target_campus, target_sport):
    logs.log_console("Begin Fetching Sports and Campus ID", "INFO")
    response = s.get(search_url, params={"id": service_category_id})
    raw_data = json.loads(response.text)['object']['queryList']
    campuses = raw_data[0]['serviceDics']
    sports = raw_data[1]['serviceDics']
    sport_id = None
    campus_id = None
    for campus in campuses:
        if campus['value'] == target_campus:
            campus_id = campus['id']
            break
    for sport in sports:
        if sport['value'] == target_sport:
            sport_id = sport['id']
            break
    if sport_id is None or campus_id is None:
        logs.log_console("Sport or Campus ID not found", "ERROR")
        raise Exception("Sport or Campus not found")
    logs.log_console(f"Campus ID for {target_campus} is {campus_id}", "INFO")
    logs.log_console(f"Sports ID for {target_sport} is {sport_id}", "INFO")
    return campus_id, sport_id


def get_service_id(s: requests.Session, service_cat_id, campus_id, sport_id, target_sport_location):
    logs.log_console(f"Begin Fetching Service ID for {target_sport_location}", "INFO")
    response = s.get(search_url, params={"id": service_cat_id, "dicId": campus_id + ',' + sport_id})
    sports_list = json.loads(response.text)['object']['pageBean']['list']
    service_id = None
    for sport in sports_list:
        if sport['publishName'] == target_sport_location:
            service_id = sport['id']
            logs.log_console(f"Service ID for {target_sport_location} is {service_id}", "INFO")
            break
    if service_id is None:
        logs.log_console("Service ID not found", "ERROR")
        raise Exception("Service ID not found")
    return service_id


def reserve(s: requests.Session, service_id, service_cat_id, target_date, target_time):
    """
    :param s: requests.Session() that contains the login information, or user token in Str format
    :param service_id: String of service ID (e.g. badminton: 2c9c486e4f821a19014f82418a900004)
    :param service_cat_id: String of service category ID
    :param target_date: String in the format of "YYYY-MM-DD" (e.g. 2020-01-01)
    :param target_time: String in the format of "HH:MM" (e.g. 10:00)
    """

    # Load reservable objects
    logs.log_console("Begin Loading Reservable Options List", "INFO")
    s.headers.update({"Referer": app_url, "Host": "elife.fudan.edu.cn", "Accept": "application/json, text/plain, */*"})
    response = s.get(get_reservables_url, params={"contentId": service_id,
                                                  "pageNum": "1", "pageSize": "100", "currentDate": target_date})

    logs.log_console(
        f"Reservable Options Response {response.text}, request: {response.request.url} {response.request.headers}",
        "DEBUG")
    reservable_options_list = json.loads(response.text)['object']['page']['list']
    logs.log_console("Loading Reservable Options List Successful", "INFO")

    for reservable_option in reservable_options_list:
        if reservable_option['ifOrder']:  # Filter out non-reservable objects
            if reservable_option['serviceTime']['beginTime'] == target_time and reservable_option['openDate'] == target_date:
                logs.log_console(
                    f"Begin Reserving Target: {reservable_option['openDate']} {reservable_option['serviceTime']['beginTime']}, Target ID: {reservable_option['id']}, Target ServiceTime ID: {reservable_option['serviceTime']['id']}",
                    "VITAL")

                try:
                    logs.log_console("Begin Loading Order Form", "INFO")
                    response = s.get(order_form_url,
                                     params={"resourceIds": reservable_option['id'], "serviceContent.id": service_id,
                                             "serviceCategory.id": service_cat_id, "orderCounts": 1})
                    logs.log_console(f"Order Form Request: {response.request.url} {response.request.headers}", "DEBUG")
                    logs.log_console(f"Order Form: {response.text}", "DEBUG")
                    info_form = json.loads(response.text)['object']['userInfo']
                    user_name = info_form['personName']
                    user_phone = info_form['phone']
                    logs.log_console("Name: " + user_name + " Phone: " + user_phone, "INFO")
                except KeyError:
                    logs.log_console("Invalid order form, falling back to manual input", "WARNING")
                    user_name = input("Enter your name: ")
                    user_phone = input("Enter your phone: ")

                logs.log_console("Begin Fetch Captcha", "INFO")
                move_X = get_and_recognize_captcha(s, captcha_url)
                response = s.post(reserve_url, data={"lastDays": 0, "orderuser": user_name,
                                                     "mobile": user_phone, "d_cgyy.bz": None,
                                                     "moveEnd_X": move_X,
                                                     "wbili": 1.0,
                                                     "resourceIds": reservable_option['id'],
                                                     "serviceContent.id": service_id,
                                                     "serviceCategory.id": service_cat_id,
                                                     "orderCounts": 1})
                logs.log_console(f"Reserve Request: {response.request.url} {response.request.headers}", "DEBUG")
                logs.log_console(f"Reserve Response: {response.text}", "DEBUG")
                if response.status_code <= 300 and json.loads(response.text)['message'] == "操作成功！":
                    logs.log_console("Reservation Successful", "VITAL")
                else:
                    logs.log_console("Reservation Failed", "VITAL")
                    raise Exception("Reservation Failed")
                break
            else:
                logs.log_console(
                    f"Skipping Available Option: {reservable_option['openDate']} {reservable_option['serviceTime']['beginTime']}",
                    "INFO")


def get_and_recognize_captcha(s,captcha_url):
    stamp = datetime.timestamp(datetime.now())
    stamp = str(int(stamp*1000))
    captcha_url += stamp
    i = 0
    while i<6:
        try:
            response = json.loads(s.get(captcha_url).text)["object"]
        except Exception as e:
            i += 1
            continue
        break
    src_edge = image_convert(response["SrcImage"]) # base64 to edge
    cut_edge = image_convert(response["CutImage"])
    res = cv2.matchTemplate(cut_edge, src_edge, cv2.TM_CCOEFF_NORMED)
    _, _, _, max_loc = cv2.minMaxLoc(res)
    x = max_loc[0]
    return x

def image_convert(image):
    image = base64.b64decode(image)
    nparr = np.fromstring(image, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    edge = cv2.Canny(img, 100, 200)
    return edge