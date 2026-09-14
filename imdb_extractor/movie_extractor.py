import base64
import json
import re
from urllib import parse

import scrapy
from fnc import get
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

from imdb_extractor.live import require_live


class IMDB_Movies_Extractor(scrapy.Spider):
    name = 'imdb_movies'
    url_api_pages_pattern = 'https://caching.graphql.imdb.com/?{query}'
    config_file_path = 'data/config.json'
    page_limit = 500

    FEED_FORMAT = 'csv'
    FEED_URI = 'movies.csv'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ids = set()

    async def start(self):
        require_live()
        companies = [v for k, v in json.loads(open(self.config_file_path).read()).items() if v]
        query_params = self.get_api_pages_query_params(company_ids=companies)
        yield scrapy.Request(
            self.url_api_pages_pattern.format(query=self.get_query(query_params)),
            self.parse_pages_api,
            headers=self.get_api_headers(),
            cb_kwargs={'companies': companies},
        )

    def parse_pages_api(self, response, companies):
        data = response.json()

        if get('data.advancedTitleSearch.pageInfo.hasNextPage', data):
            query_params = self.get_api_pages_query_params(
                company_ids=companies,
                need_after=True,
                after_field=get('data.advancedTitleSearch.pageInfo.endCursor', data),
            )
            yield scrapy.Request(
                self.url_api_pages_pattern.format(query=self.get_query(query_params)),
                self.parse_pages_api,
                headers=self.get_api_headers(),
                cb_kwargs={'companies': companies},
            )

        yield from self.process_movies(data)

    def process_movies(self, data):
        movies = get('data.advancedTitleSearch.edges', data)
        for movie in movies:
            movie_data = get('node.title', movie)

            movie_id = get('id', movie_data)
            if movie_id in self.ids:
                continue
            self.ids.add(movie_id)

            release_year = get('releaseYear', movie_data)

            if release_year and (year := release_year.get('year')):
                end_year = release_year.get('endYear')
                if end_year and end_year < 2022 or year < 2022:
                    continue

            yield {
                'id': movie_id,
                'text': get('originalTitleText.text', movie_data),
                'release_year': release_year,
                'link': f'https://www.imdb.com/title/{movie_id}/',
                'extra_info': movie_data,
            }

    def get_query(self, query_params: list):
        query = parse.unquote(parse.urlencode(query_params, quote_via=parse.quote))
        query = re.sub(r'\s', '', query)
        query = re.sub(r"'", '"', query)
        return query

    def get_api_pages_query_params(
        self,
        company_ids: list,
        need_after: bool = False,
        after_field: str = None,
        last_movie_id: str = None,
        last_index: int = None,
    ):
        params = {
            'operationName': 'AdvancedTitleSearch',
            'variables': {
                'creditedCompanyConstraint': {
                    'anyCompanyIds': company_ids,
                    'excludeCompanyIds': [],
                },
                'first': self.page_limit,
                'locale': 'en-EN',
                'sortBy': 'RELEASE_DATE',
                'sortOrder': 'DESC',
            },
            'extensions': {
                'persistedQuery': {
                    'sha256Hash': self.get_hash(),
                    'version': 1,
                }
            },
        }
        if need_after:
            params['variables']['after'] = after_field or self.get_after_field(
                last_movie_id, company_ids, last_index
            )
        return params

    def get_after_field(self, last_movie_id: str, company_ids: list, last_index: int):
        data = {
            'esToken': ['1686700800000', '16845', last_movie_id],
            'filter': {
                'constraints': {
                    'creditedCompanyConstraint': {
                        'anyCompanyIds': company_ids,
                        'excludeCompanyIds': [],
                    }
                },
                'sort': {'sortBy': 'RELEASE_DATE', 'sortOrder': 'DESC'},
                'resultIndex': last_index - 1,
            },
        }
        data['filter'] = json.dumps(data['filter'], separators=(',', ':'))
        return self.encode_base64(data)

    @staticmethod
    def decode_base64(encoded_text) -> dict:
        return json.loads(base64.b64decode(encoded_text).decode())

    @staticmethod
    def encode_base64(dict_data) -> str:
        return base64.b64encode(json.dumps(dict_data, separators=(',', ':')).encode()).decode()

    @staticmethod
    def get_web_headers():
        return {
            'Accept-Language': 'en',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Priority': 'u=0, i',
            'Sec-Ch-Ua': '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': 'macOS',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        }

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
    def get_hash():
        return 'f3e9d880ef5404e832446904abc3c455b762cf23c66089c3747ae96dfb3c0065'


if __name__ == '__main__':
    require_live()
    s = get_project_settings()
    process = CrawlerProcess(s)
    crawler = process.create_crawler(IMDB_Movies_Extractor)
    process.crawl(crawler)
    process.start()
