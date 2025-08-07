from scrapy import signals

import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
import pandas as pd


class IMDB_Producers_Extractor(scrapy.Spider):
    name = 'imdb_producers'
    web_url_pattern = 'https://m.imdb.com/title/{movie_id}/fullcredits/producer'
    producer_url_pattern = 'https://m.imdb.com{}'
    file_path = '/imdb_extractor/data/movies.csv'

    producers_dict = {}

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        """Init crawler and connect spider.spider_idle method"""
        spider = super().from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.spider_idle, signals.spider_idle)
        return spider

    def start_requests(self):
        movies = pd.read_csv(self.file_path).to_dict('records')
        for i, movie in enumerate(movies):
            yield scrapy.Request(
                self.web_url_pattern.format(movie_id=movie['id']),
                self.parse_movie_producers,
                headers=self.get_headers(),
                cb_kwargs={'name': movie['text'], 'link': movie['link']},
            )

    def parse_movie_producers(self, response, name, link):
        producers = response.xpath(
            "//section[@id='fullcredits-content']//div[@class='row']//a"
        ).getall()
        for producer in producers:
            selector = scrapy.Selector(text=producer)

            producer_name = selector.xpath('//h4//text()').get()
            if not producer_name:
                continue

            producer_link = selector.xpath('//a/@href').get()
            if not producer_link:
                continue

            if producer_name in self.producers_dict:
                self.producers_dict[producer_name]['movies'].append(
                    {'name': name, 'link': link}
                )
                self.producers_dict[producer_name]['titles'].append(
                    {'movie': name, 'title': selector.xpath('//p//text()').get()}
                )
                pass
            else:
                self.producers_dict[producer_name] = {
                    'name': producer_name,
                    'producer_link': self.producer_url_pattern.format(producer_link),
                    'titles': [
                        {'movie': name, 'title': selector.xpath('//p//text()').get()}
                    ],
                    'movies': [{'name': name, 'link': link}],
                }

    def parse_producer(self, response):
        pass

    def spider_idle(self, spider):
        pd.DataFrame.from_dict(
            self.producers_dict, orient='index'
        ).reset_index().to_csv('data/producers.csv')

    @staticmethod
    def get_headers():
        return {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,de;q=0.6,tr;q=0.5,pl;q=0.4',
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


if __name__ == '__main__':
    s = get_project_settings()
    process = CrawlerProcess(s)
    crawler = process.create_crawler(IMDB_Producers_Extractor)
    process.crawl(crawler)
    process.start()
