import re
from urllib import parse
import json
import numpy as np
import pandas as pd
import scrapy
from fnc import get
from scrapy import signals
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings


class IMDB_Producers_Info_Extractor(scrapy.Spider):
    name = 'imdb_producers_info'
    custom_settings = {
        'DOWNLOAD_DELAY': 0.1,
        'CONCURRENT_REQUESTS': 3,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 3,
    }

    file_path = '/imdb_extractor/data/producers.csv'
    url_api_pattern = 'https://caching.graphql.imdb.com/?{}'
    results = []

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        """Init crawler and connect spider.spider_idle method"""
        spider = super().from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.spider_idle, signals.spider_idle)
        return spider

    def start_requests(self):
        producers_info = pd.read_csv(self.file_path).to_dict('records')
        for i, producer in enumerate(producers_info):
            producer_id = self.get_producer_id_from_link(producer['producer_link'])
            yield scrapy.Request(
                self.url_api_pattern.format(
                    self.get_query(self.get_api_pages_query_params(producer_id))
                ),
                self.parse_credits,
                headers=self.get_api_headers(),
                meta={'handle_httpstatus_all': True},
                cb_kwargs={'producer_info': producer},
            )

    def parse_credits(self, response, producer_info):
        data = response.json()
        producer_id = self.get_producer_id_from_link(producer_info['producer_link'])
        result = {
            'id': producer_id,
            'link': producer_info['producer_link'],
            'name': producer_info['name'],
            'titles': producer_info['titles'],
            'movies': producer_info['movies'],
        }

        for credit in ['unreleasedCredits', 'releasedCredits']:
            for c in get(f'data.name.{credit}', data):
                category, movies = self.get_category_info(c, credit)
                if category not in result:
                    result[category] = list()
                result[category].extend(movies)

        for key, value in result.items():
            if key in ['id', 'link', 'name', 'titles', 'movies']:
                continue
            result[key] = json.dumps(value)

        self.results.append(result)

    def get_category_info(self, data, credit):
        category: str = get('category.text', data)
        movies = list()
        for movie in get('credits.edges', data):
            jobs = [x['text'] for x in movie['node'].get('jobs') or []]
            movie_name = movie['node']['title']['titleText']['text']
            movie_id = movie['node']['title']['id']
            movie_type = get('node.title.titleType.id', movie)
            movie_year = get('node.title.releaseYear.year', movie)
            movie_end_year = get('node.title.releaseYear.end_year', movie)
            movie_link = f'https://www.imdb.com/title/{movie_id}/'
            movies.append(
                {
                    'name': movie_name,
                    'id': movie_id,
                    'year': movie_year,
                    'end_year': movie_end_year,
                    'type': movie_type,
                    'link': movie_link,
                    'jobs': jobs,
                    'credit_status': self.to_snake_case(credit),
                }
            )
        return category.lower(), movies

    def get_query(self, query_params: list):
        query = parse.unquote(parse.urlencode(query_params, quote_via=parse.quote))
        query = re.sub(r'\s', '', query)
        query = re.sub(r"'", '"', query).replace('False', 'false')
        return query

    def get_api_pages_query_params(self, producer_id):
        params = {
            'operationName': 'NameMainFilmographyFilteredCredits',
            'variables': {
                'id': producer_id,
                'includeUserRating': False,
                'locale': 'en-EN',
            },
            'extensions': {
                'persistedQuery': {
                    'sha256Hash': '<<hash>>',
                    'version': 1,
                }
            },
        }
        return params

    def spider_idle(self, spider):
        pd.DataFrame(self.results).reset_index().fillna(np.nan).replace(
            [np.nan], [None]
        ).drop(columns=['index']).to_csv('data/result.csv')

    @staticmethod
    def get_api_headers():
        return {
            'Accept': 'application/graphql+json, application/json',
            'Accept-Language': 'en',
            'Content-Type': 'application/json',
            'Priority': 'u=1, i',
            'Referer': 'https://www.imdb.com/',
            'Sec-Ch-Ua': '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': 'macOS',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        }

    @staticmethod
    def get_producer_id_from_link(link):
        return link.split('/')[4]

    @staticmethod
    def to_snake_case(text):
        return re.sub(r'(?<!^)(?=[A-Z])', '_', text).lower()


if __name__ == '__main__':
    s = get_project_settings()
    process = CrawlerProcess(s)
    crawler = process.create_crawler(IMDB_Producers_Info_Extractor)
    process.crawl(crawler)
    process.start()
