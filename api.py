import urllib.request
import urllib.parse
import json
from html.parser import HTMLParser


def get_json(url: str):
    req = urllib.request.urlopen(url)
    return json.load(req)


def artist_by_name(name: str):
    params = {
        'entity': 'allArtist',
        'term': name,
        'attribute': 'allArtistTerm',
        'limit': 1
    }

    url = 'https://itunes.apple.com/search?%s' % urllib.parse.urlencode(params)
    data = get_json(url)
    assert(data.get('resultCount') == 1)
    first = data['results'].pop()
    return first


def lookup(*artist_ids):
    q = ','.join(*artist_ids)
    url = 'https://itunes.apple.com/lookup?id=%s' % q
    data = get_json(url)
    return data


def artist_avatar(page_url):
    req = urllib.request.urlopen(page_url)

    class MetaDataParser(HTMLParser):
        url: str = None

        def handle_starttag(self, tag: str, attrs):
            if tag.lower() == 'meta':
                d = {name.lower(): val for name, val in attrs}
                if d.get('property', '').lower() == 'og:image':
                    self.url = d.get('content')
                    # unfortunately HTMLParser can't stop

    parser = MetaDataParser()
    parser.feed(req.read().decode('utf8'))
    url = parser.url
    if type(url) is str:
        return '%s/400x400bf.jpg' % url[0:url.rfind('/')]
    raise ValueError('Unable to get avatar from %s' % page_url)


def song_info(name: str):
    params = {
        'entity': 'song',
        'term': name,
        'limit': 1
    }
    url = 'https://itunes.apple.com/search?%s' % urllib.parse.urlencode(params)
    data = get_json(url)
    assert(data.get('resultCount') == 1)
    first = data['results'].pop()
    return first


def artwork(name: str, size=100):
    data = song_info(name)
    url = data['artworkUrl100']
    resize = '/{0}x{0}bb.jpg'.format(size)
    return url.replace('/100x100bb.jpg', resize)


if __name__ == '__main__':
    # simple test
    print(artist_by_name('The Weeknd')['artistLinkUrl'])
    print(artwork('The Weeknd - Blinding Lights', 400))
