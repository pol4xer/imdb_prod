import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

from imdb_extractor.live import require_live
from imdb_extractor.tabular import REPORT_COLUMNS, read_companies, write_table
from settings import (
    get_full_output_parse_file_name,
    get_full_source_parse_file_name,
    open_config,
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
    company_credits_api_url = 'https://pro.imdb.com/title/{movie_id}/companycredits/_ajax'

    get_id_pattern = re.compile(r'/\s*(\w+\d+)\s*/')
    allowed_domains = ['pro.imdb.com']

    def __init__(self, *args, config=None, cookies=None, **kwargs):
        super().__init__(*args, **kwargs)
        config = config if config is not None else open_config()['parse_stage']
        self.file_type = config['file_type']
        self.source_filename = get_full_source_parse_file_name()
        self.output_filename = get_full_output_parse_file_name()
        self.movie_status = config['movie_status']
        self.cookies = cookies if cookies is not None else load_cookies()
        self.with_cast = config.get('with_cast', False)
        self.results = []
        self.export_completed = False
        self.company_names = {}
        if self.file_type not in {'csv', 'xlsx'}:
            raise ValueError('Export format must be CSV or XLSX.')
        if self.movie_status not in {
            '',
            'Development',
            'Pre-production',
            'Production',
            'Post-production',
            'Completed',
        }:
            raise ValueError('Choose a supported movie status.')
        if not self.output_filename:
            raise ValueError('Choose an export filename first.')
        self.companies = read_companies(self.source_filename)

    async def start(self):
        require_live()
        for company in self.companies:
            self.company_names[company['id']] = company['name']
            yield scrapy.Request(
                self.movies_api_url.format(id=company['id']),
                self.get_pre_prod_movies,
                cookies=self.get_cookies(),
                cb_kwargs={'agent_id': company['id']},
            )

    def get_pre_prod_movies(self, response, agent_id):
        block = response.xpath('//tr')
        if self.movie_status:
            block = block.xpath(
                './/span[contains(text(), $status)]/ancestor::tr', status=self.movie_status
            )
        movie_links = block.xpath(".//span[@class='a-size-base-plus']")
        for data in movie_links:
            a = data.xpath('.//a')
            movie_link = a.xpath('./@href').get()
            movie_name = a.xpath('./text()').get()
            reg_res = re.search(self.get_id_pattern, movie_link or '')
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
            occupation = filmmaker.xpath(".//span[@class='see_more_text_collapsed']/text()").get()
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
        ).get() or self.company_names.get(item['agent_id'], 'Unspecified company')

        self.yield_item(item)

    def yield_item(self, item):
        item['movie_link'] = f'https://pro.imdb.com/title/{item["movie_id"]}/'
        item['agent_link'] = f'https://pro.imdb.com/company/{item["agent_id"]}/'
        item['status'] = self.movie_status or 'Not filtered'
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

    def closed(self, reason):
        if reason == 'finished' and self.results:
            rows = [{key: item.get(key, '') for key in REPORT_COLUMNS} for item in self.results]
            write_table(rows, self.output_filename)
            self.export_completed = True


def load_cookies():
    cookie_file = os.environ.get('IMDB_COOKIES_FILE')
    if not cookie_file:
        raise ValueError('Set IMDB_COOKIES_FILE to a private JSON cookie file for live extraction.')
    try:
        cookies = json.loads(Path(cookie_file).expanduser().read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError('Cannot read IMDB_COOKIES_FILE as JSON.') from error
    if (
        not isinstance(cookies, dict)
        or not cookies
        or any(
            not isinstance(key, str) or not key or not isinstance(value, str)
            for key, value in cookies.items()
        )
    ):
        raise ValueError('The cookie file must contain a nonempty JSON object of string values.')
    return cookies


def main():
    if os.environ.get('IMDB_ENABLE_LIVE', '').lower() != 'true':
        print(
            'Live extraction is disabled. Use the offline demo or explicitly set IMDB_ENABLE_LIVE=true.',
            file=sys.stderr,
        )
        return 1
    try:
        # Validate before starting the reactor so bad input produces a nonzero exit.
        IMDB_Movies_Extractor_From_File()
        process = CrawlerProcess(get_project_settings())
        crawler = process.create_crawler(IMDB_Movies_Extractor_From_File)
        process.crawl(crawler)
        process.start()
        stats = crawler.stats.get_stats()
        failed = stats.get('spider_exceptions/count', 0) or any(
            key.startswith('downloader/response_status_count/')
            and int(key.rsplit('/', 1)[-1]) >= 400
            for key in stats
        )
        if (
            failed
            or stats.get('finish_reason') != 'finished'
            or not crawler.spider.export_completed
        ):
            print(
                'No complete export was produced. The legacy live selectors or session may need updating.',
                file=sys.stderr,
            )
            return 1
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
