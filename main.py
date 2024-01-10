import re
import time
import logging

import yaml
import faker
from pymongo import MongoClient
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select


def logger_config() -> logging.Logger:
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s:%(name)s:%(levelname)s:%(message)s')

    file_handler = logging.FileHandler('./logfile.log', encoding = "utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    logger.addHandler(stream_handler)
    return logger


def selenium_prep(headless: bool = False):
    options = webdriver.ChromeOptions()

    if headless:
        options.add_argument("--headless")
        options.add_argument("--window-size=1280,720")
        options.add_argument("--no-sandbox")
    elif not headless:
        options.add_argument("--start-maximized")

    prefs = {
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
    }
    options.add_experimental_option("prefs", prefs)
    options.add_experimental_option("excludeSwitches", ["enable-automation"])

    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(5)
    return driver


def page_1(driver) -> (list[str], str, str, str, list[str]):
    logger.info("Visiting chapter-living.com")

    driver.get("https://www.chapter-living.com/")

    # Click on the "BOOK A ROOM" button
    driver.find_element(By.CSS_SELECTOR, "#btn-main-book-a-room-pink").click()

    select = Select(driver.find_element(By.CSS_SELECTOR, "#BookingAvailabilityForm_Residence"))
    select.select_by_visible_text("CHAPTER KINGS CROSS")

    select = Select(driver.find_element(By.CSS_SELECTOR, "#BookingAvailabilityForm_BookingPeriod"))
    select.select_by_visible_text("SEP 24 - AUG 25 (51 WEEKS)")

    # scroll to bottom and click room type ensuite
    driver.execute_script("arguments[0].scrollIntoView();", driver.find_element(By.CSS_SELECTOR, "#BookingAvailabilityForm_BookingPeriod"))
    time.sleep(1)
    driver.find_element(By.CSS_SELECTOR, "#filter-room-type-ensuite").click()

    time.sleep(3)


    room_list = driver.find_elements(By.CSS_SELECTOR, "#room-list .sp-room")
    logger.info(f"Found {len(room_list)} rooms")
    room = room_list[0]

    logger.info("Getting room details")
    img_urls = []
    for div in room.find_elements(By.CSS_SELECTOR, ".swiper-container .swiper-wrapper div.the-img"):
        style = div.get_attribute("style")
        match = re.search(r'url\("(.+)"\)', style)
        if match:
            url = match.group(1)
            url = url.split("?")[0]
            img_urls.append(url)

    property_name = room.find_element(By.CSS_SELECTOR, ".sp-content .w-100 .property").text
    room_type = room.find_element(By.CSS_SELECTOR, ".sp-content .w-100 .display-4").text
    pricing = room.find_element(By.CSS_SELECTOR, ".sp-content .w-100 .pricing").text
    features = [
        feature.text
        for feature in room.find_elements(By.CSS_SELECTOR, ".sp-content .w-100 .features-list li")
    ]

    # scroll apply button into view and click
    driver.execute_script("arguments[0].scrollIntoView();", room.find_element(By.CSS_SELECTOR, ".sp-content .w-100 .display-4"))
    time.sleep(0.5)
    logger.info("Clicking apply button")
    room.find_element(By.CSS_SELECTOR, ".sp-content .w-100 .button-container a").click()

    return img_urls, property_name, room_type, pricing, features


def page_2(driver) -> (str, dict, str, str, str, str):
    logger.info("Page 2")
    logger.info("Getting floor plan details")
    floor_plan = driver.find_element(By.CSS_SELECTOR, ".box-image-holder .image-data .lease-date").text

    floor_plan_data = driver.find_element(By.CSS_SELECTOR, ".box-image-holder .image-data .data-container").text
    floor_plan_data = floor_plan_data.split("\n")
    floor_plan_data = [line.split(": ") for line in floor_plan_data]
    floor_plan_data = dict(floor_plan_data)

    logger.info("Generating fake user details")

    fake = faker.Faker("en_GB")
    name = fake.name()
    first_name, last_name = name.split()[-2:]
    phone_number = fake.phone_number()
    phone = phone_number.replace("+44", "")
    email = fake.email()
    password = fake.password()

    logger.info("Entering user details")
    driver.find_element(By.CSS_SELECTOR, "#applicant_first_name").send_keys(first_name)
    driver.find_element(By.CSS_SELECTOR, "#applicant_last_name").send_keys(last_name)
    driver.find_element(By.CSS_SELECTOR, ".phone-number").send_keys(phone)
    driver.find_element(By.CSS_SELECTOR, "#applicant_username").send_keys(email)
    driver.find_element(By.CSS_SELECTOR, "#applicant_password").send_keys(password)
    driver.find_element(By.CSS_SELECTOR, "#applicant_password_confirm").send_keys(password)
    driver.find_element(By.CSS_SELECTOR, "#agrees_to_terms").click()
    time.sleep(5)
    logger.info("Clicking create account button")
    driver.find_element(By.CSS_SELECTOR, "#create-app-btn").click()

    logger.info("Clicking agree button in popup")
    driver.find_element(By.CSS_SELECTOR, ".btn.btn--full.js-confirm").click()

    return floor_plan, floor_plan_data, name, phone, email, password


def page_3(driver) -> (str, list[dict]):
    logger.info("Page 3")
    logger.info("Getting floor plan image and unit details")
    floor_plan_image = driver.find_element(By.CSS_SELECTOR, 'img[alt="Floor plan Image"]').get_attribute("src")

    units = driver.find_elements(By.CSS_SELECTOR, ".sus-unit-details .sus-unit-space-details")
    unit_list = []
    for unit in units:
        d = dict(
            [
                row.text.split("\n")
                for row in unit.find_elements(By.CSS_SELECTOR, ".left .sus-clear")
            ]
        )
        unit_number = unit.find_element(By.CSS_SELECTOR, ".left h6").text
        d["unit_number"] = unit_number
        unit_list.append(d)

    return floor_plan_image, unit_list


if __name__ == "__main__":
    logger = logger_config()

    with open('config.yml') as f:
        config = yaml.safe_load(f)

    mongo_db_url = "mongodb+srv://{username}:{password}@{host}/{database}"
    client = MongoClient(mongo_db_url.format(**config['mongodb']))
    db = client.chapter
    collection = db.chapter

    driver = selenium_prep()

    img_urls, property_name, room_type, pricing, features = page_1(driver)
    floor_plan, floor_plan_data, name, phone, email, password = page_2(driver)
    floor_plan_image, unit_list = page_3(driver)
    driver.close()

    data = {
        "img_urls": img_urls,
        "property_name": property_name,
        "room_type": room_type,
        "pricing": pricing,
        "features": features,
        "floor_plan": floor_plan,
        "floor_plan_data": floor_plan_data,
        "user_details": {
            "name": name,
            "phone": phone,
            "email": email,
            "password": password,
        },
        "floor_plan_image": floor_plan_image,
        "units": unit_list,
    }

    try:
        logger.info("Inserting data into MongoDB")
        collection.insert_one(data)
        logger.info("Data inserted successfully")
    except Exception as e:
        logger.error(e)
        logger.error("Failed to insert data into MongoDB")
