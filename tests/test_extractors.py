import asyncio
import json

import pandas as pd
import pytest
from scrapy.http import HtmlResponse, Request

from imdb_extractor import movie_info_extractor as movies
from imdb_extractor.movie_extractor import IMDB_Movies_Extractor
from imdb_extractor.producer_extractor import IMDB_Producers_Extractor
from imdb_extractor.producers_info_extractor import IMDB_Producers_Info_Extractor
from imdb_extractor.tabular import company_id, read_companies, read_table


@pytest.mark.parametrize('extension', ['csv', 'xlsx'])
@pytest.mark.parametrize('header', [True, False])
def test_company_inputs_accept_supported_formats_and_legacy_headers(tmp_path, extension, header):
    source = tmp_path / f'companies.{extension}'
    frame = pd.DataFrame(
        [{'name': 'Fictional company', 'link': 'https://pro.imdb.com/company/co0000001/'}]
    )
    if extension == 'csv':
        frame.to_csv(source, index=False, header=header)
    else:
        frame.to_excel(source, index=False, header=header)
    assert read_companies(source)[0]['id'] == 'co0000001'


@pytest.mark.parametrize(
    'link',
    [
        'https://evil.invalid/company/co0000001/',
        'https://pro.imdb.com.evil.invalid/company/co0000001/',
        'file:///company/co0000001/',
        'https://pro.imdb.com/title/tt0000001/',
        'https://pro.imdb.com/company/invalid/',
    ],
)
def test_company_links_cannot_choose_arbitrary_destinations(link):
    assert company_id(link) is None


def test_company_input_rejects_wrong_columns_empty_rows_and_bad_links(tmp_path):
    source = tmp_path / 'companies.csv'
    source.write_text('name,wrong\nExample,https://example.invalid/\n')
    with pytest.raises(ValueError, match='name and link columns'):
        read_companies(source)
    source.write_text('name,link\n')
    with pytest.raises(ValueError, match='no rows'):
        read_companies(source)
    source.write_text('name,link\nExample,https://example.invalid/\n')
    with pytest.raises(ValueError, match='Company row 1'):
        read_companies(source)


@pytest.fixture
def spider_factory(tmp_path, monkeypatch):
    source = tmp_path / 'companies.csv'
    source.write_text('name,link\nFictional company,https://pro.imdb.com/company/co0000001/\n')
    monkeypatch.setattr(movies, 'get_full_source_parse_file_name', lambda: str(source))
    monkeypatch.setattr(
        movies, 'get_full_output_parse_file_name', lambda: str(tmp_path / 'movies.csv')
    )

    def create(**overrides):
        config = {'file_type': 'csv', 'movie_status': '', 'with_cast': False}
        config.update(overrides)
        return movies.IMDB_Movies_Extractor_From_File(config=config, cookies={})

    return create


def test_current_scrapy_start_creates_fixed_company_requests(spider_factory, monkeypatch):
    monkeypatch.setenv('IMDB_ENABLE_LIVE', 'true')
    spider = spider_factory()

    async def collect():
        return [request async for request in spider.start()]

    requests = asyncio.run(collect())
    assert len(requests) == 1
    assert requests[0].url.startswith('https://pro.imdb.com/company/co0000001/filmography/')
    assert requests[0].cb_kwargs == {'agent_id': 'co0000001'}


def test_status_filter_uses_validated_values(spider_factory):
    with pytest.raises(ValueError, match='supported movie status'):
        spider_factory(movie_status='bad" XPath')
    spider = spider_factory(movie_status='Pre-production')
    body = """<table><tr><td><span>Pre-production</span><span class="a-size-base-plus"><a href="/title/tt0000001/">Fictional title</a></span></td></tr><tr><td><span>Completed</span><span class="a-size-base-plus"><a href="/title/tt0000002/">Other title</a></span></td></tr></table>"""
    response = HtmlResponse('https://pro.imdb.com/company/co0000001/', body=body, encoding='utf-8')
    requests = list(spider.get_pre_prod_movies(response, 'co0000001'))
    assert len(requests) == 1
    assert requests[0].url == 'https://pro.imdb.com/title/tt0000001/'


def test_cast_filter_stops_incomplete_movie(spider_factory):
    spider = spider_factory(with_cast=True)
    response = HtmlResponse(
        'https://pro.imdb.com/title/tt0000001/',
        body='<div id="title_summary">Example</div>',
        encoding='utf-8',
        request=Request('https://pro.imdb.com/title/tt0000001/', meta={'item': {}}),
    )
    assert list(spider.parse_summary(response)) == []


def test_spider_instances_do_not_share_results(spider_factory):
    first, second = spider_factory(), spider_factory()
    first.results.append({'name': 'Fictional title'})
    assert second.results == []
    for extractor, field, value in [
        (IMDB_Movies_Extractor, 'ids', 'tt0000001'),
        (IMDB_Producers_Extractor, 'producers_dict', ('person', {})),
        (IMDB_Producers_Info_Extractor, 'results', {}),
    ]:
        first, second = extractor(), extractor()
        if field == 'ids':
            first.ids.add(value)
        elif field == 'producers_dict':
            first.producers_dict[value[0]] = value[1]
        else:
            first.results.append(value)
        assert not getattr(second, field)


def test_spider_exports_explicit_columns_without_index(spider_factory):
    spider = spider_factory()
    spider.results.append({'name': 'Fictional title', 'company_name': 'Fictional company'})
    spider.closed('finished')
    assert spider.export_completed
    result = read_table(spider.output_filename)
    assert result.loc[0, 'name'] == 'Fictional title'
    assert 'executive_producer' in result.columns
    assert not any(column.startswith('Unnamed:') for column in result.columns)


def test_live_command_is_disabled_by_default(monkeypatch, capsys):
    monkeypatch.delenv('IMDB_ENABLE_LIVE', raising=False)
    assert movies.main() == 1
    assert 'Live extraction is disabled' in capsys.readouterr().err


def test_cookie_file_requires_nonempty_string_mapping(tmp_path, monkeypatch):
    monkeypatch.delenv('IMDB_COOKIES_FILE', raising=False)
    with pytest.raises(ValueError, match='IMDB_COOKIES_FILE'):
        movies.load_cookies()
    source = tmp_path / 'cookies.json'
    monkeypatch.setenv('IMDB_COOKIES_FILE', str(source))
    source.write_text(json.dumps(['invalid']))
    with pytest.raises(ValueError, match='JSON object'):
        movies.load_cookies()
    source.write_text(json.dumps({'fixture': 'test-only-cookie'}))
    assert movies.load_cookies() == {'fixture': 'test-only-cookie'}


def test_live_spider_cannot_bypass_opt_in_via_scrapy_api(spider_factory, monkeypatch):
    monkeypatch.delenv('IMDB_ENABLE_LIVE', raising=False)

    async def collect():
        return [request async for request in spider_factory().start()]

    with pytest.raises(ValueError, match='Live extraction is disabled'):
        asyncio.run(collect())


def test_failed_export_never_reports_completion(spider_factory, monkeypatch):
    spider = spider_factory()
    spider.results.append({'name': 'Fictional title'})

    def fail_write(*args, **kwargs):
        raise OSError('Read-only test directory')

    monkeypatch.setattr(movies, 'write_table', fail_write)
    with pytest.raises(OSError):
        spider.closed('finished')
    assert not spider.export_completed
