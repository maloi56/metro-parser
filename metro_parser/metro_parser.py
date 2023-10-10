import json
import logging
import os
from datetime import datetime
from pathlib import Path

import requests

from exceptions import CityError

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BASE_DIR = Path(__file__).resolve().parent


class MetroParser:
    domain: str = 'https://online.metro-cc.ru'
    url: str = "https://api.metro-cc.ru/products-api/graph"
    headers: dict = {
        'Accept': '* / *',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36'
    }

    def __init__(self):
        self.stores_info: dict = self.collect_stores_info()

    def collect_stores_info(self) -> dict:
        """Метод сбора информации по доступным магазинам во всех городах"""
        try:
            logging.info('Сбор информации о магазинах...')
            print(BASE_DIR)
            with open(f'{BASE_DIR}/stores.json', 'x', encoding='utf-8') as file:
                url_for_count = 'https://www.metro-cc.ru/sxa/search/results/?l=ru-RU&s={0F3B38A3-7330-4544-B95B-81FC80A6BB6F}|{0F3B38A3-7330-4544-B95B-81FC80A6BB6F}&itemid={A59341E8-DDEE-4399-B05A-5B91DB7188EF}&sig=store-locator&g=%7C&o=StoreName%2CAscending&p=20&v=%7BA0897F25-35F9-47F8-A28F-94814E5A0A78%7D'
                try:
                    response = requests.get(url_for_count, headers=self.headers)
                    total_count = json.loads(response.text)["Count"]
                except Exception as e:
                    logging.error(f'Ошибка при получении общего числа магазинов: {e}')
                    raise e

                url = 'https://api.metro-cc.ru/api/v1/C98BB1B547ECCC17D8AEBEC7116D6/tradecenters/'
                inner_id = 1
                count = 0
                stores_info = {}
                while count != total_count:
                    response = requests.get(f'{url}{inner_id}', headers=self.headers)
                    temp_data = json.loads(response.text)
                    if temp_data['success']:
                        city = temp_data['data']['city']
                        data = {
                            'store_id': temp_data['data']['store_id'],
                            'name': temp_data['data']['name']
                        }
                        stores_info.setdefault(city, []).append(data)
                        inner_id += 1
                        count += 1
                        logging.info(f'Отобрано {count - 1} магазинов')
                    else:
                        inner_id += 1

                logging.info('Сбор окончен')
                logging.info('Количество городов: %d', len(stores_info))
                json.dump(stores_info, file, indent=4, ensure_ascii=False)
                return stores_info
        except FileExistsError:
            with open(f'{BASE_DIR}/stores.json', 'r', encoding='utf-8') as file:
                return json.load(file)

    def get_categories(self, store_id: int) -> list:
        """ Метод получения доступных категорий магазина """
        query = """
            query Search($storeId: Int!, $asTree: Boolean) {
              search(storeId: $storeId) {
                categories(asTree: $asTree) {
                  slug
                  category_type
                }
              }
            }
            """
        variables = {
            "storeId": store_id,
            "asTree": True,
        }
        response = json.loads(requests.post(self.url,
                                            json={"query": query, "variables": variables},
                                            headers=self.headers).text)

        result = []
        for category in response['data']['search']['categories']:
            if category['category_type'] != 'promo_root':
                result.append(category['slug'])

        return result

    def parse_data(self, city: str):
        """ Метод парсинга товаров в наличии каждой категории в каждом магазине указанного города """
        if city not in self.stores_info:
            raise CityError(f'В введеном городе нет магазина Metro, доступные города: {list(self.stores_info)}')

        query = """
        query Category($storeId: Int!, $slug: String!, $from: Int!, $size: Int!) {
          category(storeId: $storeId, slug: $slug) {
            products(from: $from, size: $size) {
              name
              stocks {
                prices {
                  price
                  old_price
                }
              }
              url
              article
              attributes {
                text
              }
            }
          }
        }
        """
        cities_stores = self.stores_info[city]
        for store in cities_stores:
            store_id = store['store_id']
            categories = self.get_categories(store_id)
            logging.info(f'Обработка магазина: {store["name"]}')
            for category in categories:
                logging.info(f'Скачиваю категорию: {category}')
                try:
                    variables = {
                        "storeId": store_id,
                        "slug": category,
                        "from": 0,
                        "size": 9999999,
                    }
                    response = json.loads(requests.post(self.url,
                                                        json={"query": query, "variables": variables},
                                                        headers=self.headers).text)['data']['category']['products']
                    self.make_json_report(response, city, store['name'], category)
                except Exception as e:
                    logging.error(f'Ошибка при обработке магазина с ID {store_id}: {e}')
                    raise e

        logging.info('Данные успешно загружены')

    def make_json_report(self, response: list, city: str, name: str, category: str):
        """ Метод выборки необходимых данных и создание отчета """
        result = []
        for product in response:
            result.append({
                'article': product['article'],
                'name': product['name'],
                'url': self.domain + product['url'],
                'regular_price': (
                    product['stocks'][0]['prices']['old_price']
                    if product['stocks'][0]['prices']['old_price']
                    else product['stocks'][0]['prices']['price']),

                'promo_price': (product['stocks'][0]['prices']['price']
                                if product['stocks'][0]['prices']['old_price']
                                else None),

                'brand': product['attributes'][0]['text']

            })
        date = datetime.now().strftime('%d-%m-%y')
        path = f'data/{city}/{date}/{name}'
        filename = f'{category}'
        self.create_json_file(path, filename, result)

    def create_json_file(self, path: str, filename: str, data: list):
        """ Метод создания json файла """
        os.makedirs(path, exist_ok=True)
        with open(f'{path}/{filename}.json', 'w', encoding='utf-8') as file:
            json.dump(data, file, indent=4, ensure_ascii=False)


parser = MetroParser()
