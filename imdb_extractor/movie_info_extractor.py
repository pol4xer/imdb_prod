import re
from collections import defaultdict

import numpy as np
import pandas as pd
import scrapy
import yaml
from scrapy import signals
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from settings import (
    CONFIG_FILE_PATH,
    get_full_source_parse_file_name,
    get_full_output_parse_file_name,
)


class IMDB_Movies_Extractor_From_File(scrapy.Spider):
    name = 'imdb_movies_extractor'
    custom_settings = {
        'DOWNLOAD_DELAY': 0.3,
        'CONCURRENT_REQUESTS': 2,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 2,
    }

    movies_api_url = 'https://pro.imdb.com/company/{id}/filmography/_paginated?filmographyGroup=IN_DEVELOPMENT&page=1&sortOrder=DEFAULT&offset=0&type=ALL&titleCompanyDistRegion=ALL'
    movie_web_url = 'https://pro.imdb.com/title/{id}/'
    filmmakers_api_url = 'https://pro.imdb.com/title/{movie_id}/filmmakers/_ajax'
    company_credits_api_url = (
        'https://pro.imdb.com/title/{movie_id}/companycredits/_ajax'
    )

    get_id_pattern = re.compile(r'/\s*(\w+\d+)\s*/')
    results = []

    def __init__(self, *args, **kwargs):
        with open(CONFIG_FILE_PATH) as file:
            config = yaml.safe_load(file)['parse_stage']

        self.file_type = config['file_type']
        self.source_filename = get_full_source_parse_file_name()
        self.output_filename = get_full_output_parse_file_name()
        self.movie_status = config['movie_status']
        self.cookies = config['cookies']
        self.with_cast = config.get('with_cast', False)

        super().__init__(**kwargs)

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.spider_idle, signals.spider_idle)
        return spider

    def start_requests(self):
        data = pd.read_excel(self.source_filename, header=None, names=['name', 'link'])
        for i, row in data.iterrows():
            agents_id = re.search(self.get_id_pattern, row['link']).group(1)
            yield scrapy.Request(
                self.movies_api_url.format(id=agents_id),
                self.get_pre_prod_movies,
                cookies=self.get_cookies(),
                cb_kwargs={'agent_id': agents_id},
            )

    def get_pre_prod_movies(self, response, agent_id):
        block = response.xpath(
            f'//span[contains(text(), "{self.movie_status}")]/ancestor::tr'
        )
        movie_links = block.xpath(".//span[@class='a-size-base-plus']")
        for data in movie_links:
            a = data.xpath('.//a')
            movie_link = a.xpath('./@href').get()
            movie_name = a.xpath('./text()').get()
            reg_res = re.search(self.get_id_pattern, movie_link)
            if not reg_res:
                continue
            movie_id = reg_res.group(1)
            yield scrapy.Request(
                self.movie_web_url.format(id=movie_id),
                self.parse_summary,
                cookies=self.get_cookies(),
                meta={
                    'item': {
                        'name': movie_name,
                        'movie_id': movie_id,
                        'agent_id': agent_id,
                    }
                },
            )

    def parse_summary(self, response):
        summary = response.xpath("//div[@id='title_summary']/text()").get()
        item = response.meta['item']
        item['summary'] = summary.strip() if summary else None

        stars = []
        for index, data in enumerate(response.xpath("//a[@data-tab='cst']"), start=1):
            if index % 2 == 0:
                continue
            if star := data.xpath('text()').get():
                stars.append(star.strip())

        if self.with_cast and not stars:
            return

        item['stars'] = stars[:4]

        yield scrapy.Request(
            self.filmmakers_api_url.format(movie_id=item['movie_id']),
            self.parse_filmmakers,
            cookies=self.get_cookies(),
            meta={'item': item},
        )

    def parse_filmmakers(self, response):
        item = response.meta['item']

        director = response.xpath(
            "//table[@data-filterable-name='director']//a[@data-tab='fm']/text()"
        ).get()
        item['director'] = director

        team = defaultdict(list)
        for filmmaker in response.xpath("//tr[@class='filmmaker']"):
            occupation = filmmaker.xpath(
                ".//span[@class='see_more_text_collapsed']/text()"
            ).get()
            occupation = self.to_snake_case(occupation)
            if occupation not in ['producer', 'executive_producer']:
                continue
            full_name = filmmaker.xpath(".//a[@data-tab='fm']/text()").get()
            team[occupation].append(full_name)

        for k, v in team.items():
            item[k] = v

        yield scrapy.Request(
            self.company_credits_api_url.format(movie_id=item['movie_id']),
            self.parse_company_credits,
            cookies=self.get_cookies(),
            meta={'item': item},
        )

    def parse_company_credits(self, response):
        item = response.meta['item']

        production = response.xpath(
            "//table[@id='production']//a[@class='a-size- a-align- a-link-']/text()"
        ).getall()
        sales = response.xpath(
            "//table[@id='sales']//a[@class='a-size- a-align- a-link-']/text()"
        ).getall()
        item['company_production'] = production
        item['company_sales'] = sales
        item['company_name'] = response.xpath(
            f"//a[contains(@href, '/company/{item['agent_id']}')]/text()"
        ).get()

        self.yield_item(item)

    def yield_item(self, item):
        item['movie_link'] = f'https://pro.imdb.com/title/{item["movie_id"]}/'
        item['agent_link'] = f'https://pro.imdb.com/company/{item["agent_id"]}/'
        item['status'] = self.movie_status
        self.results.append(item)
        return

    @staticmethod
    def to_snake_case(text):
        if not text:
            return None

        return '_'.join(
            re.sub(
                '([A-Z][a-z]+)',
                r' \1',
                re.sub('([A-Z]+)', r' \1', text.replace('-', ' ')),
            ).split()
        ).lower()

    def get_cookies(self):
        return self.cookies

    def spider_idle(self, spider):
        result = (
            pd.DataFrame(self.results)
            .reset_index()
            .fillna(np.nan)
            .replace([np.nan], [None])
            .drop(columns=['index'])
        )

        if self.file_type == 'csv':
            result.to_csv(self.output_filename)
        elif self.file_type == 'xlsx':
            result.to_excel(self.output_filename)
        else:
            raise Exception(f"Scrapy Error: Unknown data type '{self.file_type}'")


if __name__ == '__main__':
    s = get_project_settings()
    process = CrawlerProcess(s)
    crawler = process.create_crawler(IMDB_Movies_Extractor_From_File)
    process.crawl(crawler)
    process.start()
